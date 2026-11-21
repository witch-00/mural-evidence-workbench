import base64
import io
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

from PIL import Image
from case_store import CaseStore, StoreError


def image_data(color='tan'):
    out = io.BytesIO()
    Image.new('RGB', (24, 16), color).save(out, 'PNG')
    return 'data:image/png;base64,' + base64.b64encode(out.getvalue()).decode()


class CaseStoreTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = CaseStore(self.temp.name)
        self.project = dict(version=3, image=image_data(), mask=None, restored=None,
                            source='测试图', regions=[], recommendations=[], events=[])

    def test_reopen_database_recovers_project_and_deduplicates_images(self):
        first = self.store.save(self.project, '壁画一')
        changed = deepcopy(self.project)
        changed['source'] = '补充了授权'
        second = self.store.save(changed, '壁画一', first['id'], 1)
        other = CaseStore(self.temp.name)
        self.assertEqual(other.read(first['id'])['project'], changed)
        self.assertEqual(other.read(first['id'], 1)['project'], self.project)
        self.assertEqual(second['current_version'], 2)
        self.assertEqual(len(list(other.images.iterdir())), 1)
        self.assertEqual(len(other.versions(first['id'])), 2)

    def test_unchanged_save_does_not_create_version(self):
        case = self.store.save(self.project, '壁画一')
        saved = self.store.save(self.project, '壁画一', case['id'], 1)
        self.assertTrue(saved['unchanged'])
        self.assertEqual(len(self.store.versions(case['id'])), 1)

    def test_two_writers_cannot_silently_overwrite_same_version(self):
        case = self.store.save(self.project, '并发案例')
        def write(source):
            project = dict(self.project, source=source)
            try:
                return self.store.save(project, '并发案例', case['id'], 1)['current_version']
            except StoreError as exc:
                return exc.status
        with ThreadPoolExecutor(2) as pool:
            results = list(pool.map(write, ['甲的修改', '乙的修改']))
        self.assertCountEqual(results, [2, 409])
        self.assertEqual(len(self.store.versions(case['id'])), 2)

    def test_failed_transaction_preserves_previous_version(self):
        case = self.store.save(self.project, '事务测试')
        changed = dict(self.project, recommendations=[{'action': '记录'}])
        with self.assertRaises(sqlite3.IntegrityError):
            self.store.save(changed, '事务测试', case['id'], 1,
                            citations=[(0, {'id': 'B1'}), (0, {'id': 'B1'})])
        self.assertEqual(self.store.read(case['id'])['project'], self.project)
        self.assertEqual(len(self.store.versions(case['id'])), 1)

    def test_reference_snapshot_and_case_data_survive_later_edits(self):
        project = dict(self.project, recommendations=[{'source_ids': ['B1']}], api_key='do-not-store')
        case = self.store.save(project, '引用案例', citations=[(0, {'id': 'B1', 'title': '第一版依据'})])
        project['source'] = '新一版'
        self.store.save(project, '引用案例', case['id'], 1,
                        citations=[(0, {'id': 'B1', 'title': '修订后的书目'})])
        old = self.store.read(case['id'], 1)
        self.assertNotIn('api_key', old['project'])
        self.assertEqual(old['citations'][0]['source']['title'], '第一版依据')

    def test_invalid_or_missing_asset_is_reported_without_losing_case(self):
        with self.assertRaises(StoreError):
            self.store.save(dict(self.project, image='data:image/png;base64,AAA='))
        self.assertEqual(self.store.list_cases(), [])
        case = self.store.save(self.project, '图片校验')
        next(self.store.images.iterdir()).write_bytes(b'corrupted')
        with self.assertRaisesRegex(StoreError, '校验失败'):
            self.store.read(case['id'])
        self.store.save(self.project, '从完整工作文件恢复')
        self.assertEqual(self.store.read(case['id'])['project'], self.project)

    def test_schema_and_foreign_keys_are_active(self):
        with self.store.connect() as con:
            self.assertEqual(con.execute('PRAGMA user_version').fetchone()[0], 1)
            self.assertEqual(con.execute('PRAGMA foreign_keys').fetchone()[0], 1)
            self.assertEqual(con.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
