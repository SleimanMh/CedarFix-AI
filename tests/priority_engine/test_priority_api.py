from __future__ import annotations

from fastapi.testclient import TestClient


def test_priority_api_health_and_predict(import_service_module):
    main = import_service_module("priority_engine", "app.main")
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "priority-engine"

    response = client.post(
        "/predict",
        json={
            "complaint_id": "c1",
            "complaint_type": "flooding",
            "cluster_size": 1,
            "visual_severity": "HIGH",
            "location_district": "Tripoli",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["complaint_id"] == "c1"
    assert body["severity"] == "CRITICAL"

