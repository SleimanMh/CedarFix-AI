from __future__ import annotations

from fastapi.testclient import TestClient

from cedarfix_shared.schemas import RoutingEntity, RoutingResult


class FakeRouter:
    async def route_async(self, **kwargs):
        return RoutingResult(
            complaint_id=kwargs["complaint_id"],
            primary_entity=RoutingEntity.OGERO,
            primary_confidence=0.91,
            routing_rationale=["mocked"],
            retrieved_sources=["doc-1"],
            routing_source="rag_retrieval",
            auto_routed=True,
            requires_review=False,
            processing_ms=0,
        )


def test_routing_api_health_and_route(import_service_module, monkeypatch):
    main = import_service_module("routing_engine", "app.main", qdrant=True)
    monkeypatch.setattr(main, "router", FakeRouter())
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "routing-engine"

    response = client.post(
        "/route",
        json={
            "complaint_id": "c1",
            "complaint_type": "telecom_outage",
            "original_text": "Internet outage in Beirut",
            "extracted_keywords": ["internet"],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["primary_entity"] == "Ogero"
    assert body["auto_routed"] is True

