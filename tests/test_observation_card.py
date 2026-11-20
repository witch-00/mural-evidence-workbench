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
                "follow_up": "核对更清晰的原图", "include_note": True,
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
        for text in ("R3", original["ai_observation"], "本图无法判断",
                     *(v for k, v in original["evidence"].items() if k not in ("decision", "include_note"))):
            self.assertIn(text, content)

    def test_missing_evidence_identifies_affected_region(self):
        evidence = self.doc["regions"][0]["evidence"]
        for field in ("reference", "reason", "decision"):
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

    def test_card_uses_song_font_and_distinguishes_record_from_verification(self):
        response = self.export()
        page = PdfReader(io.BytesIO(response.data)).pages[0]
        text = page.extract_text()
        for label in ("观察与分歧", "依据与复核", "建议行动", "风险与限制", "人工复核范围"):
            self.assertIn(label, text)
        self.assertNotIn("标注：AI 初稿＝", text)
        self.assertNotIn("已人工复核", text)
        self.assertNotIn("待核", text)
        fonts = page["/Resources"]["/Font"].get_object().values()
        self.assertTrue(any("Serif" in str(font.get_object().get("/BaseFont")) for font in fonts))

    def test_personal_opinion_cannot_be_exported_as_adopted_observation(self):
        self.doc["evidence_version"] = 2
        evidence = self.doc["regions"][0]["evidence"]
        evidence.update(source_type="opinion", decision="adopt", reason_code="visible", reference="我认为没问题")
        response = self.export()
        self.assertEqual(response.status_code, 400)
        self.assertIn("R1", response.get_json()["error"])
        evidence.update(decision="insufficient", reason_code="cause")
        response = self.export()
        self.assertEqual(response.status_code, 200, response.get_json(silent=True))
        text = PdfReader(io.BytesIO(response.data)).pages[0].extract_text()
        self.assertIn("无直接依据", text)
        self.assertIn("本图无法判断", text)
        self.assertNotIn("待核", text)

    def test_new_records_require_classified_evidence_and_registered_reference(self):
        self.doc["evidence_version"] = 2
        evidence = self.doc["regions"][0]["evidence"]
        evidence["reason_code"] = "cause"
        self.assertEqual(self.export().status_code, 400)
        evidence["source_type"] = "reference"
        self.assertEqual(self.export().status_code, 400)
        self.doc["references"] = "《测试资料》第 2 页，纹样右缘照片"
        self.assertEqual(self.export().status_code, 200)
        evidence["source_type"] = "image"
        self.doc["references"] = ""
        self.assertEqual(self.export().status_code, 200)

    def test_unsupported_human_revision_is_not_printed_as_observed_fact(self):
        self.doc["evidence_version"] = 2
        region = self.doc["regions"][0]
        region["observation"] = "人工随意填写的推断不能直接作为观察结论"
        region["evidence"].update(decision="reject", source_type="image", reason_code="overstated")
        response = self.export()
        self.assertEqual(response.status_code, 200)
        text = PdfReader(io.BytesIO(response.data)).pages[0].extract_text()
        self.assertIn("AI 原文（未采纳）", text)
        self.assertNotIn(region["observation"], text)

    def test_decision_requires_matching_reason_and_real_text_revision(self):
        self.doc["evidence_version"] = 2
        region = self.doc["regions"][0]
        region["evidence"].update(source_type="image", decision="adopt", reason_code="cause")
        self.assertEqual(self.export().status_code, 400)
        region["evidence"].update(decision="revise", reason_code="overstated")
        region["observation"] = region["ai_observation"]
        self.assertEqual(self.export().status_code, 400)

    def test_insufficient_is_a_completed_conclusion_without_future_reviewer(self):
        self.doc["evidence_version"] = 2
        self.doc["regions"][0]["evidence"] = {
            "source_type": "image", "decision": "insufficient", "reason_code": "resolution"
        }
        self.assertEqual(self.export().status_code, 200)

    def test_free_text_notes_are_excluded_unless_explicitly_selected(self):
        self.doc["evidence_version"] = 2
        evidence = self.doc["regions"][0]["evidence"]
        evidence.update(source_type="image", decision="insufficient", reason_code="cause",
                        reason="这是一段仅供工作中保留的个人意见", include_note=False)
        response = self.export()
        text = PdfReader(io.BytesIO(response.data)).pages[0].extract_text()
        self.assertNotIn(evidence["reason"], text)
        evidence["include_note"] = True
        text = PdfReader(io.BytesIO(self.export().data)).pages[0].extract_text()
        self.assertIn(evidence["reason"], text)
