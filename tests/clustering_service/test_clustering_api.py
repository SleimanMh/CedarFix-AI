from __future__ import annotations

from datetime import datetime, timezone

from fastapi.testclient import TestClient

from cedarfix_shared.schemas import (
    AlignmentStatus,
    CanonicalComplaint,
    CanonicalLocationJSON,
    ClusterAssignment,
    DuplicateDecisionEnum,
    DuplicateStatus,
    EmbeddingServiceResult,
    MultimodalClusteringResult,
    TextImageAlignment,
)


class FakeClassifier:
    def classify(self, embed_result, db):
        return MultimodalClusteringResult(
            complaint_id=embed_result.complaint_id,
            duplicate_status=DuplicateStatus.NEW,
            cluster_id="cluster-1",
            cluster_size=1,
            cluster_trend="NEW",
            escalation_signal=False,
            processing_ms=0,
            duplicate_decision=DuplicateDecisionEnum.NEW_INCIDENT,
            decision_confidence=0.7,
            decision_reason="No candidates.",
            cluster_assignment=ClusterAssignment(
                complaint_id=embed_result.complaint_id,
                cluster_id="cluster-1",
                cluster_size_after=1,
            ),
            modal_alignment=embed_result.alignment,
            canonical=embed_result.canonical,
        )


def _embedding_payload():
    canonical = CanonicalComplaint(
        complaint_id="c1",
        timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        issue_type="road_damage",
        location=CanonicalLocationJSON(district="Beirut"),
    )
    return EmbeddingServiceResult(
        complaint_id="c1",
        canonical=canonical,
        alignment=TextImageAlignment(complaint_id="c1", alignment_status=AlignmentStatus.NO_IMAGE),
        candidates=[],
        text_embedding=[0.1, 0.2],
        clip_text_embedding=[0.3, 0.4],
    ).model_dump(mode="json")


def test_clustering_api_health_and_classify(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    main = import_service_module("clustering_service", "app.main")
    monkeypatch.setattr(main, "_classifier", FakeClassifier())
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "clustering-service"

    response = client.post("/classify", json=_embedding_payload())

    assert response.status_code == 200
    payload = response.json()
    assert payload["complaint_id"] == "c1"
    assert payload["duplicate_status"] == "NEW"
    assert payload["cluster_id"] == "cluster-1"
    assert payload["processing_ms"] >= 0
