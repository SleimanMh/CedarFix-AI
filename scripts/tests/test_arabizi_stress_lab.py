from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.run_arabizi_stress_lab import run_stress_lab  # noqa: E402


class ArabiziStressLabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = run_stress_lab()

    def test_stress_lab_has_demo_scale_and_coverage(self) -> None:
        self.assertGreaterEqual(self.result["meta"]["scenario_count"], 6)
        self.assertGreaterEqual(self.result["meta"]["variant_count"], 24)
        for scenario_id in (
            "STRESS-ROADS-POTHOLE",
            "STRESS-ELECTRICITY-TRANSFORMER",
            "STRESS-WATER-SEWAGE",
            "STRESS-SAFETY-FIRE",
            "STRESS-WASTE-COLLECTION",
            "STRESS-FLOODING-DRAIN",
        ):
            self.assertIn(scenario_id, self.result["scenario_summary"], msg=f"Missing {scenario_id}")

    def test_stress_lab_sector_coverage_is_complete(self) -> None:
        cov = self.result["sector_coverage"]
        self.assertIn("coverage_rate", cov)
        self.assertIn("exercised_sectors", cov)
        self.assertIn("missing_sectors", cov)
        self.assertEqual(cov["missing_sectors"], [], msg="Stress lab must cover all 6 canonical sectors")
        gates = self.result["acceptance_gates"]
        self.assertGreaterEqual(cov["coverage_rate"], gates["requires_sector_coverage_rate"])

    def test_stress_lab_meets_stability_gates(self) -> None:
        gates = self.result["acceptance_gates"]
        summary = self.result["summary"]
        self.assertGreaterEqual(summary["stable_sector_rate"], gates["min_stable_sector_rate"])
        self.assertGreaterEqual(summary["acceptable_decision_rate"], gates["min_acceptable_decision_rate"])
        self.assertGreaterEqual(summary["stable_issue_rate"], gates["min_strict_issue_rate_observed"])
        self.assertEqual(summary["unacceptable_count"], 0)

    def test_stress_lab_exercises_uncertainty_and_hitl(self) -> None:
        gates = self.result["acceptance_gates"]
        summary = self.result["summary"]
        hitl_count = round(summary["hitl_rate"] * self.result["meta"]["variant_count"])
        self.assertGreaterEqual(hitl_count, gates["requires_hitl_variant_count_at_least"])
        self.assertGreaterEqual(
            summary["oov_or_noise_variant_count"],
            gates["requires_oov_or_noise_variant_count_at_least"],
        )

    def test_each_variant_exposes_professor_visible_evidence(self) -> None:
        required_keys = {
            "variant_id",
            "raw_text",
            "predicted_sector",
            "predicted_issue_type",
            "issue_confidence",
            "acceptable_decision",
            "force_hitl",
            "drift_score",
            "normalization_coverage",
            "oov_tokens",
            "known_terms",
        }
        for row in self.result["variants"]:
            with self.subTest(variant=row["variant_id"]):
                self.assertTrue(required_keys <= row.keys())
                self.assertGreaterEqual(row["drift_score"], 0)
                self.assertLessEqual(row["drift_score"], 3)
                self.assertGreaterEqual(row["normalization_coverage"], 0.0)
                self.assertLessEqual(row["normalization_coverage"], 1.0)


if __name__ == "__main__":
    unittest.main()
