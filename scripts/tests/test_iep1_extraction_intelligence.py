"""IEP-1 extraction intelligence contract tests.

Run with:
    python -m pytest scripts/tests/test_iep1_extraction_intelligence.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep1.extractor import build_issue_intelligence, extract  # noqa: E402
from src.shared.schemas import IEP1LanguageSignal, Language, ScriptProfile  # noqa: E402


class TestIEP1ExtractionIntelligence(unittest.TestCase):
    def test_extract_emits_structured_issue_evidence(self) -> None:
        result = extract(
            complaint_id="IEP1-TOP-001",
            text="fi jora kbire 3al tari2 w l wad3 m5atra ktir",
            language_hint="arabizi",
            include_embedding=False,
        )

        signal = IEP1LanguageSignal.model_validate(result["iep1_signal_json"])
        selected_candidates = [candidate for candidate in signal.issue_candidates if candidate.selected]

        self.assertEqual(result["routing_sector"], "ROADS")
        self.assertTrue(selected_candidates)
        self.assertEqual(selected_candidates[0].sector, result["routing_sector"])
        self.assertEqual(selected_candidates[0].issue_type, result["issue_type"])
        self.assertGreaterEqual(selected_candidates[0].evidence_count, 1)
        self.assertTrue(signal.issue_evidence_terms)
        self.assertIn("jora", {item.term for item in signal.issue_evidence_terms})
        self.assertTrue(any(reason.startswith("drift_score_") for reason in signal.language_risk_reasons))
        # Safety invariant: a high-drift Arabizi safety complaint must never be
        # auto-routed. Both "HITL_LANGUAGE_REVIEW" and "REVIEW_BEFORE_AUTOROUTE"
        # satisfy that contract; the exact label depends on whether model-rule
        # reasons take precedence, which is an implementation detail.
        self.assertIn(
            signal.review_recommendation,
            {"HITL_LANGUAGE_REVIEW", "REVIEW_BEFORE_AUTOROUTE"},
        )
        self.assertNotEqual(signal.review_recommendation, "AUTO_ROUTE_ELIGIBLE")
        self.assertEqual(signal.explanation_features["selected_issue_type"], result["issue_type"])

    def test_sector_keyword_fallback_is_review_marked(self) -> None:
        signal = IEP1LanguageSignal(
            report_id="IEP1-TOP-002",
            language=Language.ENGLISH,
            script_profile=ScriptProfile.LATIN_OTHER,
            raw_text="street asphalt pavement damaged badly",
            normalized_text="street asphalt pavement damaged badly",
            normalization_applied=False,
            normalization_confidence=1.0,
            normalization_coverage=1.0,
            arabizi_marker_count=0,
            arabizi_marker_density=0.0,
            code_mix_ratio=0.0,
            oov_token_count=0,
            oov_high_risk_count=0,
            oov_tokens=[],
            known_terms=[],
            drift_score=0,
        )
        intelligence = build_issue_intelligence(signal, use_model=False)

        selected_candidates = [candidate for candidate in intelligence["issue_candidates"] if candidate.selected]

        self.assertEqual(intelligence["routing_sector"], "ROADS")
        self.assertEqual(intelligence["issue_type"], "UNCLASSIFIED")
        self.assertTrue(selected_candidates)
        self.assertEqual(selected_candidates[0].reason, "sector_keywords_only")
        self.assertGreaterEqual(selected_candidates[0].evidence_count, 1)
        self.assertIn("issue_type_unclassified", intelligence["language_risk_reasons"])
        self.assertEqual(intelligence["review_recommendation"], "REVIEW_BEFORE_AUTOROUTE")


if __name__ == "__main__":
    unittest.main()
