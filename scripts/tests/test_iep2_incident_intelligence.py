"""IEP-2 incident intelligence contract tests.

Run with:
    python -m pytest scripts/tests/test_iep2_incident_intelligence.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep2.dedup import build_incident_intelligence, classify_pair  # noqa: E402
from src.shared.schemas import IncidentIntelligence  # noqa: E402


class TestIEP2IncidentIntelligence(unittest.TestCase):
    def test_semantic_duplicate_emits_cluster_packet(self) -> None:
        candidates = [
            {
                "complaint_id": "C-001",
                "incident_id": "INC-001",
                "text_embedding_ref": [1.0, 0.0, 0.0],
                "gps_lat": 33.8886,
                "gps_lon": 35.4955,
                "issue_type": "road_pothole",
            }
        ]

        decision = classify_pair(
            complaint_id="C-002",
            embedding_ref=[0.99, 0.01, 0.0],
            lat=33.8887,
            lon=35.4956,
            issue_type="road_pothole",
            candidates=candidates,
        )
        intelligence = IncidentIntelligence.model_validate(
            build_incident_intelligence("C-002", decision, candidates)
        )

        self.assertTrue(decision["is_duplicate"])
        self.assertEqual(intelligence.incident_id, "INC-001")
        self.assertEqual(intelligence.matched_complaint_id, "C-001")
        self.assertEqual(intelligence.cluster_size, 2)
        self.assertEqual(intelligence.incident_lifecycle_state, "EMERGING")
        self.assertEqual(intelligence.review_recommendation, "AUTO_ATTACH_TO_INCIDENT")
        self.assertEqual(intelligence.match_evidence.embedding_comparison_count, 1)

    def test_geo_only_nearby_case_requires_review(self) -> None:
        candidates = [
            {
                "complaint_id": "C-010",
                "incident_id": "INC-010",
                "text_embedding_ref": None,
                "gps_lat": 33.8886,
                "gps_lon": 35.4955,
                "issue_type": "water_outage",
            }
        ]

        decision = classify_pair(
            complaint_id="C-011",
            embedding_ref=None,
            lat=33.8887,
            lon=35.4956,
            issue_type="water_outage",
            candidates=candidates,
        )
        intelligence = IncidentIntelligence.model_validate(
            build_incident_intelligence("C-011", decision, candidates)
        )

        self.assertFalse(decision["is_duplicate"])
        self.assertEqual(intelligence.incident_lifecycle_state, "NEARBY_REVIEW")
        self.assertEqual(intelligence.review_recommendation, "HITL_REVIEW_NEARBY_REPORT")
        self.assertEqual(intelligence.match_evidence.candidates_within_radius, 1)


if __name__ == "__main__":
    unittest.main()