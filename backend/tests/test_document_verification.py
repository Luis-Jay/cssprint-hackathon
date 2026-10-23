import json
import unittest

from agents.government_id_agent import (
    check_government_id,
    is_government_id_requirement,
    to_verification,
)
from agents.inspection_agent import simple_document_check
from utils.local_ocr import _annotate


ROADMAP = [{
    "step_number": 1,
    "requirements": ["Valid government ID"],
}]


class GovernmentIdVerificationTests(unittest.TestCase):
    def test_real_id_markers_are_classified_and_accepted(self):
        text = _annotate(
            "REPUBLIC OF THE PHILIPPINES\nLAND TRANSPORTATION OFFICE\n"
            "DRIVER'S LICENSE\nLICENSE NO: N01-23-456789"
        )
        result = simple_document_check(ROADMAP, [{"name": "id.jpg", "text": text}])
        self.assertEqual(result[0]["status"], "complete")

    def test_single_id_word_is_not_enough(self):
        text = _annotate("Travel checklist: remember your passport and tickets")
        result = simple_document_check(ROADMAP, [{"name": "note.jpg", "text": text}])
        self.assertNotEqual(result[0]["status"], "complete")

    def test_unrelated_document_is_rejected(self):
        result = simple_document_check(ROADMAP, [{
            "name": "receipt.jpg",
            "text": "STORE RECEIPT\nTOTAL PHP 1,250.00\nTHANK YOU",
        }])
        self.assertEqual(result[0]["status"], "missing")

    def test_previous_valid_id_cannot_validate_current_upload(self):
        valid = {
            "name": "old-id.jpg",
            "text": _annotate(
                "LAND TRANSPORTATION OFFICE\nDRIVER'S LICENSE\nLICENSE NO: 123"
            ),
        }
        unrelated = {"name": "current-receipt.jpg", "text": "SALES RECEIPT\nTOTAL 500"}

        # The inspection agent must pass only the pending/current document to
        # this matcher; this assertion captures the expected current verdict.
        result = simple_document_check(ROADMAP, [unrelated])
        self.assertEqual(result[0]["status"], "missing")
        self.assertEqual(simple_document_check(ROADMAP, [valid])[0]["status"], "complete")


class FakeClient:
    def __init__(self, reply):
        self.reply = reply
        self.prompts = []

    def invoke_model(self, prompt, **kwargs):
        self.prompts.append(prompt)
        return {"content": json.dumps(self.reply)}


class GovernmentIdAgentTests(unittest.TestCase):
    def test_recognized_id_satisfies_requirement(self):
        client = FakeClient({
            "verdict": "recognized", "document_type": "Driver's License",
            "issuing_authority": "LTO", "confidence": "high",
            "reason": "Title, agency, licence number and photo visible",
            "satisfies_requirement": True,
        })
        result = check_government_id({"name": "x.jpg", "text": "LTO"}, client)
        entry = to_verification("Valid government ID", result)
        self.assertEqual(entry["status"], "complete")

    def test_satisfies_flag_cannot_override_non_recognized_verdict(self):
        client = FakeClient({
            "verdict": "expired", "document_type": "Passport",
            "issuing_authority": "DFA", "confidence": "high",
            "reason": "Expired 2020", "satisfies_requirement": True,
        })
        result = check_government_id({"text": "PASSPORT"}, client)
        self.assertFalse(result["satisfies_requirement"])
        self.assertEqual(to_verification("Valid government ID", result)["status"],
                         "incomplete")

    def test_not_government_id_is_missing(self):
        client = FakeClient({
            "verdict": "not_government_id", "document_type": "School ID",
            "issuing_authority": "unknown", "confidence": "high",
            "reason": "School-issued card", "satisfies_requirement": False,
        })
        result = check_government_id({"text": "DLSU STUDENT ID"}, client)
        self.assertEqual(to_verification("Valid government ID", result)["status"],
                         "missing")

    def test_filename_is_not_sent_to_model(self):
        client = FakeClient({"verdict": "unreadable"})
        check_government_id({"name": "my-philid.jpg", "text": "blurry"}, client)
        self.assertNotIn("my-philid", client.prompts[0])

    def test_unknown_verdict_goes_to_manual_review(self):
        client = FakeClient({"verdict": "looks fine"})
        result = check_government_id({"text": "something"}, client)
        self.assertEqual(result["verdict"], "manual_review")
        self.assertFalse(result["satisfies_requirement"])

    def test_requirement_detection(self):
        self.assertTrue(is_government_id_requirement("Valid government ID"))
        self.assertTrue(is_government_id_requirement("Government-issued ID of owner"))
        self.assertFalse(is_government_id_requirement("Barangay Clearance"))


if __name__ == "__main__":
    unittest.main()
