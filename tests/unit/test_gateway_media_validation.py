from __future__ import annotations

import asyncio

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.unit


def _orchestrator():
    return import_or_skip("services.gateway.app.orchestrator")


def _text_result(
    schemas,
    *,
    issue_type: str = "pothole",
    category: str = "roads",
    subcategory: str = "pothole",
    confidence: float = 0.91,
    semantic_domain: str | None = "transportation",
    physical_component: str | None = "road_surface",
    failure_mode: str | None = "damage",
):
    return schemas.TextUnderstandingResult(
        complaint_id="c-media",
        original_text="There is a large pothole blocking traffic in Hamra.",
        normalized_text="There is a large pothole blocking traffic in Hamra.",
        language="en",
        summary="Large pothole in Hamra",
        category=category,
        subcategory=subcategory,
        issue_type=issue_type,
        severity=schemas.SeverityLevel.HIGH,
        confidence=confidence,
        semantic_domain=semantic_domain,
        physical_component=physical_component,
        failure_mode=failure_mode,
    )


def _non_complaint_text(schemas):
    return _text_result(
        schemas,
        issue_type="unknown",
        category="",
        subcategory="",
        confidence=0.2,
        semantic_domain=None,
        physical_component=None,
        failure_mode=None,
    )


def _candidate(
    schemas,
    *,
    category: str,
    subcategory: str,
    semantic_domain: str,
    physical_component: str,
    failure_mode: str,
    confidence: float,
):
    return schemas.VisualIssueCandidate(
        visual_category=category,
        visual_subcategory=subcategory,
        caption=f"{subcategory.replace('_', ' ')} visible",
        semantic_domain=semantic_domain,
        physical_component=physical_component,
        failure_mode=failure_mode,
        confidence=confidence,
    )


def _image_result(
    schemas,
    *,
    category: str = "roads",
    subcategory: str = "pothole",
    confidence: float = 0.88,
    usable: bool = True,
    damage_visible: bool = True,
    semantic_domain: str | None = "transportation",
    physical_component: str | None = "road_surface",
    failure_mode: str | None = "damage",
    candidates: list | None = None,
):
    return schemas.ImageUnderstandingResult(
        complaint_id="c-media",
        image_present=True,
        image_id="image-1",
        image_quality=schemas.ImageQualityJSON(
            usable=usable,
            quality_score=0.9 if usable else 0.2,
            issues=[] if usable else ["unusable"],
        ),
        visual_understanding=schemas.VisualUnderstandingJSON(
            caption=f"{subcategory.replace('_', ' ')} visible",
            visual_category=category,
            visual_subcategory=subcategory,
            detected_objects=[subcategory],
            damage_visible=damage_visible,
            visual_severity=schemas.SeverityLevel.HIGH,
            confidence=confidence,
            semantic_domain=semantic_domain,
            physical_component=physical_component,
            failure_mode=failure_mode,
            visual_candidates=candidates or [],
        ),
    )


def test_validate_media_accepts_text_only_public_complaint(schemas):
    orchestrator = _orchestrator()

    result = asyncio.run(orchestrator._validate_media("c-media", _text_result(schemas), None))

    assert result.status == schemas.MediaValidationStatus.VALID
    assert result.text_is_complaint is True
    assert result.image_has_complaint is False
    assert result.reconciled_type == "pothole"
    assert result.reconciled_source == "text"


def test_validate_media_rejects_non_complaint_text_without_image(schemas):
    orchestrator = _orchestrator()
    text = _non_complaint_text(schemas)
    text.confidence = 0.1

    result = asyncio.run(orchestrator._validate_media("c-media", text, None))

    assert result.status == schemas.MediaValidationStatus.INVALID_NO_COMPLAINT
    assert result.text_is_complaint is False
    assert result.image_has_complaint is False
    assert result.reconciled_type is None


def test_validate_media_sends_confident_image_only_report_to_human_review(schemas):
    orchestrator = _orchestrator()
    text = _non_complaint_text(schemas)
    image = _image_result(schemas, confidence=0.91)

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.HUMAN_REVIEW
    assert result.text_is_complaint is False
    assert result.image_has_complaint is True
    assert result.text_semantic_domain is None
    assert result.text_physical_component is None
    assert result.text_failure_mode is None
    assert result.reconciled_type == "pothole"
    assert result.reconciled_source == "image"


