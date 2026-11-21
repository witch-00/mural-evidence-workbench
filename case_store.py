"""Transactional SQLite case versions, with content-addressed private image files."""
from __future__ import annotations

import base64
import binascii
import hashlib
import io
import json
import os
import re
import sqlite3
import tempfile
import uuid
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, UnidentifiedImageError


class StoreError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


PROJECT_FIELDS = {
    'source', 'references', 'context', 'evidence_version', 'regions', 'recommendations',
    'uncertainty', 'uncertainty_origin', 'other_tools', 'reviewed', 'model_label',
    'repair_basis', 'repair_review', 'repair_meta', 'version', 'notice', 'image', 'mask',
    'restored', 'region_seq', 'repair_method', 'sample_point', 'model', 'events', 'artifacts', 'mask_actions',
    'reference_version',
}
SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, current_version INTEGER NOT NULL,
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS case_versions (
 id INTEGER PRIMARY KEY, case_id TEXT NOT NULL REFERENCES cases(id),
 version INTEGER NOT NULL, project_json TEXT NOT NULL, checksum TEXT NOT NULL,
 kind TEXT NOT NULL, created_at TEXT NOT NULL, UNIQUE(case_id,version)
);
CREATE TABLE IF NOT EXISTS assets (
 sha256 TEXT PRIMARY KEY, mime TEXT NOT NULL, byte_length INTEGER NOT NULL,
 width INTEGER NOT NULL, height INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS version_assets (
 version_id INTEGER NOT NULL REFERENCES case_versions(id), role TEXT NOT NULL,
 sha256 TEXT NOT NULL REFERENCES assets(sha256), PRIMARY KEY(version_id,role)
);
CREATE TABLE IF NOT EXISTS reference_sources (
 id TEXT PRIMARY KEY, source_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendation_citations (
 version_id INTEGER NOT NULL REFERENCES case_versions(id), advice_index INTEGER NOT NULL,
 source_id TEXT NOT NULL REFERENCES reference_sources(id), snapshot_json TEXT NOT NULL,
 PRIMARY KEY(version_id,advice_index,source_id)
);
CREATE INDEX IF NOT EXISTS cases_by_updated ON cases(updated_at DESC);
"""


def _json(value):
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError, RecursionError) as exc:
        raise StoreError('工作档案包含无效数据。') from exc


class CaseStore:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.images = self.directory / 'assets'
        self.database = self.directory / 'workbench.sqlite3'
        self.images.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as con:
            version = con.execute('PRAGMA user_version').fetchone()[0]
            if version not in (0, 1):
                raise RuntimeError('工作档案数据库版本高于当前程序，请使用对应版本打开。')
            con.executescript(SCHEMA)
            con.execute('PRAGMA user_version=1')
            con.commit()

    def connect(self):
        con = sqlite3.connect(self.database, timeout=8)
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA synchronous=FULL')
        # Default rollback journaling also works without WAL shared-memory files on WSL mounts.
        return con

    @staticmethod
    def _id(value):
        if not isinstance(value, str) or not re.fullmatch(r'[0-9a-f]{32}', value):
            raise StoreError('档案编号无效。')
        return value

    def _asset(self, value):
        if not isinstance(value, str) or len(value) > 180_000_000:
            raise StoreError('工作档案的图像格式或大小无效。')
        match = re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=\r\n]+)', value)
        if not match:
            raise StoreError('工作档案只支持 PNG、JPEG 或 WebP 图像。')
        try:
            raw = base64.b64decode(match[2], validate=True)
            with Image.open(io.BytesIO(raw)) as image:
                width, height = image.size
                if image.format not in ('PNG', 'JPEG', 'WEBP') or not 0 < width * height <= 80_000_000:
                    raise StoreError('工作档案图像需小于 8000 万像素。')
                mime = {'PNG': 'image/png', 'JPEG': 'image/jpeg', 'WEBP': 'image/webp'}[image.format]
                image.verify()
        except (ValueError, binascii.Error, OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
            raise StoreError('工作档案图像无法读取。') from exc
        digest = hashlib.sha256(raw).hexdigest()
        target = self.images / digest
        if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            name = None
            try:
                with tempfile.NamedTemporaryFile(dir=self.images, delete=False) as file:
                    name = file.name
                    file.write(raw)
                    file.flush()
                    os.fsync(file.fileno())
                os.replace(name, target)
            finally:
                if name and Path(name).exists():
                    Path(name).unlink()
        return {'sha256': digest, 'mime': mime, 'byte_length': len(raw), 'width': width, 'height': height}

    def save(self, project, title='', case_id=None, expected_version=None, kind='manual', citations=()):
        if not isinstance(project, dict) or type(project.get('version')) is not int or project.get('version') not in (1, 2, 3):
            raise StoreError('无法识别工作文件版本。')
        if (not isinstance(project.get('regions'), list) or len(project['regions']) > 3
                or not isinstance(project.get('recommendations'), list) or len(project['recommendations']) > 2):
            raise StoreError('工作档案最多包含 3 个区域与 2 条建议。')
        if not isinstance(title, str) or len(title.strip()) > 80:
            raise StoreError('档案名称请控制在 80 字以内。')
        if kind not in ('manual', 'autosave'):
            raise StoreError('保存方式无效。')
        if case_id is not None:
            self._id(case_id)
            if type(expected_version) is not int or expected_version < 1:
                raise StoreError('请提供打开档案时的版本号。')
        snapshot = {key: value for key, value in project.items() if key in PROJECT_FIELDS}
        assets = {}
        for role in ('image', 'mask', 'restored'):
            value = snapshot.get(role)
            if role == 'image' or value:
                assets[role] = self._asset(value)
                snapshot[role] = {'asset_sha256': assets[role]['sha256']}
        if 'restored' in assets and 'mask' not in assets:
            raise StoreError('修复结果缺少对应掩膜。')
        original = assets['image']
        if any((a['width'], a['height']) != (original['width'], original['height']) for a in assets.values()):
            raise StoreError('原图、掩膜与修复结果的尺寸不一致。')
        encoded = _json(snapshot)
        if len(encoded.encode('utf-8')) > 16 * 1024 * 1024:
            raise StoreError('档案文字与过程记录过大，请先导出归档。')
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        title = title.strip() or '未命名壁画档案'
        with closing(self.connect()) as con:
            try:
                con.execute('BEGIN IMMEDIATE')
                if case_id:
                    case = con.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
                    if not case:
                        raise StoreError('档案不存在。', 404)
                    if case['current_version'] != expected_version:
                        raise StoreError('此档案已在其他页面保存。请重新打开，或另存为新档案。', 409)
                    latest = con.execute('SELECT checksum FROM case_versions WHERE case_id=? AND version=?',
                                         (case_id, expected_version)).fetchone()
                    if latest['checksum'] == digest and case['title'] == title:
                        con.rollback()
                        return dict(case, unchanged=True)
                    version = expected_version + 1
                else:
                    case_id, version = uuid.uuid4().hex, 1
                    con.execute('INSERT INTO cases VALUES (?,?,?,?,?)', (case_id, title, 0, now, now))
                cursor = con.execute('INSERT INTO case_versions(case_id,version,project_json,checksum,kind,created_at) VALUES (?,?,?,?,?,?)',
                                     (case_id, version, encoded, digest, kind, now))
                version_id = cursor.lastrowid
                for role, asset in assets.items():
                    con.execute('INSERT OR IGNORE INTO assets VALUES (?,?,?,?,?)',
                                tuple(asset[k] for k in ('sha256', 'mime', 'byte_length', 'width', 'height')))
                    con.execute('INSERT INTO version_assets VALUES (?,?,?)', (version_id, role, asset['sha256']))
                for index, source in citations:
                    source_json = _json(source)
                    con.execute('INSERT INTO reference_sources VALUES (?,?) ON CONFLICT(id) DO UPDATE SET source_json=excluded.source_json',
                                (source['id'], source_json))
                    con.execute('INSERT INTO recommendation_citations VALUES (?,?,?,?)',
                                (version_id, index, source['id'], source_json))
                con.execute('UPDATE cases SET title=?,current_version=?,updated_at=? WHERE id=?',
                            (title, version, now, case_id))
                con.commit()
            except Exception:
                con.rollback()
                raise
        return {'id': case_id, 'title': title, 'current_version': version, 'updated_at': now, 'unchanged': False}

    def list_cases(self):
        with closing(self.connect()) as con:
            return [dict(row) for row in con.execute('SELECT * FROM cases ORDER BY updated_at DESC LIMIT 100')]

    def versions(self, case_id):
        self._id(case_id)
        with closing(self.connect()) as con:
            rows = con.execute('SELECT version,kind,created_at,checksum FROM case_versions WHERE case_id=? ORDER BY version DESC', (case_id,)).fetchall()
            if not rows:
                raise StoreError('档案不存在。', 404)
            return [dict(row) for row in rows]

    def read(self, case_id, version=None):
        self._id(case_id)
        with closing(self.connect()) as con:
            case = con.execute('SELECT * FROM cases WHERE id=?', (case_id,)).fetchone()
            if not case:
                raise StoreError('档案不存在。', 404)
            number = case['current_version'] if version is None else version
            if type(number) is not int or number < 1:
                raise StoreError('档案版本号无效。')
            row = con.execute('SELECT * FROM case_versions WHERE case_id=? AND version=?', (case_id, number)).fetchone()
            if not row:
                raise StoreError('档案版本不存在。', 404)
            project = json.loads(row['project_json'])
            for asset in con.execute('SELECT role,a.* FROM version_assets va JOIN assets a ON a.sha256=va.sha256 WHERE version_id=?', (row['id'],)):
                try:
                    raw = (self.images / asset['sha256']).read_bytes()
                except OSError as exc:
                    raise StoreError('档案图像文件缺失，请从备份工作文件恢复。', 409) from exc
                if hashlib.sha256(raw).hexdigest() != asset['sha256']:
                    raise StoreError('档案图像校验失败，请从备份恢复。', 409)
                project[asset['role']] = 'data:' + asset['mime'] + ';base64,' + base64.b64encode(raw).decode()
            return {'case': dict(case), 'version': number, 'project': project,
                    'citations': [dict(r, source=json.loads(r['snapshot_json'])) for r in con.execute(
                        'SELECT advice_index,source_id,snapshot_json FROM recommendation_citations WHERE version_id=?', (row['id'],))]}
