from __future__ import annotations


def test_template_explanation_includes_route_duplicate_and_factors(import_service_module):
    main = import_service_module("explanation_service", "app.main")
    req = main.ExplainRequest(
        complaint_id="c1",
        complaint_type="water_pipe",
        severity="high",
        assigned_entity="Beirut Water Authority",
        routing_confidence=0.9,
        is_duplicate=True,
        urgency_factors=["Cluster size 4", "High-risk district", "Visual severity HIGH"],
    )

    text, factors = main._generate_template(req)

    assert "water pipe" in text
    assert "HIGH severity" in text
    assert "duplicate" in text
    assert "Beirut Water Authority" in text
    assert factors[:2] == ["Severity: high", "Duplicate complaint detected"]


def test_llm_mode_currently_falls_back_to_template(import_service_module):
    main = import_service_module("explanation_service", "app.main")
    req = main.ExplainRequest(complaint_id="c1", complaint_type="pothole")
    assert main._generate_llm(req) == main._generate_template(req)

