import json
import unittest
from datetime import date
from unittest import mock

import importlib

# agents/__init__ re-exports a function named inspection_agent, which shadows
# the module on attribute access, so load the module itself.
inspection = importlib.import_module("agents.inspection_agent")
from agents.document_checks import check_fields, names_match
from agents.government_id_agent import GOVERNMENT_ID_SYSTEM_PROMPT
from agents.stage_documents import (
    BARANGAY_CLEARANCE, DTI_CERTIFICATE, FIRE_CERTIFICATE, MAYORS_PERMIT,
    SANITARY_PERMIT, ZONING_CLEARANCE, annotate_roadmap, stage_kind, stage_outputs,
)

ROADMAP = [
    {"step_number": 1, "title": "DTI Business Name Registration",
     "requirements": ["Valid government ID", "Proposed business names (3 options)"]},
    {"step_number": 2, "title": "Barangay Business Clearance",
     "requirements": ["DTI Certificate", "Lease contract"]},
]
PROFILE = {"business_name": "Manila Artisanal Cafe"}


class StageDocumentTests(unittest.TestCase):
    def test_each_stage_knows_its_document(self):
        self.assertEqual(stage_outputs(ROADMAP[0]), [DTI_CERTIFICATE])
        self.assertEqual(stage_outputs(ROADMAP[1]), [BARANGAY_CLEARANCE])
        self.assertEqual(stage_outputs({"title": "Mayor's Permit / Business Permit"}), [MAYORS_PERMIT])
        self.assertEqual(
            stage_outputs({"title": "Line Bureau Permits (Manila Health Department & BFP)"}),
            [SANITARY_PERMIT, FIRE_CERTIFICATE])
        self.assertEqual(stage_outputs({"title": "Zoning Clearance & Occupancy Permit"})[0],
                         ZONING_CLEARANCE)

    def test_mayors_permit_listing_barangay_is_still_mayors(self):
        step = {"title": "Mayor's Permit (BPLS Application)", "location": "Barangay Hall first"}
        self.assertEqual(stage_kind(step), "mayor")

    def test_roadmap_is_annotated_with_filing_mode(self):
        annotated = annotate_roadmap(ROADMAP)
        self.assertEqual(annotated[0]["filing"]["mode"], "both")
        self.assertEqual(annotated[1]["filing"]["mode"], "in_person")
        self.assertEqual(annotated[0]["outputs"], [DTI_CERTIFICATE])


class FieldCheckTests(unittest.TestCase):
    def test_names_match_ignores_case_accents_and_filler(self):
        self.assertTrue(names_match("MANILA ARTISANAL CAFÉ", "Manila Artisanal Cafe"))
        self.assertTrue(names_match("Manila Artisanal Cafe Shop", "Manila Artisanal Cafe"))
        self.assertFalse(names_match("JUAN'S BAKESHOP", "Manila Artisanal Cafe"))

    def test_wrong_business_name_fails(self):
        checks = check_fields({"business_name": "JUAN'S BAKESHOP"}, PROFILE)
        self.assertFalse(checks[0]["ok"])

    def test_expired_document_fails(self):
        checks = check_fields({"business_name": "Manila Artisanal Cafe", "expiry_date": "2020-01-01"},
                              PROFILE, today=date(2026, 10, 23))
        self.assertEqual([c["ok"] for c in checks], [True, False])

    def test_unreadable_name_is_reported_not_failed(self):
        self.assertIsNone(check_fields({}, PROFILE)[0]["ok"])


def fake_client(document, results):
    """A model that answers the inspection prompt with fixed findings."""
    client = mock.Mock()

    def invoke(prompt, system_prompt=None, **_):
        if system_prompt == GOVERNMENT_ID_SYSTEM_PROMPT:
            return {"content": json.dumps({"verdict": "not_government_id", "document_type": "x",
                                           "issuing_authority": "unknown", "confidence": "high",
                                           "reason": "Not an ID", "satisfies_requirement": False})}
        return {"content": json.dumps({"document": document, "results": results})}

    client.invoke_model.side_effect = invoke
    return client


def upload_state(step_number, text="some text", evidence=None):
    return {
        "roadmap": ROADMAP, "user_profile": PROFILE, "pending_step": step_number,
        "pending_document": {"name": "doc.png", "filename": "doc.png", "text": text,
                             "attachment": {"kind": "image", "media_type": "image/png", "data": "AA=="}},
        "documents": [], "stage_evidence": evidence or {},
    }


def run(state, client=None, configured=True):
    with mock.patch.object(inspection, "llm_is_configured", return_value=configured), \
         mock.patch.object(inspection, "get_llm_client", return_value=client):
        return inspection.inspection_agent(state)


class InspectionFlowTests(unittest.TestCase):
    def test_correct_certificate_passes_stage_one(self):
        client = fake_client({"business_name": "MANILA ARTISANAL CAFE"}, [
            {"document_name": DTI_CERTIFICATE, "status": "complete", "notes": "DTI certificate"},
            {"document_name": "Proposed business names (3 options)", "status": "missing", "notes": "-"},
        ])
        state = run(upload_state(1), client)
        self.assertTrue(state["stage_passed"])
        self.assertIn("looks like your", state["assistant_reply"])

    def test_certificate_for_another_business_fails(self):
        client = fake_client({"business_name": "JUAN'S BAKESHOP"}, [
            {"document_name": DTI_CERTIFICATE, "status": "complete", "notes": "DTI certificate"},
        ])
        state = run(upload_state(1), client)
        self.assertFalse(state["stage_passed"])
        out = next(r for r in state["verification"] if r["kind"] == "output")
        self.assertEqual(out["status"], "incomplete")
        self.assertIn("JUAN'S BAKESHOP", out["notes"])

    def test_evidence_accumulates_across_uploads(self):
        client = fake_client({}, [
            {"document_name": "Lease contract", "status": "complete", "notes": "Lease"},
        ])
        first = run(upload_state(2), client)
        self.assertFalse(first["stage_passed"])
        self.assertIn("Lease contract", first["stage_evidence"]["2"])

        client = fake_client({"business_name": "Manila Artisanal Cafe"}, [
            {"document_name": BARANGAY_CLEARANCE, "status": "complete", "notes": "Clearance"},
        ])
        second = run(upload_state(2, evidence=first["stage_evidence"]), client)
        self.assertTrue(second["stage_passed"])
        self.assertIn("Lease contract", second["stage_evidence"]["2"])

    def test_reworded_stage_document_still_counts(self):
        client = fake_client({"business_name": "Manila Artisanal Cafe"}, [
            {"document_name": "DTI Business Name Registration Certificate", "status": "complete",
             "notes": "DTI certificate"},
        ])
        state = run(upload_state(1), client)
        self.assertTrue(state["stage_passed"])

    def test_skipped_stage_document_is_reported(self):
        client = fake_client({}, [
            {"document_name": "Proposed business names (3 options)", "status": "missing", "notes": "-"},
        ])
        state = run(upload_state(1), client)
        out = next(r for r in state["verification"] if r["kind"] == "output")
        self.assertIn("didn't report", out["notes"])

    def test_keyword_fallback_never_passes(self):
        stuffed = "DTI Certificate of Business Name Registration Manila Artisanal Cafe"
        state = run(upload_state(1, text=stuffed), configured=False)
        self.assertFalse(state["stage_passed"])
        self.assertNotIn("complete", [r["status"] for r in state["verification"]])
        self.assertIn("unverified", [r["status"] for r in state["verification"]])


if __name__ == "__main__":
    unittest.main()
