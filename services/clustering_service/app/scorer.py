"""
Multimodal Duplicate Scorer — IEP-4

Scores each raw candidate against the incoming complaint across five
independent dimensions, then computes a weighted composite score.

Phase 1: rule-based weights + Haversine + exponential decay.
Phase 2: Replace composite formula with an XGBoost ranker trained on
         labelled duplicate pairs from admin corrections.

LLM Duplicate Judge:
  When composite score falls in the ambiguous 0.60–0.92 band, a Qwen LLM
  is called to resolve the decision. The LLM result takes precedence when
  its confidence ≥ 0.80.
"""

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Optional, Tuple

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    DuplicateCandidate,
    EmbeddingServiceResult,
    RawCandidate,
    ReconciliationStatus,
    SimilarityScores,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# LLM Judge configuration
# ---------------------------------------------------------------------------

LLM_JUDGE_ENABLED: bool = os.getenv("LLM_JUDGE_ENABLED", "true").lower() == "true"
LLM_JUDGE_TIMEOUT: float = float(os.getenv("LLM_JUDGE_TIMEOUT", "8"))
QWEN_BASE_URL: str = os.getenv("QWEN_BASE_URL", "")
QWEN_MODEL: str = os.getenv("QWEN_MODEL", "Qwen/Qwen2.5-3B-Instruct")
QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "none")

# Thresholds for LLM judge activation
LLM_JUDGE_BAND_LOW: float = 0.60
LLM_JUDGE_BAND_HIGH: float = 0.92
LLM_JUDGE_MIN_CONFIDENCE: float = 0.80   # LLM must meet this to override composite

_JUDGE_SYSTEM = """\
You are a duplicate detection expert for CedarFix, a Lebanese public infrastructure complaint platform.
Given two complaint reports, decide if they refer to the SAME real-world incident.

Return ONLY a valid JSON object with no explanation or markdown:
{
  "verdict": "<DUPLICATE | RELATED_SAME_CLUSTER | NEW_INCIDENT | NEEDS_ADMIN_REVIEW>",
  "confidence": <0.0–1.0>,
  "reason": "<1–2 sentences>"
}

Verdict definitions:
  DUPLICATE: Same issue, same location, reported within a short time window.
  RELATED_SAME_CLUSTER: Different reports about the same ongoing problem (e.g., same broken road).
  NEW_INCIDENT: Clearly distinct incidents.
  NEEDS_ADMIN_REVIEW: Insufficient information to decide.
"""


