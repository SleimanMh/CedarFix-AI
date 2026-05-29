"""
Cluster Assigner — IEP-4

Maps a DuplicateDecision to a ClusterAssignment, updating the PostgreSQL
`clusters` table accordingly.

Key behaviours:
  DUPLICATE             → JOIN_EXISTING_CLUSTER; always increment member_count
                          (per design: even duplicates count toward cluster growth)
  RELATED_SAME_CLUSTER  → JOIN_EXISTING_CLUSTER; increment member_count
  NEW_INCIDENT          → search for nearby cluster by type+district; join if
                          found, otherwise CREATE_NEW_CLUSTER
  NEEDS_ADMIN_REVIEW    → FLAG_FOR_ADMIN_REVIEW; no cluster mutation until resolved
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from cedarfix_shared.db import Cluster
from cedarfix_shared.schemas import (
    AdminReviewJSON,
    CanonicalComplaint,
    ClusterActionEnum,
    ClusterAssignment,
    ClusterGrowthSignal,
    DuplicateDecision,
    DuplicateDecisionEnum,
)

_ESCALATION_SIZE     = 2   # flag cluster as escalated when 2+ complaints share the same incident
_ESCALATION_GROWTH   = 2
_GROWTH_WINDOW_HOURS = 24


def _now_utc() -> datetime:
    return datetime.now(tz=timezone.utc)


class ClusterAssigner:

    def assign(
        self,
        decision: DuplicateDecision,
        canonical: CanonicalComplaint,
        db: Session,
    ) -> ClusterAssignment:

        action = decision.duplicate_decision

        if action in (DuplicateDecisionEnum.DUPLICATE, DuplicateDecisionEnum.RELATED_SAME_CLUSTER):
            cluster_id = decision.matched_cluster_id
            linked_to = decision.matched_complaint_id if action == DuplicateDecisionEnum.DUPLICATE else None
            return self._join_existing(cluster_id, canonical, db, linked_to)

        if action == DuplicateDecisionEnum.NEW_INCIDENT:
            nearby = self._find_nearby_cluster(canonical, db)
            if nearby:
                return self._join_existing(nearby.id, canonical, db, linked_to=None)
            return self._create_new_cluster(canonical, db)

        # NEEDS_ADMIN_REVIEW
        return self._flag_for_review(canonical, decision)

    def _join_existing(
        self,
        cluster_id: Optional[str],
        canonical: CanonicalComplaint,
        db: Session,
        linked_to: Optional[str],
    ) -> ClusterAssignment:
        if not cluster_id:
            return self._create_new_cluster(canonical, db)

        cluster = db.query(Cluster).filter(Cluster.id == cluster_id).first()
        if not cluster:
            return self._create_new_cluster(canonical, db)

        size_before = cluster.member_count
        cluster.member_count += 1
        cluster.updated_at = _now_utc()
        cluster.last_run_at = _now_utc()
        growth_signal = _compute_growth_signal(cluster)
        cluster.trend = growth_signal.value
        db.commit()

        escalate = cluster.member_count >= _ESCALATION_SIZE or (
            growth_signal == ClusterGrowthSignal.GROWING
        )

        return ClusterAssignment(
            complaint_id=canonical.complaint_id,
            cluster_action=ClusterActionEnum.JOIN_EXISTING_CLUSTER,
            cluster_id=cluster_id,
            cluster_type=cluster.complaint_type,
            cluster_location=cluster.dominant_district,
            cluster_size_before=size_before,
            cluster_size_after=cluster.member_count,
            cluster_growth_signal=growth_signal,
            priority_escalation_signal=escalate,
            linked_to_complaint_id=linked_to,
        )

    def _create_new_cluster(
        self,
        canonical: CanonicalComplaint,
        db: Session,
    ) -> ClusterAssignment:
        new_id = str(uuid.uuid4())
        now = _now_utc()
        cluster = Cluster(
            id=new_id,
            created_at=now,
            updated_at=now,
            complaint_type=canonical.issue_type.value,
            dominant_district=canonical.location.district,
            member_count=1,
            trend=ClusterGrowthSignal.NEW.value,
            last_run_at=now,
        )
        db.add(cluster)
        db.commit()

        return ClusterAssignment(
            complaint_id=canonical.complaint_id,
            cluster_action=ClusterActionEnum.CREATE_NEW_CLUSTER,
            cluster_id=new_id,
            cluster_type=canonical.issue_type.value,
            cluster_location=canonical.location.district,
            cluster_size_before=0,
            cluster_size_after=1,
            cluster_growth_signal=ClusterGrowthSignal.NEW,
            priority_escalation_signal=False,
        )

    def _flag_for_review(
        self,
        canonical: CanonicalComplaint,
        decision: DuplicateDecision,
    ) -> ClusterAssignment:
        return ClusterAssignment(
            complaint_id=canonical.complaint_id,
            cluster_action=ClusterActionEnum.FLAG_FOR_ADMIN_REVIEW,
            cluster_id=decision.matched_cluster_id,
            cluster_size_before=0,
            cluster_size_after=0,
            cluster_growth_signal=ClusterGrowthSignal.STABLE,
            priority_escalation_signal=True,
            cluster_note=decision.decision_reason,
            linked_to_complaint_id=decision.matched_complaint_id,
        )

    def _find_nearby_cluster(
        self,
        canonical: CanonicalComplaint,
        db: Session,
    ) -> Optional[Cluster]:
        cutoff = _now_utc() - timedelta(hours=48)
        return (
            db.query(Cluster)
            .filter(
                Cluster.complaint_type == canonical.issue_type.value,
                Cluster.dominant_district == canonical.location.district,
                Cluster.updated_at >= cutoff,
            )
            .order_by(Cluster.updated_at.desc())
            .first()
        )


def _compute_growth_signal(cluster: Cluster) -> ClusterGrowthSignal:
    if cluster.member_count < 2:
        return ClusterGrowthSignal.NEW
    now = _now_utc()
    updated = cluster.updated_at
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    if (now - updated) <= timedelta(hours=_GROWTH_WINDOW_HOURS) and cluster.member_count >= _ESCALATION_GROWTH:
        return ClusterGrowthSignal.GROWING
    return ClusterGrowthSignal.STABLE