def test_validate_media_asks_for_clarification_when_image_only_has_multiple_specific_issues(schemas):
    orchestrator = _orchestrator()
    text = _non_complaint_text(schemas)
    image = _image_result(
        schemas,
        candidates=[
            _candidate(
                schemas,
                category="roads",
                subcategory="pothole",
                semantic_domain="transportation",
                physical_component="road_surface",
                failure_mode="damage",
                confidence=0.9,
            ),
            _candidate(
                schemas,
                category="sanitation",
                subcategory="waste_accumulation",
                semantic_domain="environment",
                physical_component="waste_container",
                failure_mode="accumulation",
                confidence=0.82,
            ),
        ],
    )

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.NEEDS_CLARIFICATION
    assert result.text_is_complaint is False
    assert result.image_has_complaint is True
    assert result.text_semantic_domain is None
    assert "multiple issues" in result.clarification_question
    assert result.reconciled_type is None


def test_validate_media_flags_rule_based_text_image_contradiction(schemas):
    orchestrator = _orchestrator()
    text = _text_result(schemas)
    image = _image_result(
        schemas,
        category="sanitation",
        subcategory="waste_accumulation",
        semantic_domain="environment",
        physical_component="waste_container",
        failure_mode="accumulation",
        confidence=0.9,
    )

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.CONTRADICTION
    assert result.text_detected_type == "pothole"
    assert result.image_detected_type == "waste_accumulation"
    assert result.modality_overlap_score == 0
    assert result.reconciled_type is None


def test_validate_media_llm_related_override_can_prevent_rule_based_contradiction(monkeypatch, schemas):
    orchestrator = _orchestrator()
    text = _text_result(schemas)
    image = _image_result(
        schemas,
        category="sanitation",
        subcategory="waste_accumulation",
        semantic_domain="environment",
        physical_component="waste_container",
        failure_mode="accumulation",
        confidence=0.9,
    )

    async def related_alignment(complaint_id, payload):
        assert payload["rule_based_alignment"]["would_flag_contradiction"] is True
        return {
            "alignment": "RELATED",
            "confidence": 0.88,
            "reason": "The image and text both describe a public-space hazard at the same location.",
        }

    monkeypatch.setattr(orchestrator, "_llm_media_alignment", related_alignment)

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.VALID
    assert result.reconciled_type == "pothole"
    assert result.reconciled_source == "llm_related"
    assert result.modality_overlap_score == 0


def test_validate_media_llm_contradiction_override_can_reject_rule_based_match(monkeypatch, schemas):
    orchestrator = _orchestrator()
    text = _text_result(schemas)
    image = _image_result(schemas)

    async def contradiction_alignment(complaint_id, payload):
        assert payload["rule_based_alignment"]["would_flag_contradiction"] is False
        return {
            "alignment": "CONTRADICTS",
            "confidence": 0.91,
            "reason": "The image was judged to show a different incident despite matching labels.",
        }

    monkeypatch.setattr(orchestrator, "_llm_media_alignment", contradiction_alignment)

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.CONTRADICTION
    assert result.reconciled_source == "llm_contradiction"
    assert "different incident" in result.contradiction_reason


def test_validate_media_clear_text_with_unusable_image_requires_human_review(schemas):
    orchestrator = _orchestrator()
    text = _text_result(schemas)
    image = _image_result(schemas, usable=False, damage_visible=False, confidence=0.22)

    result = asyncio.run(orchestrator._validate_media("c-media", text, image))

    assert result.status == schemas.MediaValidationStatus.HUMAN_REVIEW
    assert result.text_is_complaint is True
    assert result.image_has_complaint is False
    assert result.reconciled_type == "pothole"
    assert result.reconciled_source == "text"


def test_validate_media_treats_text_service_failure_as_non_blocking(schemas):
    orchestrator = _orchestrator()
    image = _image_result(schemas, confidence=0.87)

    result = asyncio.run(orchestrator._validate_media("c-media", None, image))

    assert result.status == schemas.MediaValidationStatus.VALID
    assert result.text_is_complaint is False
    assert result.image_has_complaint is True
    assert result.text_detected_type is None
    assert result.reconciled_type == "pothole"
    assert result.reconciled_source == "image"
