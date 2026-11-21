"""Verified reference catalogue and bounded recommendation templates."""
import copy
import json
import re
from pathlib import Path


CATEGORIES = {'conservation': '保护建议', 'display': '数字展示', 'outreach': '公众传播'}


class ReferenceError(ValueError):
    pass


class RecommendationCatalog:
    def __init__(self, path):
        self.path = Path(path)
        self._mtime = None
        self._data = None

    def data(self):
        stamp = self.path.stat().st_mtime_ns
        if stamp != self._mtime:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            sources = {s['id']: s for s in data['sources']}
            if len(sources) != len(data['sources']):
                raise RuntimeError('参考目录存在重复编号。')
            for source in sources.values():
                if not re.fullmatch(r'[A-Z][A-Z0-9_-]{0,20}', source['id']):
                    raise RuntimeError('参考目录编号无效。')
            for item in data['templates']:
                if item['category'] not in CATEGORIES or not 1 <= len(item['source_ids']) <= 2:
                    raise RuntimeError('建议模板分类或引用无效。')
                if any(key not in sources or not item['source_locators'].get(key) for key in item['source_ids']):
                    raise RuntimeError('建议模板缺少已核验的文献定位。')
            self._data, self._mtime = data, stamp
        return copy.deepcopy(self._data)

    def parts(self):
        data = self.data()
        return ({s['id']: s for s in data['sources']}, {t['id']: t for t in data['templates']})

    def resolve(self, row, index, strict=False):
        sources, templates = self.parts()
        ids = row.get('source_ids', [])
        if not isinstance(ids, list) or len(ids) > 2 or any(not isinstance(s, str) or s not in sources for s in ids):
            raise ReferenceError(f'建议 {index + 1} 的文献编号无效，请重新选择文献建议。')
        ids = list(dict.fromkeys(ids))
        template_id = row.get('template_id', '')
        if not isinstance(template_id, str) or (template_id and template_id not in templates):
            raise ReferenceError(f'建议 {index + 1} 的文献建议模板无效。')
        template = templates.get(template_id)
        category = row.get('category', '')
        if not isinstance(category, str) or (category and category not in CATEGORIES):
            raise ReferenceError(f'建议 {index + 1} 的分类无效。')
        if strict:
            if not template:
                raise ReferenceError(f'请为建议 {index + 1} 选择一条已核验的文献建议，并填写本图依据。')
            if category != template['category'] or set(ids) != set(template['source_ids']):
                raise ReferenceError(f'建议 {index + 1} 与所选文献模板不一致，请重新选择。')
            if any(str(row.get(key, '')).strip() != template[key] for key in ('action', 'risk')):
                raise ReferenceError(f'建议 {index + 1} 的行动或风险已改变，无法继续沿用该模板的核验。请重新选择文献建议；本案差异可写在“本图依据”。')
        result = []
        for sid in ids:
            source = dict(sources[sid])
            if template and sid in template['source_ids']:
                source['locator'] = template['source_locators'][sid]
            result.append(source)
        return {'category': category, 'template_id': template_id, 'source_ids': ids,
                'source_citations': result, 'literature_basis': template['basis'] if template else ''}

    def draft_citations(self, project):
        result = []
        if not isinstance(project, dict):
            return result
        rows = project.get('recommendations', [])
        if not isinstance(rows, list) or len(rows) > 2:
            raise ReferenceError('工作档案最多保留两条建议。')
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ReferenceError(f'建议 {i + 1} 格式无效。')
            result.extend((i, source) for source in self.resolve(row, i)['source_citations'])
        return result

    def apply_document(self, doc, raw_rows, version=None):
        if version is not None and (type(version) is not int or version != 1):
            raise ReferenceError('文献引用格式无效。')
        cited = {}
        for i, (row, raw) in enumerate(zip(doc['advice'], raw_rows)):
            row.update(self.resolve(raw, i, strict=version == 1))
            for source in row['source_citations']:
                old = cited.get(source['id'])
                if old and source['locator'] not in old['locator']:
                    old['locator'] += '；' + source['locator']
                elif not old:
                    cited[source['id']] = dict(source)
        doc['professional_sources'] = list(cited.values())

    def generated_fields(self, raw):
        """Discard unsupported model citation IDs; never manufacture an attribution."""
        sources, templates = self.parts()
        ids = raw.get('source_ids', [])
        ids = list(dict.fromkeys(s for s in ids if isinstance(s, str) and s in sources))[:2] if isinstance(ids, list) else []
        tid = raw.get('template_id', '')
        tid = tid if isinstance(tid, str) and tid in templates else ''
        category = raw.get('category', '')
        return {'source_ids': ids, 'template_id': tid, 'category': category if isinstance(category, str) and category in CATEGORIES else ''}

    def prompt_context(self):
        data = self.data()
        sources = [{'id': s['id'], 'title': s['short_title'], 'year': s['year'], 'scope': s['scope']} for s in data['sources']]
        return ('\n下列文献和建议模板已核对全文。建议可从模板选择，action、risk 原样使用，'
                'basis 必须描述本图可见依据；category、source_ids、template_id 对应所选模板。'
                '文献只支持原则，不能证明本图存在某种病害，禁止编造引文、页码、病害原因、材料参数或机构认证。\n'
                + json.dumps({'sources': sources, 'templates': data['templates']}, ensure_ascii=False))