async def _call_llm_judge(
    incoming_text: str,
    incoming_type: str,
    incoming_location: str,
    candidate_summary: str,
    candidate_type: str,
    candidate_location: str,
    composite_score: float,
) -> Optional[dict]:
    if not LLM_JUDGE_ENABLED or not QWEN_BASE_URL:
        return None
    try:
        import openai
        client = openai.AsyncOpenAI(
            api_key=QWEN_API_KEY,
            base_url=QWEN_BASE_URL,
            max_retries=0,
            timeout=LLM_JUDGE_TIMEOUT,
        )
        user_msg = (
            f"Incoming complaint:\n"
            f"  Type: {incoming_type}\n"
            f"  Location: {incoming_location}\n"
            f"  Text: \"{incoming_text[:300]}\"\n\n"
            f"Existing complaint:\n"
            f"  Type: {candidate_type}\n"
            f"  Location: {candidate_location}\n"
            f"  Summary: \"{candidate_summary[:300]}\"\n\n"
            f"Composite similarity score: {composite_score:.3f} (in ambiguous 0.60–0.92 range).\n"
            "Is this a duplicate?"
        )
        resp = await client.chat.completions.create(
            model=QWEN_MODEL,
            messages=[
                {"role": "system", "content": _JUDGE_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        raw = resp.choices[0].message.content
        raw = re.sub(r"```(?:json)?", "", raw).strip()
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start == -1 or end == 0:
            return None
        return json.loads(raw[start:end])
    except Exception as e:
        log.warning("[IEP-4] LLM judge call failed: %s", e)
        return None

# ---------------------------------------------------------------------------
# Adjacent issue-type pairs (partial compatibility)
# ---------------------------------------------------------------------------
_ADJACENT_PAIRS = {
    frozenset({"pothole", "road_damage"}),
    frozenset({"flooding", "water_pipe"}),
    frozenset({"electricity_outage", "streetlight"}),
    frozenset({"waste_accumulation", "sidewalk_damage"}),
}

# ---------------------------------------------------------------------------
# Scoring weights — four context-sensitive sets
# ---------------------------------------------------------------------------

# Both incoming and candidate have images (full multimodal context)
_W_BOTH_MULTIMODAL = dict(mpnet=0.28, clip_text=0.18, clip_image=0.22, type=0.12, loc=0.10, time=0.10)

# Incoming has no image, candidate has image (cross-modal: text query found image entry)
_W_NEW_TEXT_EXISTING_IMAGE = dict(mpnet=0.35, clip_text=0.28, clip_image=0.00, type=0.15, loc=0.12, time=0.10)

# Incoming has image, candidate has no image (cross-modal: image query found text entry)
_W_NEW_IMAGE_EXISTING_TEXT = dict(mpnet=0.25, clip_text=0.00, clip_image=0.38, type=0.15, loc=0.12, time=0.10)

# Both text-only (no images)
_W_BOTH_TEXT_ONLY = dict(mpnet=0.50, clip_text=0.18, clip_image=0.00, type=0.14, loc=0.10, time=0.08)

# Cross-modal signals: multiply cross-modal scores by this factor before weighting
XMODAL_PENALTY = 0.90

# Convergence bonus: added to composite when both xmodal signals are strong
XMODAL_BONUS_THRESHOLD = 0.70
XMODAL_BONUS = 0.04

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

        # ── Detect modality combination ──────────────────────────────────────
        # A candidate "has image" if it has a clip_image entry (raw_clip_image_sim > 0
        # means either we found it via clip_image search, or it was a cross-modal hit).
        new_has_image = image_present
        candidate_has_image = candidate.raw_clip_image_sim > 0.0

        # ── Per-modality similarity scores ───────────────────────────────────
        mpnet_sim = candidate.raw_mpnet_text_sim or candidate.raw_text_similarity

        # Apply cross-modal penalty to CLIP scores that crossed modality boundaries
        clip_text_raw = candidate.raw_clip_text_sim
        clip_image_raw = candidate.raw_clip_image_sim

        clip_text_eff = (
            clip_text_raw * XMODAL_PENALTY
            if candidate.clip_text_is_xmodal
            else clip_text_raw
        )
        clip_image_eff = (
            clip_image_raw * XMODAL_PENALTY
            if candidate.clip_image_is_xmodal
            else clip_image_raw
        )

        type_sim = _type_match_score(
            canonical.issue_type, candidate.issue_type,
            canonical.subcategory, candidate.subcategory,
        )

        loc_sim = _location_similarity(
            lat_a=canonical.location.latitude,
            lon_a=canonical.location.longitude,
            dist_a=canonical.location.district,
            lat_b=candidate.location.latitude,
            lon_b=candidate.location.longitude,
            dist_b=candidate.location.district,
        )

        time_sim = _temporal_similarity(canonical.timestamp, candidate.timestamp)

        # ── Select weight set based on modality combination ──────────────────
        if new_has_image and candidate_has_image:
            w = _W_BOTH_MULTIMODAL
        elif new_has_image and not candidate_has_image:
            w = _W_NEW_IMAGE_EXISTING_TEXT
        elif not new_has_image and candidate_has_image:
            w = _W_NEW_TEXT_EXISTING_IMAGE
        else:
            w = _W_BOTH_TEXT_ONLY

        # ── Composite score ───────────────────────────────────────────────────
        composite = (
            w["mpnet"]     * mpnet_sim     +
            w["clip_text"] * clip_text_eff +
            w["clip_image"]* clip_image_eff +
            w["type"]      * type_sim      +
            w["loc"]       * loc_sim       +
            w["time"]      * time_sim
        )

        # Convergence bonus: both cross-modal signals strong → likely true duplicate
        if (
            candidate.clip_text_is_xmodal and clip_text_raw > XMODAL_BONUS_THRESHOLD
            and candidate.clip_image_is_xmodal and clip_image_raw > XMODAL_BONUS_THRESHOLD
        ):
            composite = min(1.0, composite + XMODAL_BONUS)

        # Legacy recheck flag: kept for backward compatibility with LLM judge
        recheck = image_present and (
            clip_image_eff >= 0.80 and mpnet_sim < 0.60
        )
        recheck_reason = (
            f"High CLIP image similarity ({clip_image_raw:.2f}, xmodal={candidate.clip_image_is_xmodal}) "
            f"but weak MPNet similarity ({mpnet_sim:.2f})"
            if recheck
            else None
        )

        scores = SimilarityScores(
            text_similarity=round(mpnet_sim, 4),
            image_similarity=round(clip_image_eff, 4),
            clip_text_similarity=round(clip_text_eff, 4),
            clip_image_similarity=round(clip_image_eff, 4),
            clip_text_is_xmodal=candidate.clip_text_is_xmodal,
            clip_image_is_xmodal=candidate.clip_image_is_xmodal,
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

    async def score_with_llm_judge(
        self,
        canonical: CanonicalComplaint,
        candidate: RawCandidate,
        text_embedding: list,
        image_embedding: list,
        image_present: bool,
        incoming_text: str = "",
    ) -> DuplicateCandidate:
        """
        Like score(), but calls the LLM judge for ambiguous composite scores
        (0.60 ≤ composite < 0.92). The LLM verdict overrides the reconciliation
        status when its confidence ≥ LLM_JUDGE_MIN_CONFIDENCE.
        """
        result = self.score(canonical, candidate, text_embedding, image_embedding, image_present)
        composite = result.multimodal_score

        # Fast paths: skip LLM for clear cases
        if composite >= LLM_JUDGE_BAND_HIGH or composite < LLM_JUDGE_BAND_LOW:
            return result

        # Ambiguous band — invoke LLM judge
        incoming_loc = (
            f"{canonical.location.district or ''}, {canonical.location.governorate or ''}".strip(", ")
            or "unknown location"
        )
        candidate_loc = (
            f"{candidate.location.district or ''}, {getattr(candidate.location, 'governorate', '') or ''}".strip(", ")
            or "unknown location"
        )

        llm_data = await _call_llm_judge(
            incoming_text=incoming_text[:300],
            incoming_type=str(canonical.issue_type),
            incoming_location=incoming_loc,
            candidate_summary=candidate.summary or "",
            candidate_type=str(candidate.issue_type),
            candidate_location=candidate_loc,
            composite_score=composite,
        )

        if llm_data:
            verdict = llm_data.get("verdict", "")
            llm_conf = float(llm_data.get("confidence", 0.0))
            llm_reason = llm_data.get("reason", "")

            if llm_conf >= LLM_JUDGE_MIN_CONFIDENCE:
                verdict_map = {
                    "DUPLICATE":            ReconciliationStatus.DUPLICATE,
                    "RELATED_SAME_CLUSTER": ReconciliationStatus.NEW_INCIDENT,  # cluster, not exact dup
                    "NEW_INCIDENT":         ReconciliationStatus.NEW_INCIDENT,
                    "NEEDS_ADMIN_REVIEW":   ReconciliationStatus.REQUIRES_ADMIN_REVIEW,
                }
                reconciliation = verdict_map.get(verdict, ReconciliationStatus.INSUFFICIENT_EVIDENCE)
                log.info(
                    "[IEP-4] LLM judge: composite=%.3f → %s (conf=%.2f) — %s",
                    composite, verdict, llm_conf, llm_reason,
                )
                # Return updated candidate with LLM reconciliation
                return result.model_copy(update={
                    "per_candidate_reconciliation": reconciliation,
                    "recheck_reason": (result.recheck_reason or "") + f" | LLM judge: {llm_reason}",
                })
            else:
                log.debug(
                    "[IEP-4] LLM judge low confidence %.2f for composite %.3f — keeping score-based decision",
                    llm_conf, composite,
                )

        return result


# ---------------------------------------------------------------------------
# Scoring sub-functions
# ---------------------------------------------------------------------------

def _type_match_score(
    type_a: str,
    type_b: str,
    sub_a: str = "",
    sub_b: str = "",
) -> float:
    type_a = (type_a or "unknown").strip().lower()
    type_b = (type_b or "unknown").strip().lower()
    if type_a == type_b:
        # Both OTHER — compare specific subcategories when available.
        # Two complaints of "other" type with DIFFERENT specific subcategories
        # (e.g. "broken_bench" vs "graffiti") should not get a full type match.
        if type_a in ("other", "unknown"):
            a = (sub_a or "").strip().lower()
            b = (sub_b or "").strip().lower()
            if (a and b
                    and a not in ("other", "unknown")
                    and b not in ("other", "unknown")
                    and a != b):
                return 0.20   # different "other" incidents — partial credit only
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
