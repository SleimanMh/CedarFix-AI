"""
Integration tests for IEP-Governance — requires containers to be running.
Run with: docker-compose up -d && python -m pytest tests/test_governance.py -v
"""
import pytest
import httpx

GOVERNANCE_URL = "http://localhost:8003"

GOOD_RECORDS = [
    {
        "slot_start": f"2021-08-01T{h:02d}:00:00",
        "predicted_kw": 10.0 + i * 0.1,
        "actual_kw": 10.0 + i * 0.2,
    }
    for i, h in enumerate(range(24))
]

PERFECT_RECORDS = [
    {"slot_start": f"2021-08-01T{h:02d}:00:00", "predicted_kw": 10.0, "actual_kw": 10.0}
    for h in range(24)
]

DRIFTED_RECORDS = [
    {"slot_start": f"2021-08-01T{h:02d}:00:00", "predicted_kw": 5.0, "actual_kw": 50.0}
    for h in range(24)
]


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=GOVERNANCE_URL, timeout=30.0) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_governance_status_returns_200(client):
    r = client.post("/governance/status", json={"records": GOOD_RECORDS})
    assert r.status_code == 200


def test_governance_status_has_required_fields(client):
    r = client.post("/governance/status", json={"records": GOOD_RECORDS})
    data = r.json()
    assert "mae" in data
    assert "psi" in data
    assert "drift_detected" in data
    assert "retrain_recommended" in data
    assert "decision" in data


def test_governance_mae_non_negative(client):
    r = client.post("/governance/status", json={"records": GOOD_RECORDS})
    assert r.json()["mae"] >= 0


def test_governance_perfect_predictions_no_drift(client):
    """Perfect predictions should give MAE=0 and no drift."""
    r = client.post("/governance/status", json={"records": PERFECT_RECORDS})
    data = r.json()
    assert data["mae"] == pytest.approx(0.0, abs=0.01)
    assert data["drift_detected"] is False
    assert data["retrain_recommended"] is False


def test_governance_large_error_triggers_retrain(client):
    """Severely wrong predictions should trigger retrain recommendation."""
    r = client.post("/governance/status", json={"records": DRIFTED_RECORDS})
    data = r.json()
    assert data["mae"] > 1.0
    assert data["retrain_recommended"] is True


def test_governance_psi_non_negative(client):
    r = client.post("/governance/status", json={"records": GOOD_RECORDS})
    assert r.json()["psi"] >= 0


def test_retrain_endpoint(client):
    r = client.post("/governance/retrain", timeout=120.0)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert "train_mae" in data
    assert "train_rmse" in data
    assert data["train_rows"] > 0
    # Promotion gate fields
    assert "promoted" in data
    assert isinstance(data["promoted"], bool)
    assert "promotion_decision" in data
    # Gate checks are explicit per-gate results
    assert "gate_checks" in data
    assert isinstance(data["gate_checks"], list)
    assert len(data["gate_checks"]) >= 3  # mae, rmse, coverage at minimum
    for g in data["gate_checks"]:
        assert "gate" in g and "passed" in g and "detail" in g
    # Comparison block with candidate + production
    assert "comparison" in data
    assert "candidate" in data["comparison"]
    # With unchanged data+hyperparams, the gate should pass
    assert data["promoted"] is True
    assert data["promotion_decision"].startswith("PROMOTED")
    assert all(g["passed"] for g in data["gate_checks"])


def test_governance_empty_records(client):
    """Empty records list should return 422 or handle gracefully."""
    r = client.post("/governance/status", json={"records": []})
    assert r.status_code in (200, 422)
