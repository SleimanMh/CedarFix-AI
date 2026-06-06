from __future__ import annotations

from fastapi.testclient import TestClient


def test_monitoring_api_health_report_and_retrain(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    main = import_service_module("monitoring_service", "app.main")

    async def report():
        return {"routing_accuracy_7d": 0.9, "drift_alert": False}

    async def retrain(_model):
        return None

    monkeypatch.setattr(main, "compute_drift_metrics", report)
    monkeypatch.setattr(main, "trigger_retraining_job", retrain)
    client = TestClient(main.app)

    assert client.get("/health").json()["service"] == "monitoring-service"
    assert client.get("/drift/report").json()["routing_accuracy_7d"] == 0.9
    assert client.post("/retrain/trigger?model=routing").json() == {
        "status": "retraining_triggered",
        "model": "routing",
    }
