"""Retraining-priority scoring for IEP-5 lifecycle outcomes."""
from __future__ import annotations


def score_retraining_priority(
    *,
    source: str,
    original_routing: dict | None,
    reason: str | None = None,
) -> dict:
    """Rank lifecycle/drift signals for active-learning review.

    The score is not a prediction of truth; it is an operations model for which
    HITL corrections should be reviewed first for retraining.
    """
    routing = original_routing or {}
    score = 0.25
    reasons: list[str] = []

    if source == "reopen":
        score += 0.30
        reasons.append("incident_reopened")
    if source in {"drift", "oov"}:
        score += 0.22
        reasons.append(f"{source}_signal")
    confidence = routing.get("routing_confidence")
    if confidence is not None:
        conf = float(confidence)
        if conf >= 0.80:
            score += 0.20
            reasons.append("high_confidence_failure")
        elif conf < 0.55:
            score += 0.08
            reasons.append("low_confidence_case")
    if routing.get("hitl_required"):
        score += 0.08
        reasons.append("hitl_case")
    if routing.get("image_text_conflict") or "image_text_conflict" in str(reason or ""):
        score += 0.12
        reasons.append("image_text_conflict")
    if routing.get("routing_risk_score", 0) >= 0.55:
        score += 0.10
        reasons.append("high_routing_risk")

    return {
        "retraining_priority_score": round(min(1.0, score), 4),
        "retraining_priority_reasons": sorted(set(reasons)),
    }
