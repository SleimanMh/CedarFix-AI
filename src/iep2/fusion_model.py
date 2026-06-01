"""Multi-signal incident fusion scorer for IEP-2.

IEP-2 still keeps hard safety gates around auto-merge. This scorer makes the
decision evidence stronger by combining semantic, geographic, temporal, issue,
and visual signals into an interpretable same-incident score.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone

SAME_INCIDENT_THRESHOLD: float = 0.78
RELATED_INCIDENT_THRESHOLD: float = 0.58


def _geo_score(distance_m: float | None) -> float:
    if distance_m is None or not math.isfinite(distance_m):
        return 0.0
    return max(0.0, min(1.0, math.exp(-distance_m / 350.0)))


def _time_score(hours_delta: float | None) -> float:
    if hours_delta is None:
        return 0.5
    return max(0.0, min(1.0, math.exp(-abs(hours_delta) / 72.0)))


def _coarse_issue(issue: str | None) -> str:
    return (issue or "").split("_", 1)[0].upper()


def _issue_score(issue_a: str | None, issue_b: str | None) -> float:
    if not issue_a or not issue_b:
        return 0.5
    if issue_a == issue_b:
        return 1.0
    if _coarse_issue(issue_a) and _coarse_issue(issue_a) == _coarse_issue(issue_b):
        return 0.75
    return 0.0


def _image_score(image_a: str | None, image_b: str | None) -> float:
    if not image_a or not image_b:
        return 0.5
    return 1.0 if image_a == image_b else 0.0


def _hours_between(a: object, b: object) -> float | None:
    if a is None or b is None:
        return None
    if isinstance(a, str):
        try:
            a = datetime.fromisoformat(a.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(b, str):
        try:
            b = datetime.fromisoformat(b.replace("Z", "+00:00"))
        except ValueError:
            return None
    if not isinstance(a, datetime) or not isinstance(b, datetime):
        return None
    if a.tzinfo is None:
        a = a.replace(tzinfo=timezone.utc)
    if b.tzinfo is None:
        b = b.replace(tzinfo=timezone.utc)
    return abs((a - b).total_seconds()) / 3600.0


def score_pair(
    *,
    similarity_score: float | None,
    geo_distance_m: float | None,
    issue_type: str | None,
    candidate_issue_type: str | None,
    image_issue_type: str | None = None,
    candidate_image_issue_type: str | None = None,
    created_at: object | None = None,
    candidate_created_at: object | None = None,
) -> dict:
    """Return interpretable fusion score and features for a candidate pair."""
    semantic = max(0.0, min(1.0, float(similarity_score or 0.0)))
    geo = _geo_score(geo_distance_m)
    time_delta = _hours_between(created_at, candidate_created_at)
    temporal = _time_score(time_delta)
    issue = _issue_score(issue_type, candidate_issue_type)
    image = _image_score(image_issue_type, candidate_image_issue_type)

    # Weighted late fusion. Semantic and GPS carry most of the signal; issue,
    # time, and image are stabilizers and explanation features.
    score = (
        0.44 * semantic
        + 0.24 * geo
        + 0.16 * issue
        + 0.10 * temporal
        + 0.06 * image
    )
    if semantic == 0.0:
        # Geo-only cases should be reviewed, not auto-merged.
        score = min(score, 0.56)
    label = (
        "same_incident"
        if score >= SAME_INCIDENT_THRESHOLD
        else "related_incident"
        if score >= RELATED_INCIDENT_THRESHOLD
        else "unrelated"
    )
    return {
        "fusion_score": round(score, 4),
        "fusion_label": label,
        "fusion_features": {
            "semantic_similarity": round(semantic, 4),
            "geo_score": round(geo, 4),
            "time_score": round(temporal, 4),
            "issue_score": round(issue, 4),
            "image_score": round(image, 4),
            "hours_delta": round(time_delta, 2) if time_delta is not None else None,
        },
    }
