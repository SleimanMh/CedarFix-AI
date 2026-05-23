"""
Multimodal Duplicate Classifier — IEP-4

Orchestrates the full multimodal deduplication + cluster assignment pipeline
for a single incoming complaint.  Replaces the old simple threshold-based
DuplicateClassifier.

Pipeline:
  1. Score all candidates (MultimodalScorer)
  2. Reconcile each candidate's evidence (ReconciliationEngine)
  3. Decide 4-state outcome (DecisionEngine)
  4. Assign/create cluster (ClusterAssigner)
  5. Build backwards-compatible MultimodalClusteringResult

Backwards compatibility:
  The returned MultimodalClusteringResult still has all the old ClusteringResult
  fields so IEP-5 / IEP-6 / IEP-7 don't need to change.
"""

from typing import List, Optional
from sqlalchemy.orm import Session

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    ClusteringResult,
    DuplicateCandidate,
    DuplicateDecisionEnum,
    DuplicateStatus,
    EmbeddingServiceResult,
    MultimodalClusteringResult,
    TextImageAlignment,
)

from .decision import DecisionEngine
from .reconciler import ReconciliationEngine
from .scorer import MultimodalScorer
from .cluster_assigner import ClusterAssigner


class MultimodalDuplicateClassifier:
    """
    Replaces the old DuplicateClassifier.  All thresholds are now encoded
    in scorer.py / decision.py rather than in env vars.
    """

    def __init__(self):
        self._scorer      = MultimodalScorer()
        self._reconciler  = ReconciliationEngine()
        self._decider     = DecisionEngine()
        self._assigner    = ClusterAssigner()

    def classify(
        self,
        embed_result: EmbeddingServiceResult,
        db: Session,
    ) -> MultimodalClusteringResult:
        """
        Main entry point.  Returns a MultimodalClusteringResult that is a
        strict superset of the old ClusteringResult.
        """
        canonical   = embed_result.canonical
        alignment   = embed_result.alignment
        candidates  = embed_result.candidates
        text_emb    = embed_result.text_embedding
        image_emb   = embed_result.image_embedding
        image_present = bool(image_emb)

        # ── 1. Score ──────────────────────────────────────────────────────────
        scored: List[DuplicateCandidate] = []
        for raw in candidates:
            dc = self._scorer.score(
                canonical=canonical,
                candidate=raw,
                text_embedding=text_emb,
                image_embedding=image_emb,
                image_present=image_present,
            )
            # ── 2. Reconcile ─────────────────────────────────────────────────
            rec_status = self._reconciler.reconcile(dc, alignment)
            dc.per_candidate_reconciliation = rec_status
            scored.append(dc)

        # ── 3. Decide ─────────────────────────────────────────────────────────
        decision = self._decider.decide(scored, alignment)

        # ── 4. Cluster assignment ─────────────────────────────────────────────
        assignment = self._assigner.assign(decision, canonical, db)

        # ── 5. Map to backwards-compatible output ─────────────────────────────
        dup_status = _decision_to_dup_status(decision.duplicate_decision)
        duplicate_of = (
            decision.matched_complaint_id
            if decision.duplicate_decision == DuplicateDecisionEnum.DUPLICATE
            else None
        )

        return MultimodalClusteringResult(
            # ── Old ClusteringResult fields ────────────────────────────────
            complaint_id=canonical.complaint_id,
            duplicate_status=dup_status,
            duplicate_of=duplicate_of,
            cluster_id=assignment.cluster_id,
            cluster_size=assignment.cluster_size_after,
            cluster_trend=assignment.cluster_growth_signal.value,
            escalation_signal=assignment.priority_escalation_signal,
            processing_ms=0,   # filled in by main.py
            # ── New multimodal fields ─────────────────────────────────────
            duplicate_decision=decision.duplicate_decision,
            decision_confidence=decision.decision_confidence,
            matched_complaint_id=decision.matched_complaint_id,
            matched_cluster_id=decision.matched_cluster_id,
            decision_reason=decision.decision_reason,
            evidence=decision.evidence,
            cluster_assignment=assignment,
            modal_alignment=alignment,
            top_candidates=scored,
            requires_admin_review=decision.requires_admin_review,
            review_reasons=decision.review_reasons,
            canonical=canonical,
        )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _decision_to_dup_status(decision: DuplicateDecisionEnum) -> DuplicateStatus:
    mapping = {
        DuplicateDecisionEnum.DUPLICATE:            DuplicateStatus.DUPLICATE,
        DuplicateDecisionEnum.RELATED_SAME_CLUSTER: DuplicateStatus.RELATED_SAME_CLUSTER,
        DuplicateDecisionEnum.NEW_INCIDENT:         DuplicateStatus.NEW,
        DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW:   DuplicateStatus.NEEDS_ADMIN_REVIEW,
    }
    return mapping.get(decision, DuplicateStatus.NEW)

