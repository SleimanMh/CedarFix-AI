from __future__ import annotations

from cedarfix_shared.schemas import (
    ImageQualityJSON,
    ImageUnderstandingResult,
    MediaValidationStatus,
    TextUnderstandingResult,
    VisualIssueCandidate,
    VisualUnderstandingJSON,
)


def _text(**overrides):
    base = dict(
        complaint_id="c1",
        original_text="Broken road in Hamra",
        normalized_text="Broken road in Hamra",
        issue_type="road_damage",
        category="roads",
        subcategory="road_damage",
        confidence=0.8,
        semantic_domain="transportation",
        physical_component="road_surface",
        failure_mode="damage",
    )
    base.update(overrides)
    return TextUnderstandingResult(**base)


def _image(**overrides):
    vu = VisualUnderstandingJSON(
        visual_category="roads",
        visual_subcategory="road_damage",
        damage_visible=True,
        confidence=0.8,
        semantic_domain="transportation",
        physical_component="road_surface",
        failure_mode="damage",
    )
    base = dict(
        complaint_id="c1",
        image_present=True,
        image_quality=ImageQualityJSON(usable=True, quality_score=0.9),
        visual_understanding=vu,
    )
    base.update(overrides)
    return ImageUnderstandingResult(**base)


def test_validate_media_accepts_compatible_text_and_image(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    result = orchestrator._validate_media(_text(), _image())
    assert result.status == MediaValidationStatus.VALID
    assert result.reconciled_source == "both"
    assert result.modality_overlap_score == 3


def test_validate_media_detects_text_image_contradiction(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    image = _image(
        visual_understanding=VisualUnderstandingJSON(
            visual_category="sanitation",
            visual_subcategory="waste_accumulation",
            damage_visible=True,
            confidence=0.8,
            semantic_domain="environment",
            physical_component="public_space",
            failure_mode="accumulation",
        )
    )
    result = orchestrator._validate_media(_text(), image)
    assert result.status == MediaValidationStatus.CONTRADICTION
    assert result.reconciled_source == "contradiction"


def test_validate_media_image_only_multiple_candidates_needs_clarification(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    image = _image(
        visual_understanding=VisualUnderstandingJSON(
            damage_visible=True,
            confidence=0.9,
            visual_candidates=[
                VisualIssueCandidate(
                    visual_category="roads",
                    visual_subcategory="pothole",
                    semantic_domain="transportation",
                    physical_component="road_surface",
                    failure_mode="damage",
                    confidence=0.8,
                ),
                VisualIssueCandidate(
                    visual_category="sanitation",
                    visual_subcategory="waste_accumulation",
                    semantic_domain="environment",
                    physical_component="public_space",
                    failure_mode="accumulation",
                    confidence=0.7,
                ),
            ],
        )
    )
    result = orchestrator._validate_media(_text(issue_type="other", confidence=0.2), image)
    assert result.status == MediaValidationStatus.NEEDS_CLARIFICATION
    assert "multiple issues" in result.clarification_question


def test_validate_media_invalid_when_no_complaint_or_image(import_service_module):
    orchestrator = import_service_module("gateway", "app.orchestrator")
    result = orchestrator._validate_media(_text(issue_type="other", confidence=0.2), None)
    assert result.status == MediaValidationStatus.INVALID_NO_COMPLAINT

