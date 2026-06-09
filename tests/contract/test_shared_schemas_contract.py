from __future__ import annotations

import pytest
from pydantic import ValidationError


pytestmark = pytest.mark.contract


def test_location_input_rejects_out_of_range_coordinates(schemas):
    with pytest.raises(ValidationError):
        schemas.LocationInput(latitude=91.0, longitude=35.0)

    with pytest.raises(ValidationError):
        schemas.LocationInput(latitude=33.0, longitude=181.0)


def test_routing_result_serializes_enums_as_contract_values(schemas):
    result = schemas.RoutingResult(
        complaint_id="r-1",
        primary_entity=schemas.RoutingEntity.OGERO,
        primary_confidence=0.91,
        secondary_entity=schemas.RoutingEntity.GENERIC_MUNICIPALITY,
        secondary_confidence=0.5,
        routing_rationale=["fixed telecom infrastructure owner selected"],
        retrieved_sources=["ogero-doc"],
        routing_source="rag_retrieval",
        auto_routed=True,
        requires_review=False,
        processing_ms=12,
    )

    dumped = result.model_dump(mode="json")

    assert dumped["primary_entity"] == "Ogero"
    assert dumped["secondary_entity"] == "Local Municipality"
    assert dumped["routing_source"] == "rag_retrieval"


def test_complaint_decision_round_trips_nested_pipeline_outputs(schemas):
    decision = schemas.ComplaintDecision(
        complaint_id="decision-1",
        original_text="There is a burst water pipe in Jounieh.",
        complaint_type="water_pipe",
        routing=schemas.RoutingResult(
            complaint_id="decision-1",
            primary_entity=schemas.RoutingEntity.WATER_AUTHORITY,
            primary_confidence=0.88,
            routing_rationale=["regional water authority selected"],
            routing_source="rag_retrieval",
            auto_routed=True,
            requires_review=False,
            processing_ms=4,
        ),
        confidence_bundle=schemas.ConfidenceBundle(
            routing=schemas.StageConfidence(score=0.88, method="rag", reliable=True),
            final=0.88,
            weakest_stage="routing",
        ),
    )

    restored = schemas.ComplaintDecision.model_validate(decision.model_dump(mode="json"))

    assert restored.complaint_id == "decision-1"
    assert restored.routing.primary_entity == schemas.RoutingEntity.WATER_AUTHORITY
    assert restored.confidence_bundle.routing.method == "rag"


def test_visual_understanding_limits_candidate_list_to_contract_size(schemas):
    candidates = [
        schemas.VisualIssueCandidate(visual_category="roads", visual_subcategory=f"issue_{idx}")
        for idx in range(4)
    ]

    with pytest.raises(ValidationError):
        schemas.VisualUnderstandingJSON(visual_candidates=candidates)


def test_human_review_item_requires_core_review_fields(schemas):
    item = schemas.HumanReviewItem(
        complaint_id="h-1",
        validation_status="human_review",
        review_reason="RAG returned no candidate authority",
        original_text="Unknown infrastructure complaint.",
    )

    assert item.image_filename is None
    assert item.validation_status == "human_review"
