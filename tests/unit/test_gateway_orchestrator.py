from __future__ import annotations

import asyncio

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.unit


def _orchestrator():
    return import_or_skip("services.gateway.app.orchestrator")


def _request(schemas, **overrides):
    payload = {
        "text": "There is a large pothole blocking traffic in Hamra.",
        "location": schemas.LocationInput(
            normalized="Hamra, Beirut",
            municipality="Beirut",
            district="Beirut",
            governorate="Beirut Governorate",
            source="user_text",
            confidence=0.85,
        ),
        "location_input_mode": "manual_text",
        "user_id": "user-1",
    }
    payload.update(overrides)
    return schemas.ComplaintRequest(**payload)


def _text_result(schemas, complaint_id="c-1"):
    return schemas.TextUnderstandingResult(
        complaint_id=complaint_id,
        original_text="There is a large pothole blocking traffic in Hamra.",
        normalized_text="There is a large pothole blocking traffic in Hamra.",
        language="en",
        summary="Large pothole in Hamra",
        category="roads",
        subcategory="pothole",
        issue_type="pothole",
        location=schemas.LocationJSON(
            raw="Hamra",
            normalized="Hamra, Beirut",
            municipality="Beirut",
            district="Beirut",
            governorate="Beirut Governorate",
            confidence=0.8,
            source="llm",
        ),
        location_mentions=["Hamra"],
        severity=schemas.SeverityLevel.HIGH,
        confidence=0.91,
        semantic_domain="transportation",
        physical_component="road_surface",
        failure_mode="damage",
        routing_features=schemas.RoutingFeaturesJSON(
            domain="transportation",
            physical_component="road_surface",
            failure_mode="damage",
            hazard_type="road_hazard",
        ),
    )


def _embedding_result(schemas, complaint_id="c-1"):
    alignment = schemas.TextImageAlignment(
        complaint_id=complaint_id,
        alignment_status=schemas.AlignmentStatus.NO_IMAGE,
        alignment_score=0.0,
        text_issue_type="pothole",
        image_issue_type=None,
        text_subcategory="pothole",
        image_subcategory="",
        reconciliation_status=schemas.ReconciliationStatus.INSUFFICIENT_EVIDENCE,
    )
    canonical = schemas.CanonicalComplaint(
        complaint_id=complaint_id,
        summary="Large pothole in Hamra",
        category="roads",
        subcategory="pothole",
        issue_type="pothole",
        severity=schemas.SeverityLevel.HIGH,
        location=schemas.CanonicalLocationJSON(
            normalized_location="Hamra, Beirut",
            district="Beirut",
            governorate="Beirut Governorate",
        ),
        modality="TEXT_ONLY",
    )
    return schemas.EmbeddingServiceResult(
        complaint_id=complaint_id,
        canonical=canonical,
        alignment=alignment,
        candidates=[],
        text_embedding=[0.1, 0.2],
        processing_ms=2,
    )


def _clustering_result(schemas, complaint_id="c-1"):
    return schemas.MultimodalClusteringResult(
        complaint_id=complaint_id,
        duplicate_status=schemas.DuplicateStatus.NEW,
        duplicate_decision=schemas.DuplicateDecisionEnum.NEW_INCIDENT,
        decision_confidence=0.86,
        decision_reason="No similar candidates.",
        processing_ms=3,
    )


def _priority_result(schemas, complaint_id="c-1"):
    return schemas.PriorityResult(
        complaint_id=complaint_id,
        severity=schemas.SeverityLevel.HIGH,
        priority_score=0.72,
        urgency_factors=["Road hazard"],
        confidence=0.75,
        processing_ms=1,
    )


def _routing_result(schemas, complaint_id="c-1", **overrides):
    payload = {
        "complaint_id": complaint_id,
        "primary_entity": schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS,
        "primary_confidence": 0.91,
        "routing_rationale": ["RAG selected road authority"],
        "retrieved_sources": ["mpwt-road-doc"],
        "routing_source": "rag_retrieval",
        "auto_routed": True,
        "requires_review": False,
        "rag_no_candidates": False,
        "processing_ms": 4,
    }
    payload.update(overrides)
    return schemas.RoutingResult(**payload)


