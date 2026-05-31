"""
Modal Alignment Computer — IEP-3

Compares the text understanding and image understanding results for the
SAME complaint to detect whether text and image are consistent.

This is the *intra-complaint* alignment (is this user's image related to
their own complaint text?).  Per-candidate reconciliation lives in IEP-4.

─────────────────────────────────────────────────────────────
ALIGNMENT SIGNAL — TWO PATHS (primary vs. fallback)
─────────────────────────────────────────────────────────────

PRIMARY (use this whenever available):
  CLIP embeds images and text in the SAME 512-dim space.
  When IEP-2 was called with the complaint text, it returns
  image_result.clip_text_embedding (512-dim CLIP text encoding).
  Cosine(clip_text_embedding, image_embedding) is a semantically
  valid alignment score — no projection, no approximation.

FALLBACK (MVP approximation only — do NOT rely on as evidence):
  If clip_text_embedding is absent (IEP-2 called without text, or
  an older client), we project the 512-dim CLIP image embedding into
  the 768-dim sentence-transformer space using the random linear
  projection matrix from fusion.py, then compute cosine with the
  sentence-transformer text embedding.
  This cross-model comparison is mathematically unsound because the
  two embedding spaces are unrelated.  Scores from this path are
  deliberately downscaled (×0.7) and the alignment is capped at
  UNCERTAIN — it must never drive a SUPPORTS or CONTRADICTS result.
  Its only purpose is to avoid returning NO_IMAGE when an image is
  genuinely present.

Phase 2: Replace both paths with a trained cross-modal alignment model.
"""

import math
from typing import Optional

from cedarfix_shared.schemas import (
    AlignmentStatus,
    ComplaintType,
    ImageUnderstandingResult,
    ReconciliationStatus,
    TextImageAlignment,
    TextUnderstandingResult,
)

# ---------------------------------------------------------------------------
# Adjacent issue-type pairs (text ↔ image mismatch is tolerable between these)
# ---------------------------------------------------------------------------

_ADJACENT_PAIRS = {
    frozenset({ComplaintType.POTHOLE, ComplaintType.ROAD_DAMAGE}),
    frozenset({ComplaintType.FLOODING, ComplaintType.WATER_PIPE}),
    frozenset({ComplaintType.ELECTRICITY, ComplaintType.STREETLIGHT}),
    frozenset({ComplaintType.WASTE, ComplaintType.SIDEWALK}),
}

# Subcategory → ComplaintType mapping for image results
_SUBCAT_TO_TYPE: dict = {
    "pothole":            ComplaintType.POTHOLE,
    "road_damage":        ComplaintType.ROAD_DAMAGE,
    "flooding":           ComplaintType.FLOODING,
    "waste_accumulation": ComplaintType.WASTE,
    "outage":             ComplaintType.ELECTRICITY,
    "traffic_light":      ComplaintType.TRAFFIC_LIGHT,
    "pipe_leak":          ComplaintType.WATER_PIPE,
    "sidewalk_damage":    ComplaintType.SIDEWALK,
    "streetlight":        ComplaintType.STREETLIGHT,
    "other":              ComplaintType.OTHER,
}

# ── Primary path (CLIP-native) thresholds ────────────────────────────────────
_SUPPORT_THRESHOLD    = 0.55   # cosine ≥ this + compatible types → SUPPORTS
_CONTRADICT_THRESHOLD = 0.25   # cosine < this + incompatible types → CONTRADICTS

# ── Fallback path (random projection) penalty ────────────────────────────────
# Scores from the fallback path are unreliable cross-model comparisons.
# Scale them down so they never cross the SUPPORT threshold on their own.
_FALLBACK_SCALE = 0.7


