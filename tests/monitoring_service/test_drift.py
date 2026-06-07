from __future__ import annotations

import asyncio


class FakeMappings:
    def __init__(self, row):
        self._row = row

    def first(self):
        return self._row


class FakeResult:
    def __init__(self, *, row=None, scalar_value=None):
        self._row = row
        self._scalar = scalar_value

    def mappings(self):
        return FakeMappings(self._row)

    def scalar(self):
        return self._scalar


class FakeSession:
    def __init__(self, results):
        self.results = list(results)
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, statement):
        self.executed.append(str(statement))
        return self.results.pop(0)


def test_compute_drift_metrics_success(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    drift = import_service_module("monitoring_service", "app.drift")
    session = FakeSession([
        FakeResult(row={"total": 20, "corrected": 4}),
        FakeResult(scalar_value=0.81234),
    ])
    monkeypatch.setattr(drift, "Session", lambda: session)

    report = asyncio.run(drift.compute_drift_metrics())

    assert report["routing_accuracy_7d"] == 0.8
    assert report["admin_correction_rate"] == 0.2
    assert report["avg_routing_confidence_7d"] == 0.8123
    assert report["drift_alert"] is True


def test_compute_drift_metrics_empty_window(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    drift = import_service_module("monitoring_service", "app.drift")
    session = FakeSession([
        FakeResult(row={"total": 0, "corrected": None}),
        FakeResult(scalar_value=None),
    ])
    monkeypatch.setattr(drift, "Session", lambda: session)

    report = asyncio.run(drift.compute_drift_metrics())

    assert report["routing_accuracy_7d"] == 1.0
    assert report["admin_correction_rate"] == 0.0
    assert report["avg_routing_confidence_7d"] == 0.0
    assert report["drift_alert"] is False


def test_compute_drift_metrics_returns_error_payload_on_failure(import_service_module, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    drift = import_service_module("monitoring_service", "app.drift")

    def broken_session():
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(drift, "Session", broken_session)

    report = asyncio.run(drift.compute_drift_metrics())

    assert "db unavailable" in report["error"]
    assert report["drift_alert"] is False

