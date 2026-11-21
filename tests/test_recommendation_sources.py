import base64
import io
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from PIL import Image
from pypdf import PdfReader
from app import app
from case_store import CaseStore
from recommendation_sources import RecommendationCatalog, ReferenceError


class RecommendationsTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        self.catalog = RecommendationCatalog(Path(__file__).resolve().parents[1] / 'references/catalog.json')
        self.sources, self.templates = self.catalog.parts()
        image = io.BytesIO()
        Image.new('RGB', (48, 32), 'tan').save(image, 'PNG')
        self.doc = dict(image='data:image/png;base64,' + base64.b64encode(image.getvalue()).decode(),
                        source='程序生成的测试图', reviewed=True, model_label='测试初稿',
                        regions=[dict(id='R1', origin='ai', x=.1, y=.1, w=.5, h=.5, observation='浅色区边缘不连续')],
                        recommendations=[self.advice('C1')], uncertainty='本例只检验图像记录，不作病害成因鉴定。', reference_version=1)

    def advice(self, template_id):
        template = self.templates[template_id]
        return dict(target='R1', origin='human', template_id=template_id, category=template['category'],
                    action=template['action'], basis='R1 浅色区边缘不连续，需保留可比较记录。',
                    risk=template['risk'], source_ids=template['source_ids'])

    def export(self):
        return self.client.post('/api/report/observation', json=self.doc)

    def test_book_citations_are_generated_by_server_and_fit_one_page(self):
        self.doc['recommendations'][0]['source_citations'] = [{'title': '伪造专家背书'}]
        response = self.export()
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        reader = PdfReader(io.BytesIO(response.data))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        self.assertIn('The Conservation of Wall Paintings', text)
        self.assertIn('[B1]', text)
        self.assertIn('第23页', text)
        self.assertNotIn('伪造专家背书', text)
        self.assertTrue(reader.pages[0].get('/Annots'))

    def test_two_categories_and_four_references_remain_on_one_page(self):
        self.doc['recommendations'].append(self.advice('D2'))
        response = self.export()
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        reader = PdfReader(io.BytesIO(response.data))
        self.assertEqual(len(reader.pages), 1)
        text = reader.pages[0].extract_text()
        for sid in ['B1', 'G1', 'G3', 'G4']:
            self.assertIn('[' + sid + ']', text)

    def test_unverified_or_rewritten_action_cannot_borrow_a_book_attribution(self):
        for field, value in [('template_id', ''), ('source_ids', ['MADEUP']),
                             ('action', '使用某药剂清洗并加固原物'), ('category', 'outreach')]:
            with self.subTest(field=field):
                old = deepcopy(self.doc['recommendations'][0][field])
                self.doc['recommendations'][0][field] = value
                response = self.export()
                self.assertEqual(response.status_code, 400)
                self.assertIn('建议 1', response.get_json()['error'])
                self.doc['recommendations'][0][field] = old

    def test_case_api_saves_drafts_and_reference_snapshots_without_api_credentials(self):
        old = app.extensions['case_store']
        with tempfile.TemporaryDirectory() as directory:
            app.extensions['case_store'] = CaseStore(directory)
            try:
                project = dict(self.doc, version=3, api_key='not-a-real-key')
                response = self.client.post('/api/cases', json={'project': project, 'title': '文献案例'})
                self.assertEqual(response.status_code, 200, response.get_json(silent=True))
                case_id = response.get_json()['id']
                restored = self.client.get('/api/cases/' + case_id).get_json()
                self.assertNotIn('api_key', restored['project'])
                self.assertEqual(restored['project']['image'], project['image'])
                self.assertEqual(restored['citations'][0]['source']['locator'], 'Dasser章节，第23页')
                draft = dict(project, recommendations=[{'action': '', 'basis': '', 'risk': ''}])
                saved = self.client.post('/api/cases/' + case_id + '/save', json={
                    'project': draft, 'title': '文献案例', 'expected_version': 1})
                self.assertEqual(saved.status_code, 200, saved.get_json(silent=True))
                stale = self.client.post('/api/cases/' + case_id + '/save', json={
                    'project': project, 'title': '文献案例', 'expected_version': 1})
                self.assertEqual(stale.status_code, 409)
                self.assertEqual(self.client.get('/api/cases/' + case_id + '?version=1').get_json()['project']['recommendations'], project['recommendations'])
            finally:
                app.extensions['case_store'] = old

    def test_case_routes_retain_origin_and_local_access_guards(self):
        self.assertEqual(self.client.get('/api/cases', environ_base={'REMOTE_ADDR': '10.0.0.2'}).status_code, 403)
        self.assertEqual(self.client.post('/api/cases', json={}, headers={'Origin': 'https://hostile.example'}).status_code, 403)
        self.assertEqual(self.client.get('/api/cases/../../outside').status_code, 404)

    def test_catalog_covers_categories_and_each_template_has_precise_sources(self):
        self.assertEqual({t['category'] for t in self.templates.values()}, {'conservation', 'display', 'outreach'})
        for tid, template in self.templates.items():
            row = self.advice(tid)
            resolved = self.catalog.resolve(row, 0, strict=True)
            self.assertTrue(resolved['source_citations'])
            for s in resolved['source_citations']:
                self.assertTrue(s['verified_on'])
                self.assertEqual(s['locator'], template['source_locators'][s['id']])