class ModalAlignmentComputer:
    """
    Produces TextImageAlignment for a single complaint.

    Uses CLIP-native cosine similarity when clip_text_embedding is available
    in image_result (preferred).  Falls back to a random-projection
    approximation otherwise, with a reduced score and a capped status.
    """

    def compute(
        self,
        text_result: TextUnderstandingResult,
        image_result: Optional[ImageUnderstandingResult],
    ) -> TextImageAlignment:

        complaint_id = text_result.complaint_id

        # ── No image ─────────────────────────────────────────────────────────
        if image_result is None or not image_result.image_present:
            return TextImageAlignment(
                complaint_id=complaint_id,
                alignment_status=AlignmentStatus.NO_IMAGE,
                alignment_score=0.0,
                text_issue_type=text_result.issue_type,
                reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                reconciliation_note="No image submitted.",
            )

        # ── Unusable image ────────────────────────────────────────────────────
        if not image_result.image_quality.usable:
            return TextImageAlignment(
                complaint_id=complaint_id,
                alignment_status=AlignmentStatus.NO_IMAGE,
                alignment_score=0.0,
                text_issue_type=text_result.issue_type,
                reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                reconciliation_note=(
                    f"Image present but unusable: {image_result.image_quality.issues}"
                ),
            )

        # ── Choose alignment path ─────────────────────────────────────────────
        clip_text_emb = image_result.clip_text_embedding
        image_emb     = image_result.image_embedding
        use_clip_native = bool(clip_text_emb and image_emb)

        alignment_score = 0.0
        used_fallback   = False

        if use_clip_native:
            # PRIMARY PATH — both vectors are 512-dim CLIP, same embedding space.
            # Direct cosine is the correct similarity measure.
            alignment_score = round(_cosine(clip_text_emb, image_emb), 4)
        elif image_emb and text_result.text_embedding:
            # FALLBACK PATH — cross-model approximation (unreliable).
            # Project 512-dim CLIP image → 768-dim sentence-transformer space
            # via a random linear projection.  Score is scaled down and the
            # alignment status will be capped at UNCERTAIN regardless of value.
            from .fusion import project_image_embedding
            image_proj      = project_image_embedding(image_emb)
            raw_score       = _cosine(text_result.text_embedding, image_proj)
            alignment_score = round(raw_score * _FALLBACK_SCALE, 4)
            used_fallback   = True

        # ── Resolve image issue type ──────────────────────────────────────────
        img_subcat   = image_result.visual_understanding.visual_subcategory
        image_issue_type: Optional[ComplaintType] = _SUBCAT_TO_TYPE.get(img_subcat)
        text_issue_type = text_result.issue_type

        types_match     = (image_issue_type == text_issue_type)
        types_adjacent  = (
            image_issue_type is not None
            and frozenset({text_issue_type, image_issue_type}) in _ADJACENT_PAIRS
        )
        types_compatible = types_match or types_adjacent

        # ── Classify alignment status ─────────────────────────────────────────
        alignment_status, conflict_detected, conflict_reason = _classify_alignment(
            score=alignment_score,
            types_compatible=types_compatible,
            types_match=types_match,
            types_adjacent=types_adjacent,
            image_type=image_issue_type,
            cap_at_uncertain=used_fallback,
        )

        if used_fallback and conflict_reason is None:
            conflict_reason = (
                "Alignment score computed via cross-model random projection "
                "(MVP fallback — complaint text was not sent to IEP-2). "
                "Result is indicative only; do not use as evidence."
            )

        reconciliation_status, reconciliation_note = _reconcile(
            alignment_status=alignment_status,
            score=alignment_score,
            types_match=types_match,
            types_compatible=types_compatible,
            text_conf=text_result.confidence,
            image_conf=image_result.visual_understanding.confidence,
            used_fallback=used_fallback,
        )

        return TextImageAlignment(
            complaint_id=complaint_id,
            alignment_status=alignment_status,
            alignment_score=alignment_score,
            text_issue_type=text_issue_type,
            image_issue_type=img_subcat or None,
            text_subcategory=text_result.subcategory,
            image_subcategory=img_subcat,
            conflict_detected=conflict_detected,
            conflict_reason=conflict_reason,
            reconciliation_status=reconciliation_status,
            reconciliation_note=reconciliation_note,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na  = math.sqrt(sum(x * x for x in a)) + 1e-8
    nb  = math.sqrt(sum(x * x for x in b)) + 1e-8
    return dot / (na * nb)


def _classify_alignment(
    score: float,
    types_compatible: bool,
    types_match: bool,
    types_adjacent: bool,
    image_type,
    cap_at_uncertain: bool,
) -> tuple:
    """
    Returns (AlignmentStatus, conflict_detected, conflict_reason).

    When cap_at_uncertain=True (fallback path), the status is capped at
    UNCERTAIN — the cross-model projection score is not reliable enough
    to assert SUPPORTS or CONTRADICTS.
    """
    conflict_detected = False
    conflict_reason   = None

    if image_type is None:
        return AlignmentStatus.UNCERTAIN, False, None

    if cap_at_uncertain:
        # Fallback path: acknowledge the image is present but don't assert alignment.
        return AlignmentStatus.UNCERTAIN, False, None

    # Type match is the primary signal — CLIP cosine on raw complaint text is
    # unreliable because CLIP was trained on image captions, not complaint prose.
    if types_match:
        return AlignmentStatus.SUPPORTS, False, None

    if types_adjacent:
        return AlignmentStatus.UNCERTAIN, False, None

    # Types differ — use cosine as secondary evidence.
    if score >= _SUPPORT_THRESHOLD:
        # High visual similarity but different types — flag as unrelated
        conflict_detected = True
        conflict_reason = (
            f"CLIP similarity is high ({score:.2f}) but issue types differ: "
            f"image={image_type}"
        )
        return AlignmentStatus.UNRELATED, conflict_detected, conflict_reason

    if score < _CONTRADICT_THRESHOLD:
        conflict_detected = True
        conflict_reason = f"Low CLIP similarity ({score:.2f}) and mismatched types."
        return AlignmentStatus.CONTRADICTS, conflict_detected, conflict_reason

    return AlignmentStatus.UNCERTAIN, False, None


def _reconcile(
    alignment_status: AlignmentStatus,
    score: float,
    types_match: bool,
    types_compatible: bool,
    text_conf: float,
    image_conf: float,
    used_fallback: bool,
) -> tuple:
    if alignment_status == AlignmentStatus.NO_IMAGE:
        return ReconciliationStatus.INSUFFICIENT_EVIDENCE, "No image."

    # Fallback-path results are never promoted to TEXT_AND_IMAGE_SUPPORT.
    if used_fallback:
        return (
            ReconciliationStatus.INSUFFICIENT_EVIDENCE,
            "Alignment computed via cross-model projection (fallback). "
            "Re-send complaint text to IEP-2 to enable CLIP-native alignment.",
        )

    both_strong  = text_conf >= 0.70 and image_conf >= 0.70
    image_strong = image_conf >= 0.75 and text_conf < 0.55
    text_strong  = text_conf >= 0.75 and image_conf < 0.50

    if alignment_status == AlignmentStatus.SUPPORTS and both_strong:
        return (
            ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
            "Both text and image confidently describe the same issue (CLIP-native).",
        )
    if alignment_status == AlignmentStatus.SUPPORTS and image_strong:
        return (
            ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT,
            "Image is strong; text is vague but CLIP similarity confirms same issue.",
        )
    if alignment_status == AlignmentStatus.SUPPORTS and text_strong:
        return (
            ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE,
            "Text is strong; image confidence is lower but compatible.",
        )
    if alignment_status == AlignmentStatus.SUPPORTS:
        return (
            ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
            "Both modalities support the same issue type (CLIP-native).",
        )
    if alignment_status == AlignmentStatus.CONTRADICTS:
        return (
            ReconciliationStatus.MODAL_CONFLICT,
            "CLIP similarity and type comparison indicate different issues.",
        )
    if alignment_status in (AlignmentStatus.UNRELATED, AlignmentStatus.UNCERTAIN):
        if text_strong:
            return (
                ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE,
                "Text is reliable; image is ambiguous or unrelated.",
            )
        if image_strong:
            return (
                ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT,
                "Image is informative; text is vague.",
            )

    return (
        ReconciliationStatus.INSUFFICIENT_EVIDENCE,
        "Neither modality is strong enough to determine alignment.",
    )


import math
from typing import Optional

from cedarfix_shared.schemas import (
    AlignmentStatus,
    ComplaintType,
    ImageUnderstandingResult,
    ReconciliationStatus,
    TextImageAlignment,
    TextUnderstandingResult,
)

# ---------------------------------------------------------------------------
# Adjacent issue-type pairs (text ↔ image mismatch is tolerable between these)
# ---------------------------------------------------------------------------

_ADJACENT_PAIRS = {
    frozenset({ComplaintType.POTHOLE, ComplaintType.ROAD_DAMAGE}),
    frozenset({ComplaintType.FLOODING, ComplaintType.WATER_PIPE}),
    frozenset({ComplaintType.ELECTRICITY, ComplaintType.STREETLIGHT}),
    frozenset({ComplaintType.WASTE, ComplaintType.SIDEWALK}),
}

# Subcategory → ComplaintType mapping for image results
_SUBCAT_TO_TYPE: dict = {
    "pothole":          ComplaintType.POTHOLE,
    "road_damage":      ComplaintType.ROAD_DAMAGE,
    "flooding":         ComplaintType.FLOODING,
    "waste_accumulation": ComplaintType.WASTE,
    "outage":           ComplaintType.ELECTRICITY,
    "traffic_light":    ComplaintType.TRAFFIC_LIGHT,
    "pipe_leak":        ComplaintType.WATER_PIPE,
    "sidewalk_damage":  ComplaintType.SIDEWALK,
    "streetlight":      ComplaintType.STREETLIGHT,
    "other":            ComplaintType.OTHER,
}

# Thresholds
_SUPPORT_THRESHOLD = 0.55        # cosine sim above this → SUPPORTS (if types compatible)
_CONTRADICT_THRESHOLD = 0.25     # cosine sim below this AND types differ → CONTRADICTS


# ---------------------------------------------------------------------------
# ModalAlignmentComputer
# ---------------------------------------------------------------------------

class ModalAlignmentComputer:
    """
    Produces TextImageAlignment for a single complaint.

    Called inside IEP-3 after both IEP-1 and IEP-2 have completed.
    """

    def compute(
        self,
        text_result: TextUnderstandingResult,
        image_result: Optional[ImageUnderstandingResult],
    ) -> TextImageAlignment:

        complaint_id = text_result.complaint_id

        # ── No image ─────────────────────────────────────────────────────────
        if image_result is None or not image_result.image_present:
            return TextImageAlignment(
                complaint_id=complaint_id,
                alignment_status=AlignmentStatus.NO_IMAGE,
                alignment_score=0.0,
                text_issue_type=text_result.issue_type,
                reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                reconciliation_note="No image submitted.",
            )

        # ── Unusable image ────────────────────────────────────────────────────
        if not image_result.image_quality.usable:
            return TextImageAlignment(
                complaint_id=complaint_id,
                alignment_status=AlignmentStatus.NO_IMAGE,
                alignment_score=0.0,
                text_issue_type=text_result.issue_type,
                reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE,
                reconciliation_note=(
                    f"Image present but unusable: {image_result.image_quality.issues}"
                ),
            )

        # ── Compute cosine similarity between text embedding and projected image emb ──
        text_emb = text_result.text_embedding
        image_emb = image_result.image_embedding

        alignment_score = 0.0
        if text_emb and image_emb:
            # Project image embedding to same 768-dim space as text using
            # the same random projection matrix used in fusion.py
            # (import lazily to avoid circular dependency)
            from .fusion import project_image_embedding
            image_proj = project_image_embedding(image_emb)
            alignment_score = round(_cosine(text_emb, image_proj), 4)

        # ── Resolve image issue type from visual subcategory ──────────────────
        img_subcat = image_result.visual_understanding.visual_subcategory
        image_issue_type: Optional[ComplaintType] = _SUBCAT_TO_TYPE.get(img_subcat)
        text_issue_type = text_result.issue_type

        types_match = (image_issue_type == text_issue_type)
        types_adjacent = (
            image_issue_type is not None
            and frozenset({text_issue_type, image_issue_type}) in _ADJACENT_PAIRS
        )
        types_compatible = types_match or types_adjacent

        # ── Decision rules ────────────────────────────────────────────────────
        alignment_status, conflict_detected, conflict_reason = _classify_alignment(
            alignment_score, types_compatible, types_match, image_issue_type
        )

        reconciliation_status, reconciliation_note = _reconcile(
            alignment_status,
            alignment_score,
            types_match,
            types_compatible,
            text_result.confidence,
            image_result.visual_understanding.confidence,
        )

        return TextImageAlignment(
            complaint_id=complaint_id,
            alignment_status=alignment_status,
            alignment_score=alignment_score,
            text_issue_type=text_issue_type,
            image_issue_type=img_subcat or None,
            text_subcategory=text_result.subcategory,
            image_subcategory=img_subcat,
            conflict_detected=conflict_detected,
            conflict_reason=conflict_reason,
            reconciliation_status=reconciliation_status,
            reconciliation_note=reconciliation_note,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _cosine(a: list, b: list) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) + 1e-8
    nb = math.sqrt(sum(x * x for x in b)) + 1e-8
    return dot / (na * nb)


def _classify_alignment(
    score: float,
    types_compatible: bool,
    types_match: bool,
    image_type,
) -> tuple:
    conflict_detected = False
    conflict_reason = None

    if image_type is None:
        return AlignmentStatus.UNCERTAIN, False, None

    if score >= _SUPPORT_THRESHOLD and types_compatible:
        return AlignmentStatus.SUPPORTS, False, None

    if score >= _SUPPORT_THRESHOLD and not types_compatible:
        conflict_detected = True
        conflict_reason = (
            f"Embedding similarity is high ({score:.2f}) but "
            f"issue types differ: text={None}, image={image_type}"
        )
        return AlignmentStatus.UNRELATED, conflict_detected, conflict_reason

    if score < _CONTRADICT_THRESHOLD and not types_match:
        conflict_detected = True
        conflict_reason = (
            f"Low embedding similarity ({score:.2f}) and mismatched types."
        )
        return AlignmentStatus.CONTRADICTS, conflict_detected, conflict_reason

    if score < _CONTRADICT_THRESHOLD and types_match:
        return AlignmentStatus.UNRELATED, False, "Image appears unrelated despite matching type."

    return AlignmentStatus.UNCERTAIN, False, None


def _reconcile(
    alignment_status: AlignmentStatus,
    score: float,
    types_match: bool,
    types_compatible: bool,
    text_conf: float,
    image_conf: float,
) -> tuple:
    if alignment_status == AlignmentStatus.NO_IMAGE:
        return ReconciliationStatus.INSUFFICIENT_EVIDENCE, "No image."

    both_strong = text_conf >= 0.70 and image_conf >= 0.70
    image_strong = image_conf >= 0.75 and text_conf < 0.55
    text_strong = text_conf >= 0.75 and image_conf < 0.50

    if alignment_status == AlignmentStatus.SUPPORTS and both_strong:
        return (
            ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
            "Both text and image confidently describe the same issue.",
        )

    if alignment_status == AlignmentStatus.SUPPORTS and image_strong:
        return (
            ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT,
            "Image is strong; text is vague but compatible.",
        )

    if alignment_status == AlignmentStatus.SUPPORTS and text_strong:
        return (
            ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE,
            "Text is strong; image confidence is lower but compatible.",
        )

    if alignment_status == AlignmentStatus.SUPPORTS:
        return (
            ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT,
            "Both modalities support the same issue type.",
        )

    if alignment_status == AlignmentStatus.CONTRADICTS:
        return (
            ReconciliationStatus.MODAL_CONFLICT,
            "Text and image describe different infrastructure issues.",
        )

    if alignment_status in (AlignmentStatus.UNRELATED, AlignmentStatus.UNCERTAIN):
        if text_strong:
            return (
                ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE,
                "Text is reliable; image is ambiguous or unrelated.",
            )
        if image_strong:
            return (
                ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT,
                "Image is informative; text is vague.",
            )

    return (
        ReconciliationStatus.INSUFFICIENT_EVIDENCE,
        "Neither modality is strong enough to determine alignment.",
    )