def _explanation_result(schemas, complaint_id="c-1"):
    return schemas.ExplanationResult(
        complaint_id=complaint_id,
        explanation_text="Your complaint was routed to the road authority.",
        mode="template",
        key_factors=["Road hazard", "Hamra"],
    )


def test_run_pipeline_stops_immediately_on_moderation_reject(monkeypatch, schemas):
    orchestrator = _orchestrator()

    async def reject(**kwargs):
        return schemas.ModerationResult(
            decision=schemas.ModerationDecisionEnum.REJECT,
            reason="Rejected by moderation",
        )

    async def should_not_run(*args, **kwargs):
        raise AssertionError("downstream pipeline stages should not run after moderation reject")

    monkeypatch.setattr(orchestrator, "moderate", reject)
    monkeypatch.setattr(orchestrator, "_call_text_understanding", should_not_run)

    decision = asyncio.run(orchestrator.run_pipeline("c-1", _request(schemas)))

    assert decision.status == schemas.PipelineStatus.REJECTED
    assert decision.moderation.reason == "Rejected by moderation"
    assert decision.text_analysis is None


def test_run_pipeline_happy_path_populates_stage_outputs(monkeypatch, schemas):
    orchestrator = _orchestrator()

    async def pass_moderation(**kwargs):
        return schemas.ModerationResult(decision=schemas.ModerationDecisionEnum.PASS, reason="Clean")

    async def call_text(client, complaint_id, request):
        return _text_result(schemas, complaint_id)

    async def call_image(client, complaint_id, request):
        return None

    async def validate_media(complaint_id, text_result, image_result):
        return schemas.MediaValidationResult(
            status=schemas.MediaValidationStatus.VALID,
            text_is_complaint=True,
            image_has_complaint=False,
            text_detected_type="pothole",
            reconciled_type="pothole",
            reconciled_source="text",
        )

    async def call_embedding(client, complaint_id, text_result, image_result):
        return _embedding_result(schemas, complaint_id)

    async def call_clustering(client, complaint_id, embedding_result):
        return _clustering_result(schemas, complaint_id)

    async def call_priority(client, complaint_id, decision):
        return _priority_result(schemas, complaint_id)

    async def call_routing(client, complaint_id, decision):
        return _routing_result(schemas, complaint_id)

    async def call_explanation(client, complaint_id, decision):
        return _explanation_result(schemas, complaint_id)

    monkeypatch.setattr(orchestrator, "moderate", pass_moderation)
    monkeypatch.setattr(orchestrator, "_call_text_understanding", call_text)
    monkeypatch.setattr(orchestrator, "_call_image_understanding", call_image)
    monkeypatch.setattr(orchestrator, "_validate_media", validate_media)
    monkeypatch.setattr(orchestrator, "_call_embedding_service", call_embedding)
    monkeypatch.setattr(orchestrator, "_call_clustering_service", call_clustering)
    monkeypatch.setattr(orchestrator, "_call_priority_engine", call_priority)
    monkeypatch.setattr(orchestrator, "_call_routing_engine", call_routing)
    monkeypatch.setattr(orchestrator, "_call_explanation_service", call_explanation)

    decision = asyncio.run(orchestrator.run_pipeline("c-1", _request(schemas)))

    assert decision.status == schemas.PipelineStatus.COMPLETED
    assert decision.complaint_type == "pothole"
    assert decision.priority_score == 0.72
    assert decision.assigned_entity == schemas.RoutingEntity.MINISTRY_PUBLIC_WORKS
    assert decision.confidence_bundle.routing.score == 0.91
    assert decision.explanation.explanation_text.startswith("Your complaint")


