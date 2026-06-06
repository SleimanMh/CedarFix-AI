from __future__ import annotations

from datetime import datetime, timedelta, timezone

from cedarfix_shared.schemas import (
    CanonicalComplaint,
    CanonicalLocationJSON,
    ClusterActionEnum,
    ClusterGrowthSignal,
    DuplicateDecision,
    DuplicateDecisionEnum,
)


def _canonical() -> CanonicalComplaint:
    return CanonicalComplaint(
        complaint_id="incoming",
        issue_type="road_damage",
        location=CanonicalLocationJSON(district="Beirut"),
    )


def _cluster(cluster_cls, cluster_id="cluster-1", member_count=1):
    return cluster_cls(
        id=cluster_id,
        complaint_type="road_damage",
        dominant_district="Beirut",
        member_count=member_count,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )


class FakeQuery:
    def __init__(self, cluster):
        self.cluster = cluster
        self.filters = []
        self.ordered = False

    def filter(self, *conditions):
        self.filters.extend(conditions)
        return self

    def order_by(self, *_args):
        self.ordered = True
        return self

    def first(self):
        return self.cluster


class FakeDB:
    def __init__(self, cluster=None):
        self.query_obj = FakeQuery(cluster)
        self.added = []
        self.commits = 0

    def query(self, _model):
        return self.query_obj

    def add(self, record):
        self.added.append(record)

    def commit(self):
        self.commits += 1


def _module_and_cluster(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    assigner_mod = import_service_module("clustering_service", "app.cluster_assigner")
    from cedarfix_shared.db import Cluster

    return assigner_mod, Cluster


def test_duplicate_decision_joins_existing_cluster_and_escalates(import_service_module, monkeypatch):
    assigner_mod, cluster_cls = _module_and_cluster(import_service_module, monkeypatch)
    cluster = _cluster(cluster_cls, member_count=1)
    db = FakeDB(cluster)
    decision = DuplicateDecision(
        complaint_id="incoming",
        duplicate_decision=DuplicateDecisionEnum.DUPLICATE,
        matched_complaint_id="existing",
        matched_cluster_id="cluster-1",
    )

    assignment = assigner_mod.ClusterAssigner().assign(decision, _canonical(), db)

    assert assignment.cluster_action == ClusterActionEnum.JOIN_EXISTING_CLUSTER
    assert assignment.cluster_size_before == 1
    assert assignment.cluster_size_after == 2
    assert assignment.cluster_growth_signal == ClusterGrowthSignal.GROWING
    assert assignment.priority_escalation_signal is True
    assert assignment.linked_to_complaint_id == "existing"
    assert cluster.member_count == 2
    assert db.commits == 1


def test_duplicate_with_missing_cluster_creates_new_cluster(import_service_module, monkeypatch):
    assigner_mod, _cluster_cls = _module_and_cluster(import_service_module, monkeypatch)
    db = FakeDB(cluster=None)
    decision = DuplicateDecision(
        complaint_id="incoming",
        duplicate_decision=DuplicateDecisionEnum.DUPLICATE,
        matched_cluster_id="missing",
    )

    assignment = assigner_mod.ClusterAssigner().assign(decision, _canonical(), db)

    assert assignment.cluster_action == ClusterActionEnum.CREATE_NEW_CLUSTER
    assert assignment.cluster_size_after == 1
    assert db.added[0].complaint_type == "road_damage"
    assert db.commits == 1


def test_new_incident_reuses_recent_nearby_cluster(import_service_module, monkeypatch):
    assigner_mod, cluster_cls = _module_and_cluster(import_service_module, monkeypatch)
    cluster = _cluster(cluster_cls, cluster_id="nearby", member_count=2)
    db = FakeDB(cluster)
    decision = DuplicateDecision(
        complaint_id="incoming",
        duplicate_decision=DuplicateDecisionEnum.NEW_INCIDENT,
    )

    assignment = assigner_mod.ClusterAssigner().assign(decision, _canonical(), db)

    assert assignment.cluster_action == ClusterActionEnum.JOIN_EXISTING_CLUSTER
    assert assignment.cluster_id == "nearby"
    assert db.query_obj.ordered is True
    assert db.commits == 1


def test_admin_review_assignment_does_not_mutate_clusters(import_service_module, monkeypatch):
    assigner_mod, cluster_cls = _module_and_cluster(import_service_module, monkeypatch)
    db = FakeDB(_cluster(cluster_cls))
    decision = DuplicateDecision(
        complaint_id="incoming",
        duplicate_decision=DuplicateDecisionEnum.NEEDS_ADMIN_REVIEW,
        matched_cluster_id="cluster-1",
        matched_complaint_id="existing",
        decision_reason="modal conflict",
    )

    assignment = assigner_mod.ClusterAssigner().assign(decision, _canonical(), db)

    assert assignment.cluster_action == ClusterActionEnum.FLAG_FOR_ADMIN_REVIEW
    assert assignment.priority_escalation_signal is True
    assert assignment.cluster_note == "modal conflict"
    assert assignment.linked_to_complaint_id == "existing"
    assert db.commits == 0
    assert db.added == []
