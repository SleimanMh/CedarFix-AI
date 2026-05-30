"""IEP-2 duplicate and incident-cluster detection.

Algorithm
---------
1. Retrieve the embedding for the incoming complaint from the DB.
2. Query existing complaints within the geo-radius window that share the
   same coarse issue_type bucket.
3. Compute cosine similarity against each candidate.
4. If the closest candidate exceeds SIM_THRESHOLD AND is within
   GEO_RADIUS_M, flag as semantic duplicate and attach to its incident_id.
5. Otherwise assign a new incident_id (uuid4).

The actual embedding comparison is intentionally lightweight: IEP-1 stores
``text_embedding_ref`` as a JSON-serialised float list when the model is
available, or None otherwise.  IEP-2 degrades gracefully to geo-only when
embeddings are missing.
"""
from __future__ import annotations

import json
import math
import uuid

SIM_THRESHOLD: float = 0.88   # cosine similarity above which we call it a dup
GEO_RADIUS_M: float = 500.0   # candidates beyond this are never auto-merged


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _parse_embedding(ref: str | None) -> list[float] | None:
    """Try to decode a stored embedding reference (JSON array)."""
    if not ref:
        return None
    try:
        decoded = json.loads(ref)
        if isinstance(decoded, list) and decoded:
            return [float(x) for x in decoded]
    except (json.JSONDecodeError, ValueError):
        pass
    return None


def geo_distance_m(lat1: float | None, lon1: float | None,
                   lat2: float | None, lon2: float | None) -> float:
    """Equirectangular approximation — good enough within a city block."""
    if None in (lat1, lon1, lat2, lon2):
        return float("inf")
    R = 6_371_000.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    return R * math.sqrt(dlat**2 + dlon**2)


def classify_pair(
    complaint_id: str,
    embedding_ref: str | None,
    lat: float | None,
    lon: float | None,
    issue_type: str | None,
    candidates: list[dict],
) -> dict:
    """Return a dedup decision for a single complaint against a candidate list.

    Each ``candidates`` entry is a dict with keys:
        complaint_id, incident_id, text_embedding_ref, gps_lat, gps_lon, issue_type

    Returns a dict with:
        is_duplicate      bool
        incident_id       str  (existing or new uuid4)
        match_complaint   str | None  (matched complaint_id if dup)
        similarity_score  float | None
        geo_distance_m    float | None
        decision_reason   str
    """
    my_vec = _parse_embedding(embedding_ref)

    best: dict | None = None
    best_sim: float = -1.0
    best_dist: float = float("inf")

    for cand in candidates:
        dist = geo_distance_m(lat, lon, cand.get("gps_lat"), cand.get("gps_lon"))
        if dist > GEO_RADIUS_M:
            continue

        # Coarse issue_type gate (None matches anything)
        cand_issue = cand.get("issue_type") or ""
        my_issue = issue_type or ""
        if my_issue and cand_issue and my_issue.split("_")[0] != cand_issue.split("_")[0]:
            continue

        sim: float | None = None
        if my_vec is not None:
            cand_vec = _parse_embedding(cand.get("text_embedding_ref"))
            if cand_vec is not None:
                sim = _cosine(my_vec, cand_vec)

        if sim is not None and sim > best_sim:
            best_sim = sim
            best_dist = dist
            best = cand
        elif sim is None and dist < best_dist:
            # Geo-only fallback: pick closest
            best_dist = dist
            best = cand

    if best is not None and best_sim >= SIM_THRESHOLD:
        return {
            "is_duplicate": True,
            "incident_id": best["incident_id"] or str(uuid.uuid4()),
            "match_complaint": best["complaint_id"],
            "similarity_score": round(best_sim, 4),
            "geo_distance_m": round(best_dist, 1),
            "decision_reason": f"semantic_dup sim={best_sim:.3f} dist={best_dist:.0f}m",
        }

    if best is not None and best_sim < 0 and best_dist <= 200.0:
        # Geo-only: within 200 m and no embedding — be conservative, flag for HITL
        return {
            "is_duplicate": False,
            "incident_id": str(uuid.uuid4()),
            "match_complaint": best["complaint_id"],
            "similarity_score": None,
            "geo_distance_m": round(best_dist, 1),
            "decision_reason": "geo_only_within_200m_no_embedding_needs_hitl",
        }

    return {
        "is_duplicate": False,
        "incident_id": str(uuid.uuid4()),
        "match_complaint": None,
        "similarity_score": round(best_sim, 4) if best_sim >= 0 else None,
        "geo_distance_m": round(best_dist, 1) if best_dist < float("inf") else None,
        "decision_reason": "no_duplicate_found",
    }
