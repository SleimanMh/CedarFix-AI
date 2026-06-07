from __future__ import annotations

import asyncio
import inspect
from pathlib import Path

from cedarfix_shared.schemas import (
    ComplaintRequest,
    LocationInput,
    LocationJSON,
    MediaValidationResult,
    MediaValidationStatus,
)


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


def test_location_evaluation_treats_submitted_location_as_authoritative(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")

    result = orchestrator._evaluate_location_extraction(
        submitted_location=LocationInput(
            normalized="Verdun",
            municipality="Beirut",
            district="Beirut",
            governorate="Beirut Governorate",
            source="text_lookup",
            confidence=0.8,
        ),
        text_location=LocationJSON(
            raw="Tripoli",
            normalized="Tripoli",
            municipality="Tripoli",
            district="Tripoli",
            governorate="North Governorate",
            confidence=0.7,
            source="llm_extracted",
        ),
        input_mode="manual_text",
    )

    assert result["routing_uses_submitted_location"] is True
    assert result["authoritative_location_source"] == "text_lookup"
    assert result["llm_matches_submitted"] is False
    assert result["usable_for_finetuning"] is True
    assert result["finetuning_note"] == "Use submitted/resolved location as correction label."


def test_descriptor_similarity_accepts_semantic_token_overlap(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")

    assert orchestrator._descriptor_similarity("telecom cable", "public_fixed_telecom_cable") >= 0.75
    assert orchestrator._descriptor_overlap(
        "utilities",
        "telecom cable",
        "low hanging",
        "utilities",
        "public_fixed_telecom_cable",
        "hanging low",
    ) == 3
