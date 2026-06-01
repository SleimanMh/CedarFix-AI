"""IEP-3 routing intelligence contract tests.

Run with:
    python -m pytest scripts/tests/test_iep3_routing_intelligence.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep3.router import route  # noqa: E402
from src.iep3.worker import _build_routing_intelligence  # noqa: E402
from src.shared.schemas import RoutingDecisionEvidence  # noqa: E402


class TestIEP3RoutingIntelligence(unittest.TestCase):
    def test_legacy_route_packet_marks_auto_route_eligibility(self) -> None:
        decision = route(
            complaint_id="R-001",
            routing_sector="ROADS",
            issue_type="road_pothole",
            issue_type_confidence=0.86,
            drift_score=0,
            gps_lat=33.8886,
            gps_lon=35.4955,
        )
        packet = RoutingDecisionEvidence.model_validate(
            _build_routing_intelligence(
                "R-001",
                decision,
                issue_type="road_pothole",
                issue_type_confidence=0.86,
                hitl_required=decision["hitl_required"],
                hitl_reason=decision.get("hitl_reason"),
            )
        )

        self.assertEqual(packet.router_version, "sector_agency_map")
        self.assertEqual(packet.routing_sector, "ROADS")
        self.assertTrue(packet.auto_route_eligible)
        self.assertEqual(packet.issue_type, "road_pothole")

    def test_kb_packet_preserves_rule_location_and_hitl_codes(self) -> None:
        decision = {
            "routing_sector": "WATER",
            "routing_entity": "HITL",
            "routing_confidence": 0.45,
            "priority_score": 65.0,
            "hitl_required": True,
            "hitl_reason": "kb:missing_location,routing_rule_hitl",
            "shap_top3": {
                "router_version": "route_complaint_kb",
                "kb_route_reason": "sector=WATER | type=water_outage_area",
                "kb_complaint_type_id": "CT-WATER-001",
                "kb_complaint_type": "water_outage_area",
                "kb_primary_entity_raw": "RWA_DYNAMIC",
                "kb_secondary_entity": "MUN",
                "kb_location_method": "not_found",
                "kb_municipality_id": None,
                "kb_municipality_name": "",
                "kb_warnings": ["HITL_GATE: no location found in text"],
            },
        }
        packet = RoutingDecisionEvidence.model_validate(
            _build_routing_intelligence(
                "R-002",
                decision,
                issue_type="water_outage_area",
                issue_type_confidence=0.81,
                hitl_required=True,
                hitl_reason=decision["hitl_reason"],
            )
        )

        self.assertEqual(packet.router_version, "route_complaint_kb")
        self.assertFalse(packet.auto_route_eligible)
        self.assertIn("missing_location", packet.hitl_reason_codes)
        self.assertEqual(packet.kb_complaint_type_id, "CT-WATER-001")
        self.assertEqual(packet.kb_location_method, "not_found")


if __name__ == "__main__":
    unittest.main()