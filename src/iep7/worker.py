"""IEP-7 calibration computation worker.

Derives ground-truth correctness from the IEP-5 incident lifecycle:
- a routed complaint whose incident reached RESOLVED/CLOSED with
  ``reopen_count == 0`` is counted *correct* (the routing held);
- one whose incident was reopened is counted *incorrect* (routing/handling
  missed the mark).

Per sector it computes ECE, Brier and accuracy, persists a CalibrationMetric
snapshot, and emits a drift RetrainingCandidate when ECE exceeds a threshold.
"""
from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from src.eep.db import (
    CalibrationMetric,
    Complaint,
    Incident,
    RetrainingCandidate,
    SessionLocal,
)
from src.iep7.calibration import build_report
from src.shared.calibration_schemas import CalibrationReport
from src.shared.lifecycle_schemas import IncidentState

logger = logging.getLogger("iep7.worker")

ECE_DRIFT_THRESHOLD = float(__import__("os").getenv("IEP7_ECE_DRIFT_THRESHOLD", "0.15"))
MIN_SECTOR_SAMPLES = int(__import__("os").getenv("IEP7_MIN_SECTOR_SAMPLES", "20"))

_TERMINAL_STATES = (IncidentState.RESOLVED.value, IncidentState.CLOSED.value)


async def _collect_outcomes() -> dict[str, tuple[list[float], list[int]]]:
    """Return ``{sector: (confidences, correct)}`` from resolved incidents."""
    buckets: dict[str, tuple[list[float], list[int]]] = {}
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(
                    Complaint.routing_sector,
                    Complaint.routing_confidence,
                    Incident.current_state,
                    Incident.reopen_count,
                )
                .join(Incident, Complaint.incident_id == Incident.incident_id)
                .where(
                    Complaint.routing_confidence.isnot(None),
                    Complaint.routing_sector.isnot(None),
                    Incident.current_state.in_(_TERMINAL_STATES),
                )
            )
        ).all()

    for sector, confidence, _state, reopen_count in rows:
        if confidence is None or sector is None:
            continue
        correct = 0 if (reopen_count or 0) > 0 else 1
        confidences, hits = buckets.setdefault(sector, ([], []))
        confidences.append(float(confidence))
        hits.append(correct)
    return buckets


async def compute_calibration() -> list[CalibrationReport]:
    """Compute, persist and (on drift) flag calibration for every sector."""
    buckets = await _collect_outcomes()
    reports: list[CalibrationReport] = []

    async with SessionLocal() as session:
        for sector, (confidences, correct) in buckets.items():
            if len(confidences) < MIN_SECTOR_SAMPLES:
                continue
            report = build_report(sector, confidences, correct)
            reports.append(report)
            session.add(
                CalibrationMetric(
                    id=str(uuid.uuid4()),
                    sector=sector,
                    n=report.n,
                    accuracy=report.accuracy,
                    mean_confidence=report.mean_confidence,
                    ece=report.ece,
                    brier=report.brier,
                    bins_json={
                        "bins": [b.model_dump() for b in report.bins],
                        "calibration_temperature": report.calibration_temperature,
                        "calibrated_ece": report.calibrated_ece,
                        "calibrated_brier": report.calibrated_brier,
                    },
                )
            )
            if report.ece > ECE_DRIFT_THRESHOLD:
                session.add(
                    RetrainingCandidate(
                        id=str(uuid.uuid4()),
                        complaint_id=f"calib:{sector}",
                        incident_id=None,
                        source="drift",
                        reason=f"ece={report.ece:.3f}>{ECE_DRIFT_THRESHOLD}",
                        original_routing={
                            "sector": sector,
                            "ece": report.ece,
                            "brier": report.brier,
                            "calibrated_ece": report.calibrated_ece,
                            "calibrated_brier": report.calibrated_brier,
                            "calibration_temperature": report.calibration_temperature,
                            "n": report.n,
                        },
                        status="pending",
                    )
                )
                logger.info(
                    "IEP-7 drift flagged sector=%s ece=%.3f n=%d",
                    sector,
                    report.ece,
                    report.n,
                )
        if reports:
            await session.commit()
    logger.info("IEP-7 calibration computed for %d sector(s)", len(reports))
    return reports


async def latest_metrics() -> list[dict]:
    """Most recent CalibrationMetric per sector."""
    async with SessionLocal() as session:
        rows = (
            await session.execute(
                select(CalibrationMetric).order_by(CalibrationMetric.created_at.desc())
            )
        ).scalars().all()
    seen: set[str] = set()
    latest: list[dict] = []
    for metric in rows:
        if metric.sector in seen:
            continue
        seen.add(metric.sector)
        latest.append(
            {
                "sector": metric.sector,
                "n": metric.n,
                "ece": metric.ece,
                "brier": metric.brier,
                "accuracy": metric.accuracy,
                "mean_confidence": metric.mean_confidence,
                "calibrated_ece": (metric.bins_json or {}).get("calibrated_ece")
                if isinstance(metric.bins_json, dict)
                else None,
                "calibrated_brier": (metric.bins_json or {}).get("calibrated_brier")
                if isinstance(metric.bins_json, dict)
                else None,
                "calibration_temperature": (metric.bins_json or {}).get("calibration_temperature")
                if isinstance(metric.bins_json, dict)
                else None,
                "created_at": metric.created_at.isoformat() if metric.created_at else None,
            }
        )
    return latest
