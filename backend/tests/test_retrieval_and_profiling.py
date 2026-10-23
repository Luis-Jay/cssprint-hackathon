import unittest

from agents.profiling_agent import _next_question, missing_profile_fields
from agents.workflow import profile_is_complete
from rag.chunker import TextChunker
from rag.document_loader import Document, source_agency
from rag.ranking import BM25, detect_agencies, fuse, rerank


class SourceAgencyTests(unittest.TestCase):
    def test_sources_map_to_their_stage(self):
        self.assertEqual(source_agency("BIR_Citizens_Charter_Complete.pdf"), "bir")
        self.assertEqual(source_agency("DTI_BNRS_Business_Law_and_Rules.pdf"), "dti")
        self.assertEqual(source_agency("ORDINANCE-NO.-8331.pdf"), "mayors_permit")
        self.assertEqual(source_agency("1. ORDINANCE 8119 ZONING ORDINANCE (AS PUBLISHED).pdf"),
                         "zoning")
        self.assertEqual(source_agency("Master_Document_Checklist.json"), "general")

    def test_mislabelled_8331_json_is_zoning(self):
        # Its content is Ordinance 8341, the zoning amendment.
        self.assertEqual(source_agency("Manila_Ordinance_8331.json"), "zoning")


class QueryAgencyTests(unittest.TestCase):
    def test_detects_stage_in_english_and_tagalog(self):
        self.assertIn("bir", detect_agencies("Paano kumuha ng TIN?"))
        self.assertIn("dti", detect_agencies("register my business name"))
        self.assertIn("mayors_permit", detect_agencies("Saan kukuha ng mayor's permit?"))
        self.assertIn("mayors_permit", detect_agencies("sanitary permit for a carinderia"))
        self.assertIn("barangay", detect_agencies("barangay clearance fee"))

    def test_general_question_has_no_stage(self):
        self.assertEqual(detect_agencies("How long does the whole process take?"), set())


class RankingTests(unittest.TestCase):
    def test_bm25_prefers_exact_terms(self):
        bm25 = BM25(["fire safety inspection certificate", "petroleum dealer permit",
                     "sanitary permit for food establishments"])
        self.assertEqual(bm25.search("sanitary permit", 1), [2])

    def test_fuse_rewards_agreement(self):
        scores = fuse([[0, 1, 2], [2, 0, 3]])
        self.assertGreater(scores[0], scores[1])
        self.assertGreater(scores[2], scores[3])

    def test_off_topic_agency_is_demoted(self):
        sources = ["BIR_Citizens_Charter_Complete.pdf", "ORDINANCE-NO.-8331.pdf"]
        # BIR ranked first on raw score, but the question is about sanitary.
        picked = rerank({0: 1.0, 1: 0.6}, sources, {"mayors_permit"}, 2)
        self.assertEqual(picked[0], 1)

    def test_one_source_cannot_fill_every_slot(self):
        sources = ["BIR.pdf"] * 5 + ["Master_Document_Checklist.json"]
        scores = {i: 1.0 - i * 0.1 for i in range(6)}
        picked = rerank(scores, sources, set(), 4)
        self.assertEqual(sum(1 for i in picked if sources[i] == "BIR.pdf"), 2)
        self.assertIn(5, picked)

    def test_duplicate_chunks_are_dropped(self):
        chunks = [Document("Same  text", {}), Document("same text", {}),
                  Document("other", {})]
        self.assertEqual(len(TextChunker.dedupe(chunks)), 2)


class ProfilingTests(unittest.TestCase):
    def test_business_name_is_not_required(self):
        profile = {"business_type": "cafe", "location": "Sampaloc"}
        self.assertTrue(profile_is_complete(profile))
        self.assertEqual(missing_profile_fields(profile), [])

    def test_asks_for_everything_missing_in_one_message(self):
        question = _next_question({})
        self.assertIn("kind of business", question)
        self.assertIn("barangay", question)
        self.assertIn("food", question)
        self.assertNotIn("called", question)

    def test_does_not_ask_about_known_facts(self):
        question = _next_question({"business_type": "cafe", "serves_food": True,
                                   "is_homebased": False})
        self.assertNotIn("food", question)
        self.assertNotIn("home", question)

    def test_confirms_without_a_name(self):
        reply = _next_question({"business_type": "salon", "location": "Tondo"})
        self.assertIn("salon in Tondo", reply)


if __name__ == "__main__":
    unittest.main()
