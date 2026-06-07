from __future__ import annotations

import pytest

from cedarfix_shared.schemas import SeverityLevel


def test_priority_score_combines_and_caps_factors(import_service_module):
    scorer_mod = import_service_module("priority_engine", "app.scorer")
    result = scorer_mod.PriorityScorer().score(
        complaint_id="c1",
        complaint_type="flooding",
        cluster_size=20,
        visual_severity="CRITICAL",
        location_district="Tripoli",
        top_similarity_score=0.0,
    )
    assert result.priority_score == 1.0
    assert result.cluster_size_factor == 0.3
    assert result.visual_severity_factor == 0.4
    assert result.location_risk_factor == 0.15
    assert result.severity == SeverityLevel.CRITICAL


@pytest.mark.parametrize(
    ("score", "expected"),
    [
        (0.39, SeverityLevel.LOW),
        (0.4, SeverityLevel.MEDIUM),
        (0.6, SeverityLevel.HIGH),
        (0.8, SeverityLevel.CRITICAL),
    ],
)
def test_priority_severity_boundaries(import_service_module, score, expected):
    scorer_mod = import_service_module("priority_engine", "app.scorer")
    assert scorer_mod.PriorityScorer()._map_severity(score) == expected


def test_priority_unknown_type_and_medium_risk_location(import_service_module):
    scorer_mod = import_service_module("priority_engine", "app.scorer")
    result = scorer_mod.PriorityScorer().score(
        complaint_id="c1",
        complaint_type="mystery",
        cluster_size=1,
        visual_severity="UNKNOWN",
        location_district="Hamra",
        top_similarity_score=0.0,
    )
    assert result.complaint_type_factor == 0.3
    assert result.cluster_size_factor == 0.05
    assert result.location_risk_factor == 0.08
    assert result.priority_score == 0.43

