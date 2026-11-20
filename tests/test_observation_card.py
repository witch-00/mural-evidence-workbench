"""Run with the integrated workbench directory on PYTHONPATH."""
import base64
import io
import unittest

from PIL import Image
from pypdf import PdfReader

from app import app


class ObservationCardTest(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        sample = io.BytesIO()
        Image.new("RGB", (48, 32), "tan").save(sample, "PNG")
        region = {
            "id": "R1", "x": .1, "y": .1, "w": .4, "h": .4,
            "observation": "纹样右缘有一条细线", "origin": "edited",
            "ai_observation": "疑似裂隙",
            "evidence": {
                "decision": "暂缓判断", "reference": "原图右缘",
                "alternative": "可能是笔线", "reason": "线条紧贴纹样",
                "follow_up": "核对更清晰的原图",
            },
        }
        self.doc = {
            "evidence_version": 1,
            "image": "data:image/png;base64," + base64.b64encode(sample.getvalue()).decode(),
            "source": "程序生成的练习图", "reviewed": True, "regions": [region],
            "recommendations": [{
                "target": "R1", "action": "暂时保留", "basis": "边缘连续", "risk": "错把笔线判作裂隙"
            }],
            "uncertainty": "需要复核", "model_label": "测试用初稿",
        }

    def export(self):
        return self.client.post("/api/report/observation", json=self.doc)

    def test_three_regions_keep_disagreement_and_sources_on_one_page(self):
        original = self.doc["regions"][0]
        self.doc["regions"] += [dict(original, id="R2", x=.2), dict(original, id="R3", x=.3)]
        response = self.export()
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        pages = PdfReader(io.BytesIO(response.data)).pages
        self.assertEqual(len(pages), 1)
        content = pages[0].extract_text()
        for text in ("R3", original["ai_observation"], *original["evidence"].values()):
            self.assertIn(text, content)

    def test_missing_evidence_or_followup_identifies_affected_region(self):
        evidence = self.doc["regions"][0]["evidence"]
        for field in ("reference", "reason", "decision", "follow_up"):
            with self.subTest(field=field):
                old = evidence.pop(field)
                response = self.export()
                self.assertEqual(response.status_code, 400)
                self.assertIn("R1", response.get_json()["error"])
                evidence[field] = old

    def test_legacy_request_remains_readable(self):
        self.doc.pop("evidence_version")
        self.doc["regions"][0].pop("evidence")
        self.assertEqual(self.export().status_code, 200)
