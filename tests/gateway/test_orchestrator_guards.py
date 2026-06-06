from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from cedarfix_shared.schemas import ComplaintRequest, MediaValidationResult, MediaValidationStatus


ROOT = Path(__file__).resolve().parents[2]


class FakeClient:
    def __init__(self):
        self.posts = []

    async def post(self, url, json):
        self.posts.append({"url": url, "json": json})


def test_add_to_human_review_posts_contradiction_reason_when_no_clarification(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    client = FakeClient()

    asyncio.run(
        orchestrator._add_to_human_review(
            client,
            "c1",
            ComplaintRequest(text="Broken road near Hamra", image_filename="local://road.jpg"),
            MediaValidationResult(
                status=MediaValidationStatus.HUMAN_REVIEW,
                text_is_complaint=True,
                image_has_complaint=False,
                contradiction_reason="Qdrant returned zero routing candidates.",
                text_detected_type="road_damage",
            ),
        )
    )

    assert len(client.posts) == 1
    payload = client.posts[0]["json"]
    assert payload["review_reason"] == "Qdrant returned zero routing candidates."
    assert payload["text_detected_type"] == "road_damage"
    assert payload["image_filename"] == "local://road.jpg"


def test_add_to_human_review_is_fire_and_forget_only(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    source = inspect.getsource(orchestrator._add_to_human_review)

    assert "Full EEP" not in source
    assert "async with httpx.AsyncClient" not in source
    assert "return decision" not in source


def test_gateway_auth_handlers_do_not_keep_legacy_dead_branches():
    source = (ROOT / "services" / "gateway" / "app" / "main.py").read_text(encoding="utf-8")

    assert "For capstone demo" not in source
    assert "ADMIN_REGISTRATION_SECRET" not in source
    assert "Invalid username or password" not in source
    assert "Username \u2265 3 chars" not in source
