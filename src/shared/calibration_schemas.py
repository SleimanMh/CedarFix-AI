"""IEP-7 calibration and drift contracts plus pure metric math.

IEP-7 measures whether IEP-3's ``routing_confidence`` is *calibrated*: when
the router says 0.8, is it right ~80% of the time?  Ground-truth correctness
is derived from the IEP-5 incident lifecycle — a routed complaint is counted
"correct" when its incident reached RESOLVED without a later REOPENED event,
and "incorrect" when it was reopened (the routing/handling missed).

The ECE and Brier functions are pure and dependency-free so they can be
unit-tested directly.
"""
from __future__ import annotations

import math

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "CalibrationBin",
    "CalibrationReport",
    "expected_calibration_error",
    "brier_score",
    "reliability_bins",
    "temperature_scale_confidences",
    "find_best_temperature",
]


class CalibrationBin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lower: float = Field(..., ge=0.0, le=1.0)
    upper: float = Field(..., ge=0.0, le=1.0)
    count: int = Field(..., ge=0)
    mean_confidence: float = Field(..., ge=0.0, le=1.0)
    accuracy: float = Field(..., ge=0.0, le=1.0)


class CalibrationReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sector: str = Field(..., min_length=1)
    n: int = Field(..., ge=0)
    accuracy: float = Field(..., ge=0.0, le=1.0)
    mean_confidence: float = Field(..., ge=0.0, le=1.0)
    ece: float = Field(..., ge=0.0, le=1.0)
    brier: float = Field(..., ge=0.0, le=1.0)
    calibrated_ece: float = Field(default=0.0, ge=0.0, le=1.0)
    calibrated_brier: float = Field(default=0.0, ge=0.0, le=1.0)
    calibration_temperature: float = Field(default=1.0, gt=0.0)
    bins: list[CalibrationBin] = Field(default_factory=list)


def reliability_bins(
    confidences: list[float],
    correct: list[int],
    n_bins: int = 10,
) -> list[CalibrationBin]:
    """Partition predictions into equal-width confidence bins."""
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must be the same length")
    bins: list[CalibrationBin] = []
    width = 1.0 / n_bins
    for index in range(n_bins):
        lo = index * width
        hi = 1.0 if index == n_bins - 1 else (index + 1) * width
        # Upper-inclusive only for the final bin so 1.0 lands somewhere.
        members = [
            (conf, hit)
            for conf, hit in zip(confidences, correct)
            if (lo <= conf <= hi if index == n_bins - 1 else lo <= conf < hi)
        ]
        count = len(members)
        if count == 0:
            bins.append(
                CalibrationBin(lower=lo, upper=hi, count=0, mean_confidence=0.0, accuracy=0.0)
            )
            continue
        mean_conf = sum(conf for conf, _ in members) / count
        acc = sum(hit for _, hit in members) / count
        bins.append(
            CalibrationBin(
                lower=lo,
                upper=hi,
                count=count,
                mean_confidence=mean_conf,
                accuracy=acc,
            )
        )
    return bins


def expected_calibration_error(
    confidences: list[float],
    correct: list[int],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error — weighted |confidence - accuracy| over bins."""
    total = len(confidences)
    if total == 0:
        return 0.0
    bins = reliability_bins(confidences, correct, n_bins)
    ece = 0.0
    for bucket in bins:
        if bucket.count == 0:
            continue
        ece += (bucket.count / total) * abs(bucket.mean_confidence - bucket.accuracy)
    return ece


def brier_score(confidences: list[float], correct: list[int]) -> float:
    """Mean squared error between predicted confidence and binary outcome."""
    if len(confidences) != len(correct):
        raise ValueError("confidences and correct must be the same length")
    if not confidences:
        return 0.0
    return sum((conf - hit) ** 2 for conf, hit in zip(confidences, correct)) / len(confidences)


def _logit(p: float) -> float:
    p = min(0.999999, max(0.000001, p))
    return math.log(p / (1.0 - p))


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def temperature_scale_confidences(confidences: list[float], temperature: float) -> list[float]:
    """Apply scalar temperature scaling to binary confidence estimates."""
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    return [_sigmoid(_logit(conf) / temperature) for conf in confidences]


def find_best_temperature(
    confidences: list[float],
    correct: list[int],
    candidates: tuple[float, ...] = (0.6, 0.75, 0.9, 1.0, 1.15, 1.35, 1.6, 2.0, 2.5, 3.0),
) -> float:
    """Grid-search the temperature that minimizes Brier score."""
    if not confidences:
        return 1.0
    best_temp = 1.0
    best_score = brier_score(confidences, correct)
    for temp in candidates:
        scaled = temperature_scale_confidences(confidences, temp)
        score = brier_score(scaled, correct)
        if score < best_score:
            best_score = score
            best_temp = temp
    return best_temp
