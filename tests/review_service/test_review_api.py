from __future__ import annotations

from fastapi.testclient import TestClient


def test_review_api_queue_and_retraining_routes(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    main = import_service_module("review_service", "app.main")

    async def queue(limit=20):
        return {"queue": [{"id": 1}], "total": 1, "limit": limit}

    async def save(_correction):
        return None

    async def add_item(**_kwargs):
        return 7

    async def list_items(limit=50):
        return {"queue": [], "total": 0, "limit": limit}

    async def resolve_item(_item_id, _notes, _admin_id):
        return None

    monkeypatch.setattr(main, "get_review_queue", queue)
    monkeypatch.setattr(main, "save_correction", save)
    monkeypatch.setattr(main, "add_human_review_item", add_item)
    monkeypatch.setattr(main, "get_human_review_queue", list_items)
    monkeypatch.setattr(main, "resolve_human_review_item", resolve_item)
    monkeypatch.setattr(main, "get_retraining_queue", lambda **_kwargs: {"records": [], "total": 0})
    monkeypatch.setattr(main, "get_retraining_record", lambda _cid: None)
    monkeypatch.setattr(main, "save_retraining_review", lambda **_kwargs: None)
    monkeypatch.setattr(main, "get_retraining_export", lambda mark_exported=False: {"records": [], "total": 0})

    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "review-service"
    assert client.get("/queue?limit=3").json()["total"] == 1
    assert client.get("/human-review").json()["total"] == 0

    add_response = client.post(
        "/human-review",
        json={
            "complaint_id": "c1",
            "validation_status": "human_review",
            "review_reason": "unclear",
            "original_text": "broken pipe",
        },
    )
    assert add_response.status_code == 201
    assert add_response.json()["id"] == 7

    assert client.get("/retraining/missing").status_code == 404
    invalid = client.post(
        "/retraining/c1/review",
        json={"admin_id": "admin", "admin_decision": "bad"},
    )
    assert invalid.status_code == 422

