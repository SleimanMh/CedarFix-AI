from __future__ import annotations

from cedarfix_shared.schemas import SeverityLevel


def test_parse_llm_json_extracts_object_from_markdown(import_service_module):
    llm = import_service_module("text_understanding", "app.llm_extractor")

    parsed = llm._parse_llm_json("```json\n{\"issue_type\":\"road_damage\"}\n```")

    assert parsed == {"issue_type": "road_damage"}


def test_coerce_llm_output_repairs_loose_shapes_and_clamps_confidence(import_service_module):
    llm = import_service_module("text_understanding", "app.llm_extractor")

    clean = llm._coerce_llm_output(
        {
            "is_complaint": "yes",
            "issue_type": {"bad": "shape"},
            "category": "Road Surface",
            "severity": "extreme",
            "location_mentions": "Hamra",
            "keywords": ["urgent", "", "traffic"],
            "signals": {"emergency_signal": "true"},
            "routing_features": {"affected_public_space": "false"},
            "evidence": "visible crack",
            "alignment_features": {"objects": "road"},
            "confidence": "1.8",
        }
    )

    assert clean["is_complaint"] is True
    assert clean["issue_type"] == "unknown"
    assert clean["severity"] == "LOW"
    assert clean["location_mentions"] == ["Hamra"]
    assert clean["signals"]["emergency_signal"] is True
    assert clean["routing_features"]["affected_public_space"] is False
    assert clean["evidence"]["text_evidence"] == ["visible crack"]
    assert clean["alignment_features"]["objects"] == ["road"]
    assert clean["confidence"] == 1.0


def test_build_result_creates_not_complaint_payload(import_service_module):
    llm = import_service_module("text_understanding", "app.llm_extractor")

    result = llm._build_result(
        "c1",
        "hello",
        "en",
        {"is_complaint": False, "summary": "Greeting only"},
        processing_ms=12,
    )

    assert result.issue_type == "unknown"
    assert result.confidence == 0.0
    assert result.location.source == "none"
    assert result.evidence.missing_information == ["complaint_not_detected_in_text"]
    assert result.processing_ms == 12


def test_build_result_normalizes_dynamic_descriptors_and_location(import_service_module):
    llm = import_service_module("text_understanding", "app.llm_extractor")

    result = llm._build_result(
        "c1",
        "Broken sidewalk in Hamra",
        "en",
        {
            "is_complaint": True,
            "issue_type": "Broken Sidewalk",
            "category": "Sidewalk",
            "subcategory": "",
            "severity": "HIGH",
            "location_mentions": ["Hamra"],
            "summary": "",
            "signals": {"traffic_impact": True},
            "confidence": 0.8,
        },
        processing_ms=5,
    )

    assert result.issue_type == "broken_sidewalk"
    assert result.subcategory == "broken_sidewalk"
    assert result.severity == SeverityLevel.HIGH
    assert result.semantic_domain == "sidewalk"
    assert result.physical_component == "sidewalk"
    assert result.location.normalized == "Hamra"
    assert result.summary == "Broken sidewalk reported."
