from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.audit_arabizi_excellence_gates import audit  # noqa: E402
from scripts.evaluate_arabizi_pair_coverage import evaluate  # noqa: E402


class ArabiziNextPhaseGateTests(unittest.TestCase):
    def test_excellence_audit_is_honest_about_not_final_ready_yet(self) -> None:
        result = audit()
        self.assertEqual(result["summary"]["readiness"], "NOT_READY_FOR_FINAL_ARABIZI_CLAIM")
        self.assertGreaterEqual(result["summary"]["gate_pass_count"], 1)
        gate_ids = {gate["gate_id"] for gate in result["gates"]}
        self.assertEqual(gate_ids, {"ARZ-G01", "ARZ-G02", "ARZ-G03", "ARZ-G04", "ARZ-G05", "ARZ-G06"})
        self.assertIn("Batch 002", result["next_actions_ranked"][0])

    def test_pair_coverage_reports_arabizi_involving_pairs(self) -> None:
        result = evaluate()
        summary = result["summary"]
        self.assertGreater(summary["arabizi_pair_count"], 0)
        self.assertGreater(summary["cross_language_duplicate_count"], 0)
        self.assertIn("arabizi-en", result["language_pair_breakdown"])
        self.assertIn("ar-arabizi", result["language_pair_breakdown"])


if __name__ == "__main__":
    unittest.main()
