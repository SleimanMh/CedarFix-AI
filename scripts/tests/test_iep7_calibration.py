"""IEP-7 calibration math tests (ECE / Brier / reliability bins).

Run with:
    python -m pytest scripts/tests/test_iep7_calibration.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.iep7.calibration import build_report  # noqa: E402
from src.shared.calibration_schemas import (  # noqa: E402
    brier_score,
    expected_calibration_error,
    reliability_bins,
)


class TestECE(unittest.TestCase):
    def test_perfect_calibration_zero_ece(self) -> None:
        # Confidence equals empirical accuracy in every bin -> ECE 0.
        confidences = [0.05] * 100 + [0.95] * 100
        correct = [0] * 95 + [1] * 5 + [1] * 95 + [0] * 5
        ece = expected_calibration_error(confidences, correct, n_bins=10)
        self.assertLess(ece, 0.02)

    def test_overconfident_has_positive_ece(self) -> None:
        # Always says 0.99 but only right half the time.
        confidences = [0.99] * 100
        correct = [1, 0] * 50
        ece = expected_calibration_error(confidences, correct, n_bins=10)
        self.assertGreater(ece, 0.4)

    def test_empty_inputs(self) -> None:
        self.assertEqual(expected_calibration_error([], []), 0.0)
        self.assertEqual(brier_score([], []), 0.0)


class TestBrier(unittest.TestCase):
    def test_brier_perfect(self) -> None:
        self.assertAlmostEqual(brier_score([1.0, 0.0], [1, 0]), 0.0)

    def test_brier_worst(self) -> None:
        self.assertAlmostEqual(brier_score([0.0, 1.0], [1, 0]), 1.0)

    def test_length_mismatch_raises(self) -> None:
        with self.assertRaises(ValueError):
            brier_score([0.5], [1, 0])


class TestBinsAndReport(unittest.TestCase):
    def test_bins_cover_unit_interval(self) -> None:
        bins = reliability_bins([0.1, 0.5, 0.95], [0, 1, 1], n_bins=10)
        self.assertEqual(len(bins), 10)
        total = sum(b.count for b in bins)
        self.assertEqual(total, 3)

    def test_build_report_fields(self) -> None:
        confidences = [0.8] * 10
        correct = [1] * 8 + [0] * 2
        report = build_report("ROADS", confidences, correct)
        self.assertEqual(report.sector, "ROADS")
        self.assertEqual(report.n, 10)
        self.assertAlmostEqual(report.accuracy, 0.8)
        self.assertAlmostEqual(report.mean_confidence, 0.8)
        self.assertGreaterEqual(report.ece, 0.0)
        self.assertGreaterEqual(report.brier, 0.0)


if __name__ == "__main__":
    unittest.main()
