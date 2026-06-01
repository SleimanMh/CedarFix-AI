"""IEP-7 calibration core.

Thin re-export of the pure ECE / Brier math (kept in shared so it is
unit-testable without importing the service), plus the per-sector report
builder used by the worker.
"""
from __future__ import annotations

from src.shared.calibration_schemas import (
    CalibrationBin,
    CalibrationReport,
    brier_score,
    expected_calibration_error,
    find_best_temperature,
    reliability_bins,
    temperature_scale_confidences,
)

__all__ = [
    "CalibrationBin",
    "CalibrationReport",
    "brier_score",
    "expected_calibration_error",
    "find_best_temperature",
    "reliability_bins",
    "temperature_scale_confidences",
    "build_report",
]


def build_report(
    sector: str,
    confidences: list[float],
    correct: list[int],
    n_bins: int = 10,
) -> CalibrationReport:
    """Assemble a full calibration report for one sector."""
    n = len(confidences)
    if n == 0:
        return CalibrationReport(
            sector=sector,
            n=0,
            accuracy=0.0,
            mean_confidence=0.0,
            ece=0.0,
            brier=0.0,
            bins=[],
        )
    accuracy = sum(correct) / n
    mean_conf = sum(confidences) / n
    temperature = find_best_temperature(confidences, correct)
    calibrated = temperature_scale_confidences(confidences, temperature)
    return CalibrationReport(
        sector=sector,
        n=n,
        accuracy=accuracy,
        mean_confidence=mean_conf,
        ece=expected_calibration_error(confidences, correct, n_bins),
        brier=brier_score(confidences, correct),
        calibrated_ece=expected_calibration_error(calibrated, correct, n_bins),
        calibrated_brier=brier_score(calibrated, correct),
        calibration_temperature=temperature,
        bins=reliability_bins(confidences, correct, n_bins),
    )
