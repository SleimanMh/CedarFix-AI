"""
Reconciliation Engine — IEP-4

Determines the *reconciliation status* for the best-scoring candidate
by examining whether text and image evidence agree or conflict.

Phase 1: threshold rules.
Phase 2: Replace with a small calibrated classifier trained on
         admin-labelled resolution decisions.
"""

from cedarfix_shared.schemas import (
    DuplicateCandidate,
    ReconciliationStatus,
    TextImageAlignment,
    AlignmentStatus,
)

# ---------------------------------------------------------------------------
# Evidence strength thresholds
# ---------------------------------------------------------------------------
_TEXT_STRONG  = 0.75
_TEXT_WEAK    = 0.60
_IMAGE_STRONG = 0.75
_IMAGE_WEAK   = 0.60

_TYPE_MATCH_MIN = 0.80   # minimum issue_type_similarity to count as type-match
_LOC_MIN        = 0.70   # minimum location_similarity for geo override to apply


class ReconciliationEngine:
    """
    Given a scored candidate and the intra-complaint modal alignment,
    return the ReconciliationStatus that best describes how evidence aligns.
    """

    def reconcile(
        self,
        candidate: DuplicateCandidate,
        intra_alignment: TextImageAlignment,
    ) -> ReconciliationStatus:

        s = candidate.similarity_scores
        text_sim  = s.text_similarity
        image_sim = s.image_similarity
        type_sim  = s.issue_type_similarity
        loc_sim   = s.location_similarity

        types_match = type_sim >= _TYPE_MATCH_MIN
        text_strong = text_sim >= _TEXT_STRONG
        image_strong = image_sim >= _IMAGE_STRONG
        text_weak   = text_sim < _TEXT_WEAK
        image_weak  = image_sim < _IMAGE_WEAK

        # ── Rule 1: Both modalities strongly support duplicate ───────────────
        if text_strong and image_strong and types_match:
            return ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT

        # ── Rule 2: Image strong, text weak but geo matches ──────────────────
        #    Vision found the same pothole; the text description is terse/different
        if image_strong and text_weak and loc_sim >= _LOC_MIN and types_match:
            return ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT

        # ── Rule 3: Text strong, no usable image on one side ─────────────────
        #    One complaint had no image — text evidence is the only signal
        if text_strong and image_sim == 0.0:
            return ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE

        # ── Rule 4: Text strong, image weak ──────────────────────────────────
        if text_strong and image_weak and image_sim > 0.0:
            return ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE

        # ── Rule 5: Modal conflict — both present but don't agree ─────────────
        if (
            intra_alignment.alignment_status == AlignmentStatus.CONTRADICTS
            and text_sim > _TEXT_WEAK
            and image_sim > _IMAGE_WEAK
        ):
            return ReconciliationStatus.MODAL_CONFLICT

        # ── Rule 6: Same type, but neither modality is strong ─────────────────
        if types_match and (text_sim >= 0.50 or image_sim >= 0.50):
            return ReconciliationStatus.INSUFFICIENT_EVIDENCE

        # Fallback
        return ReconciliationStatus.INSUFFICIENT_EVIDENCE
