from __future__ import annotations

import asyncio

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.unit


def test_language_detector_prioritizes_arabizi_before_library_detection():
    detector = import_or_skip("services.text_understanding.app.language_detector")

    assert detector.detect_arabizi("fi 7afra kbire 3al tari2") is True
    assert detector.detect_language("fi 7afra kbire 3al tari2") == "arabizi"
    assert detector.detect_language("في حفرة كبيرة على الطريق") == "ar"


def test_llm_json_parsing_and_coercion_repairs_loose_shapes():
    extractor = import_or_skip("services.text_understanding.app.llm_extractor")

    parsed = extractor._parse_llm_json('```json\n{"issue_type":"Road Damage"}\n```')
    assert parsed == {"issue_type": "Road Damage"}

    coerced = extractor._coerce_llm_output(
        {
            "is_complaint": "yes",
            "issue_type": ["bad-shape"],
            "category": "Roads",
            "subcategory": None,
            "severity": "wild",
            "location_mentions": "Hamra",
            "keywords": ["pothole", "", None],
            "signals": {"traffic_impact": "true", "emergency_signal": "0"},
            "confidence": "1.7",
        }
    )

    assert coerced["is_complaint"] is True
    assert coerced["issue_type"] == "unknown"
    assert coerced["category"] == "Roads"
    assert coerced["severity"] == "LOW"
    assert coerced["location_mentions"] == ["Hamra"]
    assert coerced["keywords"] == ["pothole", "None"]
    assert coerced["signals"]["traffic_impact"] is True
    assert coerced["signals"]["emergency_signal"] is False
    assert coerced["confidence"] == 1.0


def test_issue_type_promotion_uses_specific_fallbacks():
    extractor = import_or_skip("services.text_understanding.app.llm_extractor")

    assert extractor._promote_issue_type("unknown", "roads", "pothole", "damage") == "pothole"
    assert extractor._promote_issue_type("other", "water", "unknown", "leak") == "water_leak"
    assert extractor._promote_issue_type("streetlight", "electricity", "lamp", "outage") == "streetlight"


def test_visual_candidate_parser_deduplicates_and_repairs_component_mismatch(schemas):
    analyzer = import_or_skip("services.image_understanding.app.analyzer")

    candidates = analyzer._parse_visual_candidates(
        {
            "visual_candidates": [
                {
                    "visual_category": "Safety",
                    "visual_subcategory": "hazard",
                    "physical_component": "telecom cable",
                    "failure_mode": "hanging low",
                    "confidence": "0.8",
                    "caption": "A telecom cable is hanging low over the street.",
                    "evidence": "low hanging cable",
                },
                {
                    "visual_category": "Safety",
                    "visual_subcategory": "hazard",
                    "physical_component": "telecom cable",
                    "failure_mode": "hanging low",
                    "confidence": "0.8",
                },
            ]
        }
    )

    assert len(candidates) == 1
    assert candidates[0].visual_subcategory == "low_hanging_telecom_cable"
    assert candidates[0].failure_mode == "low_hanging"
    assert candidates[0].semantic_domain == "utilities"
    assert candidates[0].confidence == 0.8


def test_splitter_enumerated_parts_and_independent_clauses():
    splitter = import_or_skip("services.gateway.app.splitter")

    enumerated = splitter._enumerated_parts(
        "1. There is a pothole near Hamra main road. "
        "2. The streetlight is broken near Bliss street."
    )
    assert enumerated == [
        "There is a pothole near Hamra main road.",
        "The streetlight is broken near Bliss street.",
    ]

    clauses = splitter._independent_issue_clauses(
        "there is a pothole on the road and there is no electricity in Achrafieh"
    )
    assert len(clauses) == 2
    assert "pothole" in clauses[0]
    assert "electricity" in clauses[1]


def test_splitter_coerces_single_result_when_llm_marks_single():
    splitter = import_or_skip("services.gateway.app.splitter")

    output = splitter._LLMSplitOutput(
        is_multi=False,
        complaints=[
            {"complaint_text": "There is a pothole in Hamra.", "confidence": 0.8},
            {"complaint_text": "Streetlight is broken in Hamra.", "confidence": 0.8},
        ],
        confidence=0.7,
    )

    result = splitter._coerce_result("Original combined complaint text here.", "llm", output)

    assert result.is_multi is False
    assert result.source == "single"
    assert len(result.complaints) == 1
    assert result.complaints[0].complaint_text == "Original combined complaint text here."


def test_split_complaint_text_stays_single_without_llm_url(monkeypatch):
    splitter = import_or_skip("services.gateway.app.splitter")
    monkeypatch.setattr(splitter, "SPLITTER_ENABLED", True)
    monkeypatch.setattr(splitter, "SPLITTER_LLM_ENABLED", True)
    monkeypatch.setattr(splitter, "QWEN_BASE_URL", "")

    result = asyncio.run(splitter.split_complaint_text("There is a pothole and the road is damaged in Hamra."))

    assert result.is_multi is False
    assert result.source == "single"
    assert len(result.complaints) == 1
