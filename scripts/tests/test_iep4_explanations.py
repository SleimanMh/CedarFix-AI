"""IEP-4 explanation contract tests.

Validates that the IEP-4 explainer module produces structurally correct
bilingual outputs for all routing sectors.

Run with:
    python -m pytest scripts/tests/test_iep4_explanations.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep4.explainer import explain  # noqa: E402

SECTORS = ["ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY", "TELECOM", "OTHER"]


class TestExplainerOutputSchema(unittest.TestCase):
    def _explain(self, sector, hitl=False):
        return explain(
            complaint_id="TEST-001",
            routing_sector=sector,
            routing_entity="MUN",
            routing_confidence=0.78,
            priority_score=65.0,
            issue_type="test_issue",
            gps_lat=33.8886,
            gps_lon=35.4955,
            hitl_required=hitl,
        )

    def test_all_sectors_produce_both_explanations(self) -> None:
        for sector in SECTORS:
            with self.subTest(sector=sector):
                result = self._explain(sector)
                self.assertIn("citizen_explanation", result)
                self.assertIn("admin_explanation", result)
                self.assertIn("iep4_explanation_json", result)
                self.assertTrue(result["citizen_explanation"].strip())
                self.assertTrue(result["admin_explanation"].strip())

    def test_citizen_explanation_is_non_empty(self) -> None:
        result = self._explain("ROADS")
        self.assertGreater(len(result["citizen_explanation"]), 10)

    def test_admin_explanation_contains_entity(self) -> None:
        result = explain(
            complaint_id="TEST-002",
            routing_sector="ROADS",
            routing_entity="MPWT",
            routing_confidence=0.85,
            priority_score=60.0,
            issue_type="pothole",
            gps_lat=33.8886,
            gps_lon=35.4955,
            hitl_required=False,
        )
        self.assertIn("MPWT", result["admin_explanation"])

    def test_hitl_flag_appears_in_admin_explanation(self) -> None:
        result = self._explain("ELECTRICITY", hitl=True)
        self.assertIn("HITL", result["admin_explanation"])

    def test_safety_always_contains_hitl_marker(self) -> None:
        result = self._explain("SAFETY", hitl=True)
        self.assertIn("HITL", result["admin_explanation"])

    def test_no_internal_codes_leaked_to_citizen(self) -> None:
        """Citizen explanation must not contain internal routing codes or scores."""
        for sector in SECTORS:
            with self.subTest(sector=sector):
                result = self._explain(sector)
                # Confidence scores like 0.78 should not appear in citizen text
                self.assertNotIn("0.78", result["citizen_explanation"])
                self.assertNotIn("MUN", result["citizen_explanation"])

    def test_other_sector_produces_generic_message(self) -> None:
        result = self._explain("OTHER")
        self.assertTrue(result["citizen_explanation"].strip())
        self.assertIn("reviewer", result["admin_explanation"].lower())

    def test_telecom_routes_to_ogero(self) -> None:
        result = explain(
            complaint_id="TEST-003",
            routing_sector="TELECOM",
            routing_entity="OGERO",
            routing_confidence=0.59,
            priority_score=55.0,
            issue_type="dsl_outage",
            gps_lat=None,
            gps_lon=None,
            hitl_required=True,
        )
        self.assertIn("OGERO", result["admin_explanation"])
        self.assertIn("HITL", result["admin_explanation"])

    def test_gps_not_provided_gracefully(self) -> None:
        result = explain(
            complaint_id="TEST-004",
            routing_sector="WASTE",
            routing_entity="MUN",
            routing_confidence=0.80,
            priority_score=55.0,
            issue_type="uncollected_waste",
            gps_lat=None,
            gps_lon=None,
            hitl_required=False,
        )
        self.assertIn("not provided", result["admin_explanation"])

    def test_priority_score_appears_in_admin(self) -> None:
        result = explain(
            complaint_id="TEST-005",
            routing_sector="FLOODING",
            routing_entity="CD",
            routing_confidence=0.77,
            priority_score=80.0,
            issue_type="flash_flood",
            gps_lat=33.888,
            gps_lon=35.496,
            hitl_required=False,
        )
        self.assertIn("80", result["admin_explanation"])

    def test_audit_packet_records_guardrails(self) -> None:
        result = explain(
            complaint_id="TEST-006",
            routing_sector="ROADS",
            routing_entity="MPWT",
            routing_confidence=0.85,
            priority_score=60.0,
            issue_type="pothole",
            gps_lat=33.8886,
            gps_lon=35.4955,
            hitl_required=False,
            language="en",
        )
        audit = result["iep4_explanation_json"]
        self.assertEqual(audit["stage"], "iep4")
        self.assertTrue(audit["guardrails"]["citizen_hides_internal_codes"])
        self.assertTrue(audit["guardrails"]["no_repair_timeline_promised"])


if __name__ == "__main__":
    unittest.main()
