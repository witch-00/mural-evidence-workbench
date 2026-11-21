"""Local-only case endpoints; Flask's existing host, origin and login guards apply."""
import sqlite3
from flask import Blueprint, current_app, jsonify, request

from case_store import CaseStore, StoreError
from recommendation_sources import ReferenceError


def install(app, directory, catalog):
    app.extensions['case_store'] = CaseStore(directory)
    app.extensions['recommendation_catalog'] = catalog
    api = Blueprint('case_library', __name__)

    @api.errorhandler(StoreError)
    def store_error(error):
        return jsonify(error=str(error)), error.status

    @api.errorhandler(ReferenceError)
    def reference_error(error):
        return jsonify(error=str(error)), 400

    @api.errorhandler(sqlite3.OperationalError)
    def unavailable(_error):
        return jsonify(error='本机档案库暂时无法访问。当前编辑仍在页面中，可先导出工作文件，再重试。'), 503

    def store():
        return current_app.extensions['case_store']

    def save(case_id=None):
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise StoreError('请求格式无效。')
        project = data.get('project')
        citations = current_app.extensions['recommendation_catalog'].draft_citations(project)
        return jsonify(store().save(project, data.get('title', ''), case_id,
                                    data.get('expected_version'), data.get('kind', 'manual'), citations))

    @api.get('/api/cases')
    def list_cases():
        return jsonify(cases=store().list_cases(), storage='sqlite')

    @api.post('/api/cases')
    def new_case():
        return save()

    @api.post('/api/cases/<case_id>/save')
    def update(case_id):
        return save(case_id)

    @api.get('/api/cases/<case_id>')
    def read(case_id):
        version = request.args.get('version')
        if version is not None:
            if not version.isdigit():
                raise StoreError('档案版本号无效。')
            version = int(version)
        return jsonify(store().read(case_id, version))

    @api.get('/api/cases/<case_id>/versions')
    def versions(case_id):
        return jsonify(versions=store().versions(case_id))

    @api.get('/api/references')
    def references():
        return jsonify(current_app.extensions['recommendation_catalog'].data())

    app.register_blueprint(api)
