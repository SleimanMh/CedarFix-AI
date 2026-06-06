from __future__ import annotations

from fastapi.testclient import TestClient


class FakeQdrant:
    def __init__(self):
        self.calls = []

    async def store_text(self, complaint_id, vector, payload):
        self.calls.append(("text", complaint_id, vector, payload))

    async def store_clip_text(self, complaint_id, vector, payload):
        self.calls.append(("clip_text", complaint_id, vector, payload))

    async def store_clip_image(self, complaint_id, vector, payload):
        self.calls.append(("clip_image", complaint_id, vector, payload))


class FakeRetriever:
    def __init__(self):
        self.received = None

    async def retrieve(self, **kwargs):
        self.received = kwargs
        return []


def test_embedding_api_stores_text_and_clip_text_then_returns_result(import_service_module, monkeypatch):
    main = import_service_module("embedding_service", "app.main", qdrant=True, ml=True)
    fake_qdrant = FakeQdrant()
    fake_retriever = FakeRetriever()
    monkeypatch.setattr(main, "qdrant", fake_qdrant)
    monkeypatch.setattr(main, "retriever", fake_retriever)
    monkeypatch.setattr(main, "_encode_clip_text", lambda text: [0.3, 0.4])
    client = TestClient(main.app)

    response = client.post(
        "/embed",
        json={
            "complaint_id": "c1",
            "text_result": {
                "complaint_id": "c1",
                "original_text": "Broken road near Hamra",
                "normalized_text": "broken road near hamra",
                "summary": "Broken road near Hamra",
                "category": "roads",
                "subcategory": "road_damage",
                "issue_type": "road_damage",
                "severity": "HIGH",
                "text_embedding": [0.1, 0.2],
                "confidence": 0.9,
            },
            "image_result": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["complaint_id"] == "c1"
    assert payload["text_embedding"] == [0.1, 0.2]
    assert payload["clip_text_embedding"] == [0.3, 0.4]
    assert payload["candidates"] == []
    assert [call[0] for call in fake_qdrant.calls] == ["text", "clip_text"]
    assert fake_retriever.received["image_present"] is False
