from __future__ import annotations

from fastapi.testclient import TestClient


def test_explanation_api_health_and_explain(import_service_module):
    main = import_service_module("explanation_service", "app.main")
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "explanation-service"

    response = client.post(
        "/explain",
        json={
            "complaint_id": "c1",
            "complaint_type": "pothole",
            "severity": "medium",
            "assigned_entity": "Ministry of Public Works",
            "routing_confidence": 0.86,
        },
    )

    assert response.status_code == 200
    assert response.json()["complaint_id"] == "c1"
    assert "pothole" in response.json()["explanation_text"]

