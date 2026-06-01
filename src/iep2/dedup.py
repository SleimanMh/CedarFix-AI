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
the vector in ``text_embedding_vector`` when the model is available, while
older/demo rows may still pass an inline JSON array. IEP-2 degrades gracefully
to geo-only when embeddings are missing.
"""
from __future__ import annotations

import json
import math
import uuid

from src.shared.schemas import DuplicateMatchEvidence, IncidentIntelligence
from src.iep2.fusion_model import RELATED_INCIDENT_THRESHOLD, SAME_INCIDENT_THRESHOLD, score_pair

SIM_THRESHOLD: float = 0.88   # cosine similarity above which we call it a dup
GEO_RADIUS_M: float = 500.0   # candidates beyond this are never auto-merged


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    mag_a = math.sqrt(sum(x * x for x in a))
    mag_b = math.sqrt(sum(x * x for x in b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _parse_embedding(ref: str | list[float] | None) -> list[float] | None:
    """Try to decode a stored embedding reference (JSON array)."""
    if not ref:
        return None
    if isinstance(ref, list):
        try:
            return [float(x) for x in ref]
        except (TypeError, ValueError):
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
    embedding_ref: str | list[float] | None,
    lat: float | None,
    lon: float | None,
    issue_type: str | None,
    candidates: list[dict],
    *,
    created_at: object | None = None,
    image_issue_type: str | None = None,
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
    best_fusion: dict | None = None
    best_fusion_score: float = -1.0
    candidates_within_radius = 0
    embedding_comparison_count = 0

    for cand in candidates:
        dist = geo_distance_m(lat, lon, cand.get("gps_lat"), cand.get("gps_lon"))
        if dist > GEO_RADIUS_M:
            continue
        candidates_within_radius += 1

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
                embedding_comparison_count += 1

        if sim is not None and sim > best_sim:
            pass

        fusion = score_pair(
            similarity_score=sim,
            geo_distance_m=dist,
            issue_type=issue_type,
            candidate_issue_type=cand.get("issue_type"),
            image_issue_type=image_issue_type,
            candidate_image_issue_type=cand.get("image_issue_type"),
            created_at=created_at,
            candidate_created_at=cand.get("created_at"),
        )
        fusion_score = float(fusion["fusion_score"])
        if fusion_score > best_fusion_score or (
            fusion_score == best_fusion_score and dist < best_dist
        ):
            best_fusion_score = fusion_score
            best_fusion = fusion
            if sim is not None:
                best_sim = sim
            elif best_sim < 0:
                best_sim = -1.0
            best_dist = dist
            best = cand

    if best is not None and (
        best_sim >= SIM_THRESHOLD
        or (best_fusion_score >= SAME_INCIDENT_THRESHOLD and best_sim >= 0.75)
    ):
        return {
            "is_duplicate": True,
            "incident_id": best["incident_id"] or str(uuid.uuid4()),
            "match_complaint": best["complaint_id"],
            "similarity_score": round(best_sim, 4),
            "geo_distance_m": round(best_dist, 1),
            "decision_reason": (
                f"learned_fusion_same_incident score={best_fusion_score:.3f} "
                f"sim={best_sim:.3f} dist={best_dist:.0f}m"
            ),
            "candidate_count": len(candidates),
            "candidates_within_radius": candidates_within_radius,
            "embedding_comparison_count": embedding_comparison_count,
            "semantic_threshold": SIM_THRESHOLD,
            "geo_radius_m": GEO_RADIUS_M,
            "fusion_score": round(best_fusion_score, 4),
            "fusion_label": (best_fusion or {}).get("fusion_label", "same_incident"),
            "fusion_features": (best_fusion or {}).get("fusion_features", {}),
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
            "candidate_count": len(candidates),
            "candidates_within_radius": candidates_within_radius,
            "embedding_comparison_count": embedding_comparison_count,
            "semantic_threshold": SIM_THRESHOLD,
            "geo_radius_m": GEO_RADIUS_M,
            "fusion_score": round(best_fusion_score, 4) if best_fusion_score >= 0 else None,
            "fusion_label": (best_fusion or {}).get("fusion_label", "nearby_review"),
            "fusion_features": (best_fusion or {}).get("fusion_features", {}),
        }

    return {
        "is_duplicate": False,
        "incident_id": str(uuid.uuid4()),
        "match_complaint": None,
        "similarity_score": round(best_sim, 4) if best_sim >= 0 else None,
        "geo_distance_m": round(best_dist, 1) if best_dist < float("inf") else None,
        "decision_reason": "no_duplicate_found",
        "candidate_count": len(candidates),
        "candidates_within_radius": candidates_within_radius,
        "embedding_comparison_count": embedding_comparison_count,
        "semantic_threshold": SIM_THRESHOLD,
        "geo_radius_m": GEO_RADIUS_M,
        "fusion_score": round(best_fusion_score, 4) if best_fusion_score >= 0 else None,
        "fusion_label": (
            (best_fusion or {}).get("fusion_label")
            or ("related_incident" if best_fusion_score >= RELATED_INCIDENT_THRESHOLD else "unrelated")
        ),
        "fusion_features": (best_fusion or {}).get("fusion_features", {}),
    }


def build_incident_intelligence(
    complaint_id: str,
    decision: dict,
    candidates: list[dict],
) -> dict:
    """Build the durable IEP-2 incident packet from a pair decision."""
    incident_id = decision["incident_id"]
    cluster_report_ids = [
        cand["complaint_id"]
        for cand in candidates
        if cand.get("incident_id") == incident_id and cand.get("complaint_id")
    ]
    if complaint_id not in cluster_report_ids:
        cluster_report_ids.append(complaint_id)

    cluster_issue_types = [
        cand["issue_type"]
        for cand in candidates
        if cand.get("incident_id") == incident_id and cand.get("issue_type")
    ]
    cluster_size = max(1, len(cluster_report_ids))
    decision_reason = decision.get("decision_reason", "")

    if decision.get("is_duplicate"):
        review_recommendation = "AUTO_ATTACH_TO_INCIDENT"
    elif decision_reason.startswith("geo_only"):
        review_recommendation = "HITL_REVIEW_NEARBY_REPORT"
    else:
        review_recommendation = "CREATE_NEW_INCIDENT"

    if review_recommendation == "HITL_REVIEW_NEARBY_REPORT":
        lifecycle_state = "NEARBY_REVIEW"
    elif cluster_size >= 5:
        lifecycle_state = "ACTIVE"
    elif cluster_size >= 2:
        lifecycle_state = "EMERGING"
    else:
        lifecycle_state = "NEW"

    evidence = DuplicateMatchEvidence(
        complaint_id=complaint_id,
        incident_id=incident_id,
        is_duplicate=bool(decision.get("is_duplicate")),
        match_complaint_id=decision.get("match_complaint"),
        similarity_score=decision.get("similarity_score"),
        geo_distance_m=decision.get("geo_distance_m"),
        decision_reason=decision_reason,
        candidate_count=decision.get("candidate_count", len(candidates)),
        candidates_within_radius=decision.get("candidates_within_radius", 0),
        embedding_comparison_count=decision.get("embedding_comparison_count", 0),
        semantic_threshold=decision.get("semantic_threshold", SIM_THRESHOLD),
        geo_radius_m=decision.get("geo_radius_m", GEO_RADIUS_M),
        fusion_score=decision.get("fusion_score"),
        fusion_label=decision.get("fusion_label"),
        fusion_features=decision.get("fusion_features") or {},
    )
    return IncidentIntelligence(
        complaint_id=complaint_id,
        incident_id=incident_id,
        is_duplicate=bool(decision.get("is_duplicate")),
        matched_complaint_id=decision.get("match_complaint"),
        incident_lifecycle_state=lifecycle_state,
        review_recommendation=review_recommendation,
        cluster_size=cluster_size,
        cluster_duplicate_count=max(0, cluster_size - 1),
        cluster_report_ids=cluster_report_ids,
        cluster_issue_types=cluster_issue_types,
        match_evidence=evidence,
    ).model_dump(mode="json")
