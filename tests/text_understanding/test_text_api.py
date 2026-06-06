from __future__ import annotations

from fastapi.testclient import TestClient

from cedarfix_shared.schemas import TextUnderstandingResult


class FakeTextModel:
    async def analyze(self, complaint_id, text):
        return TextUnderstandingResult(
            complaint_id=complaint_id,
            original_text=text,
            normalized_text=text.lower(),
            language="en",
            summary="Road damage reported.",
            category="roads",
            subcategory="road_damage",
            issue_type="road_damage",
            confidence=0.82,
            text_embedding=[0.1, 0.2],
        )


def test_text_api_health_and_analyze(import_service_module, monkeypatch):
    main = import_service_module("text_understanding", "app.main", ml=True)
    monkeypatch.setattr(main, "model", FakeTextModel())
    client = TestClient(main.app)

    health = client.get("/health").json()
    assert health["service"] == "text-understanding"
    assert health["model_loaded"] is True

    response = client.post("/analyze", json={"complaint_id": "c1", "text": "Broken road near Hamra"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["complaint_id"] == "c1"
    assert payload["issue_type"] == "road_damage"
    assert payload["processing_ms"] >= 0