def test_run_pipeline_needs_clarification_queues_human_review_and_stops(monkeypatch, schemas):
    orchestrator = _orchestrator()
    queued: list[tuple[str, str]] = []

    async def pass_moderation(**kwargs):
        return schemas.ModerationResult(decision=schemas.ModerationDecisionEnum.PASS, reason="Clean")

    async def call_text(client, complaint_id, request):
        return _text_result(schemas, complaint_id)

    async def call_image(client, complaint_id, request):
        return None

    async def validate_media(complaint_id, text_result, image_result):
        return schemas.MediaValidationResult(
            status=schemas.MediaValidationStatus.NEEDS_CLARIFICATION,
            text_is_complaint=False,
            image_has_complaint=False,
            clarification_question="Please describe the infrastructure issue.",
        )

    async def add_to_review(client, complaint_id, request, validation):
        queued.append((complaint_id, validation.status.value))

    async def should_not_run(*args, **kwargs):
        raise AssertionError("downstream stages should not run after clarification gate")

    monkeypatch.setattr(orchestrator, "moderate", pass_moderation)
    monkeypatch.setattr(orchestrator, "_call_text_understanding", call_text)
    monkeypatch.setattr(orchestrator, "_call_image_understanding", call_image)
    monkeypatch.setattr(orchestrator, "_validate_media", validate_media)
    monkeypatch.setattr(orchestrator, "_add_to_human_review", add_to_review)
    monkeypatch.setattr(orchestrator, "_call_embedding_service", should_not_run)

    decision = asyncio.run(orchestrator.run_pipeline("c-1", _request(schemas)))

    assert decision.status == schemas.PipelineStatus.NEEDS_CLARIFICATION
    assert queued == [("c-1", "needs_clarification")]
    assert decision.embedding is None


def test_run_pipeline_rag_no_candidates_queues_review_and_marks_review_required(monkeypatch, schemas):
    orchestrator = _orchestrator()
    queued: list[tuple[str, str | None]] = []

    async def pass_moderation(**kwargs):
        return schemas.ModerationResult(decision=schemas.ModerationDecisionEnum.PASS, reason="Clean")

    async def call_text(client, complaint_id, request):
        return _text_result(schemas, complaint_id)

    async def call_image(client, complaint_id, request):
        return None

    async def validate_media(complaint_id, text_result, image_result):
        return schemas.MediaValidationResult(
            status=schemas.MediaValidationStatus.VALID,
            text_is_complaint=True,
            image_has_complaint=False,
            text_detected_type="pothole",
            reconciled_type="pothole",
            reconciled_source="text",
        )

    async def call_embedding(client, complaint_id, text_result, image_result):
        return _embedding_result(schemas, complaint_id)

    async def call_clustering(client, complaint_id, embedding_result):
        return _clustering_result(schemas, complaint_id)

    async def call_priority(client, complaint_id, decision):
        return _priority_result(schemas, complaint_id)

    async def call_routing(client, complaint_id, decision):
        return _routing_result(
            schemas,
            complaint_id,
            primary_entity=schemas.RoutingEntity.HUMAN_REVIEW,
            primary_confidence=0.0,
            routing_source="rag_no_match",
            auto_routed=False,
            requires_review=True,
            review_reason="Qdrant returned zero routing candidates",
            rag_no_candidates=True,
        )

    async def call_explanation(client, complaint_id, decision):
        return _explanation_result(schemas, complaint_id)

    async def add_to_review(client, complaint_id, request, validation):
        queued.append((complaint_id, validation.contradiction_reason or validation.clarification_question))

    monkeypatch.setattr(orchestrator, "moderate", pass_moderation)
    monkeypatch.setattr(orchestrator, "_call_text_understanding", call_text)
    monkeypatch.setattr(orchestrator, "_call_image_understanding", call_image)
    monkeypatch.setattr(orchestrator, "_validate_media", validate_media)
    monkeypatch.setattr(orchestrator, "_call_embedding_service", call_embedding)
    monkeypatch.setattr(orchestrator, "_call_clustering_service", call_clustering)
    monkeypatch.setattr(orchestrator, "_call_priority_engine", call_priority)
    monkeypatch.setattr(orchestrator, "_call_routing_engine", call_routing)
    monkeypatch.setattr(orchestrator, "_call_explanation_service", call_explanation)
    monkeypatch.setattr(orchestrator, "_add_to_human_review", add_to_review)

    decision = asyncio.run(orchestrator.run_pipeline("c-1", _request(schemas)))

    assert decision.status == schemas.PipelineStatus.REVIEW_REQUIRED
    assert decision.routing.rag_no_candidates is True
    assert queued == [("c-1", "Qdrant returned zero routing candidates")]
