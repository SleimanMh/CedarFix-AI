"""
Decision Engine — IEP-4

Makes the final 4-state duplicate decision given the best-scored candidate
and the reconciliation evidence.

States:
  DUPLICATE             — same physical incident; link and increment cluster
  RELATED_SAME_CLUSTER  — related but distinct; join same cluster
  NEW_INCIDENT          — no existing match; start/join based on type+location
  NEEDS_ADMIN_REVIEW    — conflicting or borderline evidence; flag for human

Phase 1: threshold rules + trigger counting.
Phase 2: Replace with a calibrated Platt-scaled logistic model.
"""

from typing import List, Optional

from cedarfix_shared.schemas import (
    DuplicateCandidate,
    DuplicateDecision,
    DuplicateDecisionEnum,
    EvidenceJSON,
    ReconciliationStatus,
    TextImageAlignment,
)

# ---------------------------------------------------------------------------
# Score thresholds
# ---------------------------------------------------------------------------
_DUPLICATE_THRESHOLD  = 0.92
_RELATED_THRESHOLD    = 0.72

# Reconciliation-status confidence multipliers
_STATUS_MULTIPLIER = {
    ReconciliationStatus.TEXT_AND_IMAGE_SUPPORT:      1.00,
    ReconciliationStatus.IMAGE_OVERRIDES_WEAK_TEXT:   0.93,
    ReconciliationStatus.TEXT_OVERRIDES_WEAK_IMAGE:   0.90,
    ReconciliationStatus.MODAL_CONFLICT:              0.75,
    ReconciliationStatus.INSUFFICIENT_EVIDENCE:       0.80,
}


class DecisionEngine:
    """
    Given the list of scored+reconciled candidates, choose the best match
    and produce a DuplicateDecision that matches the shared schema.
    """

    def decide(
        self,
        candidates: List[DuplicateCandidate],
        intra_alignment: TextImageAlignment,
    ) -> DuplicateDecision:

        complaint_id = intra_alignment.complaint_id

        if not candidates:
            return _new_incident(complaint_id, "No candidates retrieved from any search source")

        best = max(candidates, key=lambda c: c.multimodal_score)
        rec_status = best.per_candidate_reconciliation
        multiplier = _STATUS_MULTIPLIER.get(rec_status, 0.80)
        adjusted_score = best.multimodal_score * multiplier

        triggers = _collect_triggers(best, intra_alignment)
        needs_review = (rec_status == ReconciliationStatus.MODAL_CONFLICT or len(triggers) >= 2)

        evidence = EvidenceJSON(
            strongest_signal=rec_status.value,
            text_similarity=best.similarity_scores.text_similarity,
            image_similarity=best.similarity_scores.image_similarity,
            location_similarity=best.similarity_scores.location_similarity,
            time_similarity=best.similarity_scores.time_similarity,
            issue_type_similarity=best.similarity_scores.issue_type_similarity,
            reconciliation_status=rec_status,
        )

        if adjusted_score >= _DUPLICATE_THRESHOLD and not needs_review:
            return DuplicateDecision(
                complaint_id=complaint_id,
                duplicate_decision=DuplicateDecisionEnum.DUPLICATE,
                decision_confidence=round(adjusted_score, 4),
                matched_complaint_id=best.candidate_complaint_id,
                matched_cluster_id=best.candidate_cluster_id,
                decision_reason=f"Strong multimodal match ({adjusted_score:.2f})",
                evidence=evidence,
                requires_admin_review=False,
                review_reasons=[],
            )

        if adjusted_score >= _DUPLICATE_THRESHOLD and needs_review:
            return DuplicateDecision(
                complaint_id=complaint_id,
                duplicate_decision=DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW,
                decision_confidence=round(adjusted_score, 4),
                matched_complaint_id=best.candidate_complaint_id,
                matched_cluster_id=best.candidate_cluster_id,
                decision_reason="High score but conflicting evidence requires human review",
                evidence=evidence,
                requires_admin_review=True,
                review_reasons=triggers,
            )

        if adjusted_score >= _RELATED_THRESHOLD:
            if needs_review:
                return DuplicateDecision(
                    complaint_id=complaint_id,
                    duplicate_decision=DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW,
                    decision_confidence=round(adjusted_score, 4),
                    matched_complaint_id=best.candidate_complaint_id,
                    matched_cluster_id=best.candidate_cluster_id,
                    decision_reason="Boundary score with conflicting modalities",
                    evidence=evidence,
                    requires_admin_review=True,
                    review_reasons=triggers,
                )
            return DuplicateDecision(
                complaint_id=complaint_id,
                duplicate_decision=DuplicateDecisionEnum.RELATED_SAME_CLUSTER,
                decision_confidence=round(adjusted_score, 4),
                matched_complaint_id=best.candidate_complaint_id,
                matched_cluster_id=best.candidate_cluster_id,
                decision_reason=f"Related complaint ({adjusted_score:.2f}); assigning to same cluster",
                evidence=evidence,
                requires_admin_review=False,
                review_reasons=[],
            )

        if len(triggers) >= 2:
            return DuplicateDecision(
                complaint_id=complaint_id,
                duplicate_decision=DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW,
                decision_confidence=round(adjusted_score, 4),
                matched_complaint_id=best.candidate_complaint_id,
                matched_cluster_id=best.candidate_cluster_id,
                decision_reason="Low score with multiple conflicting signals",
                evidence=evidence,
                requires_admin_review=True,
                review_reasons=triggers,
            )

        return _new_incident(
            complaint_id,
            f"Best candidate score {adjusted_score:.2f} below threshold {_RELATED_THRESHOLD}",
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _collect_triggers(best: DuplicateCandidate, intra: TextImageAlignment) -> List[str]:
    found = []
    if best.per_candidate_reconciliation == ReconciliationStatus.MODAL_CONFLICT:
        found.append("modal_conflict")
    score = best.multimodal_score
    if _RELATED_THRESHOLD <= score < _DUPLICATE_THRESHOLD:
        found.append("boundary_score")
    s = best.similarity_scores
    if s.image_similarity >= 0.80 and s.issue_type_similarity < 0.80:
        found.append("type_mismatch_high_image")
    if best.recheck_triggered:
        found.append("recheck_triggered")
    return found


def _new_incident(complaint_id: str, reason: str) -> DuplicateDecision:
    from cedarfix_shared.schemas import EvidenceJSON, ReconciliationStatus
    return DuplicateDecision(
        complaint_id=complaint_id,
        duplicate_decision=DuplicateDecisionEnum.NEW_INCIDENT,
        decision_confidence=1.0,
        matched_complaint_id=None,
        matched_cluster_id=None,
        decision_reason=reason,
        evidence=EvidenceJSON(reconciliation_status=ReconciliationStatus.INSUFFICIENT_EVIDENCE),
        requires_admin_review=False,
        review_reasons=[],
    )

