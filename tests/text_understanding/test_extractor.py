from __future__ import annotations

import pytest

from cedarfix_shared.schemas import ComplaintType, SeverityLevel


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("There is a large pothole on Hamra road", ComplaintType.POTHOLE),
        ("The asphalt crack caused clear road damage in Verdun", ComplaintType.ROAD_DAMAGE),
        ("Standing water and flooding are blocking the street", ComplaintType.FLOODING),
        ("Garbage and waste accumulation are overflowing near the bins", ComplaintType.WASTE),
        ("There is no electricity after a power outage", ComplaintType.ELECTRICITY),
        ("The traffic light signal is not working", ComplaintType.TRAFFIC_LIGHT),
        ("A burst pipe is leaking water on the road", ComplaintType.WATER_PIPE),
        ("No water supply is available in the building", ComplaintType.WATER_OUTAGE),
        ("The sidewalk is cracked and dangerous", ComplaintType.SIDEWALK),
        ("The streetlight is broken and the road is dark", ComplaintType.STREETLIGHT),
        ("A traffic accident caused a road closure", ComplaintType.TRAFFIC_INCIDENT),
        ("There is an unsafe open manhole and public safety hazard", ComplaintType.PUBLIC_SAFETY),
        ("Please check this unclear municipal issue", ComplaintType.OTHER),
    ],
)
def test_issue_type_classification(import_service_module, text, expected):
    extractor_mod = import_service_module("text_understanding", "app.extractor")
    result = extractor_mod.StructuredExtractor().extract("c1", text)
    assert result.issue_type == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("This is life threatening and an emergency", SeverityLevel.CRITICAL),
        ("A very deep pothole is causing accident risk", SeverityLevel.CRITICAL),
        ("A big hole is causing serious traffic jam", SeverityLevel.HIGH),
        ("Several moderate cracks are causing traffic", SeverityLevel.MEDIUM),
        ("A small minor crack exists", SeverityLevel.LOW),
    ],
)
def test_severity_keyword_precedence(import_service_module, text, expected):
    extractor_mod = import_service_module("text_understanding", "app.extractor")
    assert extractor_mod.StructuredExtractor()._estimate_severity(text) == expected


def test_location_extraction_deduplicates_and_maps_admin_areas(import_service_module):
    extractor_mod = import_service_module("text_understanding", "app.extractor")
    loc = extractor_mod.StructuredExtractor()._extract_location("Hamra and hamra near Beirut")
    assert loc.raw == "Hamra, Beirut"
    assert loc.normalized == "Hamra"
    assert loc.district == "Beirut"
    assert loc.governorate == "Beirut Governorate"


def test_signal_and_summary_generation(import_service_module):
    extractor_mod = import_service_module("text_understanding", "app.extractor")
    result = extractor_mod.StructuredExtractor().extract(
        "c1",
        "Urgent dangerous pothole in Hamra causing traffic and no one came before",
    )
    assert result.signals.public_safety_risk is True
    assert result.signals.traffic_impact is True
    assert result.signals.corruption_signal is True
    assert result.signals.emergency_signal is True
    assert "urgent" in result.urgency_keywords
    assert result.summary == "Pothole reported in Hamra"

