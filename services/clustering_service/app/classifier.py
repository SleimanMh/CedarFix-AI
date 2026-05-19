"""Duplicate/near-duplicate classifier based on similarity thresholds."""

from cedarfix_shared.schemas import ClusteringResult, DuplicateStatus
from typing import List


class DuplicateClassifier:
    def __init__(self, duplicate_threshold: float, near_duplicate_threshold: float):
        self.dup_threshold = duplicate_threshold
        self.near_dup_threshold = near_duplicate_threshold

    def classify(
        self, complaint_id: str, similar_complaints: List[dict], top_similarity_score: float
    ) -> ClusteringResult:

        if top_similarity_score >= self.dup_threshold:
            duplicate_of = similar_complaints[0]["complaint_id"] if similar_complaints else None
            return ClusteringResult(
                complaint_id=complaint_id,
                duplicate_status=DuplicateStatus.DUPLICATE,
                duplicate_of=duplicate_of,
                cluster_size=len(similar_complaints),
                cluster_trend="stable",
                escalation_signal=False,
                processing_ms=0,
            )

        if top_similarity_score >= self.near_dup_threshold:
            cluster_size = len([s for s in similar_complaints if s["similarity_score"] >= self.near_dup_threshold])
            escalate = cluster_size >= 5
            return ClusteringResult(
                complaint_id=complaint_id,
                duplicate_status=DuplicateStatus.NEAR_DUPLICATE,
                cluster_size=cluster_size,
                cluster_trend="growing" if escalate else "stable",
                escalation_signal=escalate,
                processing_ms=0,
            )

        return ClusteringResult(
            complaint_id=complaint_id,
            duplicate_status=DuplicateStatus.NEW,
            cluster_size=0,
            processing_ms=0,
        )
