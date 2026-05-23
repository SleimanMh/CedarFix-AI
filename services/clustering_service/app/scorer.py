"""
Multimodal Duplicate Scorer — IEP-4

Scores each raw candidate against the incoming complaint across five
independent dimensions, then computes a weighted composite score.

Phase 1: rule-based weights + Haversine + exponential decay.
Phase 2: Replace composite formula with an XGBoost ranker trained on
         labelled duplicate pairs from admin corrections.
"""

import math
from datetime import datetime, timezone
from typing import Optional, Tuple

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    ComplaintType,
    DuplicateCandidate,
    EmbeddingServiceResult,
    RawCandidate,
    ReconciliationStatus,
    SimilarityScores,
)

# ---------------------------------------------------------------------------
# Adjacent issue-type pairs (partial compatibility)
# ---------------------------------------------------------------------------
_ADJACENT_PAIRS = {
    frozenset({ComplaintType.POTHOLE, ComplaintType.ROAD_DAMAGE}),
    frozenset({ComplaintType.FLOODING, ComplaintType.WATER_PIPE}),
    frozenset({ComplaintType.ELECTRICITY, ComplaintType.STREETLIGHT}),
    frozenset({ComplaintType.WASTE, ComplaintType.SIDEWALK}),
}

# ---------------------------------------------------------------------------
# Standard scoring weights
# ---------------------------------------------------------------------------
_W_STD = dict(text=0.40, image=0.25, type=0.15, loc=0.10, time=0.10)

# Weights used when image_sim is high but text_sim is weak (cross-modal recheck)
_W_RECHECK = dict(text=0.20, image=0.50, type=0.15, loc=0.10, time=0.05)

# Thresholds for recheck trigger
_RECHECK_IMAGE_MIN = 0.80
_RECHECK_TEXT_MAX = 0.60

# Temporal half-life in hours
_TIME_HALF_LIFE_HOURS = 24.0

# Location similarity constants
_LOC_DECAY_KM = 0.5          # Haversine decay: 50% at 350m, ~0 at 2km
_LOC_DISTRICT_MATCH = 0.80   # score when same district but no GPS
_LOC_NEUTRAL = 0.50          # score when no location info on either side


class MultimodalScorer:
    """
    Scores a single RawCandidate against the incoming complaint.
    Returns a DuplicateCandidate with all dimension scores populated.
    """

    def score(
        self,
        canonical: CanonicalComplaint,
        candidate: RawCandidate,
        text_embedding: list,
        image_embedding: list,
        image_present: bool,
    ) -> DuplicateCandidate:

        # ── Individual dimension scores ──────────────────────────────────────
        text_sim = candidate.raw_text_similarity       # already computed by Qdrant
        image_sim = candidate.raw_image_similarity     # from Qdrant image search (0 if N/A)

        # If both complaints have embeddings but image_sim was not set
        # (candidate came via text_search only), keep it 0.0 — we did not
        # compare images so we should not inflate the score.

        type_sim = _type_match_score(canonical.issue_type, candidate.issue_type)

        loc_sim = _location_similarity(
            lat_a=canonical.location.latitude,
            lon_a=canonical.location.longitude,
            dist_a=canonical.location.district,
            lat_b=candidate.location.latitude,
            lon_b=candidate.location.longitude,
            dist_b=candidate.location.district,
        )

        time_sim = _temporal_similarity(canonical.timestamp, candidate.timestamp)

        # ── Cross-modal recheck ───────────────────────────────────────────────
        recheck = image_present and (
            image_sim >= _RECHECK_IMAGE_MIN and text_sim < _RECHECK_TEXT_MAX
        )
        recheck_reason = (
            f"High image similarity ({image_sim:.2f}) but weak text similarity ({text_sim:.2f})"
            if recheck
            else None
        )

        # ── Composite score ───────────────────────────────────────────────────
        w = _W_RECHECK if recheck else _W_STD
        composite = (
            w["text"]  * text_sim  +
            w["image"] * image_sim +
            w["type"]  * type_sim  +
            w["loc"]   * loc_sim   +
            w["time"]  * time_sim
        )

        scores = SimilarityScores(
            text_similarity=round(text_sim, 4),
            image_similarity=round(image_sim, 4),
            location_similarity=round(loc_sim, 4),
            time_similarity=round(time_sim, 4),
            issue_type_similarity=round(type_sim, 4),
        )

        return DuplicateCandidate(
            candidate_complaint_id=candidate.complaint_id,
            candidate_cluster_id=candidate.cluster_id,
            candidate_summary=candidate.summary,
            candidate_issue_type=candidate.issue_type,
            candidate_subcategory=candidate.subcategory,
            candidate_location=candidate.location,
            similarity_scores=scores,
            candidate_source=list(candidate.sources),
            multimodal_score=round(composite, 4),
            recheck_triggered=recheck,
            recheck_reason=recheck_reason,
            # Reconciliation filled in by ReconciliationEngine after scoring
            per_candidate_reconciliation=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
        )


# ---------------------------------------------------------------------------
# Scoring sub-functions
# ---------------------------------------------------------------------------

def _type_match_score(type_a: ComplaintType, type_b: ComplaintType) -> float:
    if type_a == type_b:
        return 1.0
    if frozenset({type_a, type_b}) in _ADJACENT_PAIRS:
        return 0.40
    return 0.0


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return R * 2 * math.asin(math.sqrt(a))


def _location_similarity(
    lat_a: Optional[float], lon_a: Optional[float], dist_a: Optional[str],
    lat_b: Optional[float], lon_b: Optional[float], dist_b: Optional[str],
) -> float:
    if lat_a is not None and lon_a is not None and lat_b is not None and lon_b is not None:
        dist_km = _haversine_km(lat_a, lon_a, lat_b, lon_b)
        return round(math.exp(-dist_km / _LOC_DECAY_KM), 4)
    if dist_a and dist_b:
        return _LOC_DISTRICT_MATCH if dist_a == dist_b else 0.10
    return _LOC_NEUTRAL


def _temporal_similarity(
    ts_a: Optional[datetime], ts_b: Optional[datetime]
) -> float:
    if ts_a is None or ts_b is None:
        return 0.50   # neutral
    # Make both timezone-aware for safe comparison
    if ts_a.tzinfo is None:
        ts_a = ts_a.replace(tzinfo=timezone.utc)
    if ts_b.tzinfo is None:
        ts_b = ts_b.replace(tzinfo=timezone.utc)
    delta_hours = abs((ts_a - ts_b).total_seconds()) / 3600.0
    return round(math.exp(-delta_hours / _TIME_HALF_LIFE_HOURS), 4)
