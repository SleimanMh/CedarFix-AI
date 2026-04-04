"""
Integration tests for IEP-Forecast — requires containers to be running.
Run with: docker-compose up -d && python -m pytest tests/test_forecast.py -v
"""
import pytest
import httpx

FORECAST_URL = "http://localhost:8001"

VALID_SLOT = {
    "hour_sin": 0.5, "hour_cos": 0.866,
    "dow_sin": 0.0, "dow_cos": 1.0,
    "month_sin": 0.866, "month_cos": 0.5,
    "is_weekend": 0, "is_summer": 1,
    "slot_of_day": 36,
    "lag_4": 5.0, "lag_16": 4.0, "lag_96": 6.0, "lag_672": 5.5,
    "rolling_mean_1h": 5.0, "rolling_std_1h": 0.5,
}


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=FORECAST_URL, timeout=30.0) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_forecast_single_slot(client):
    r = client.post("/forecast", json={"slots": [VALID_SLOT]})
    assert r.status_code == 200
    data = r.json()
    assert "predictions" in data
    assert len(data["predictions"]) == 1
    pred = data["predictions"][0]
    assert "predicted_kw" in pred
    assert "lower_ci" in pred
    assert "upper_ci" in pred


@pytest.mark.parametrize("endpoint,payload", [
    ("/forecast", {"slots": [VALID_SLOT]}),
    ("/forecast/horizon", {"current_time": "2021-08-01T00:00:00Z", "horizon_slots": 6, "recent_kw": [6.0, 5.5, 5.2, 5.0]}),
])
def test_forecast_ci_bounds_valid(client, endpoint, payload):
    """Lower CI <= mean prediction <= upper CI for both endpoints."""
    r = client.post(endpoint, json=payload)
    assert r.status_code == 200
    for pred in r.json()["predictions"]:
        assert pred["lower_ci"] <= pred["predicted_kw"] <= pred["upper_ci"]


def test_forecast_multiple_slots(client):
    """Multiple slots return one prediction per slot."""
    slots = [VALID_SLOT] * 5
    r = client.post("/forecast", json={"slots": slots})
    assert r.status_code == 200
    assert len(r.json()["predictions"]) == 5


def test_forecast_missing_feature(client):
    """Slot missing required features returns 422."""
    r = client.post("/forecast", json={"slots": [{"hour_sin": 0.5}]})
    assert r.status_code == 422


def test_forecast_empty_slots(client):
    """Empty slots list returns 200 with empty predictions."""
    r = client.post("/forecast", json={"slots": []})
    assert r.status_code == 200
    assert r.json()["predictions"] == []


def test_forecast_model_version_present(client):
    """Response includes model_version field."""
    r = client.post("/forecast", json={"slots": [VALID_SLOT]})
    assert r.status_code == 200
    assert "model_version" in r.json()


def test_forecast_horizon_basic(client):
    """Convenience endpoint should return N slot predictions with timestamps."""
    payload = {
        "current_time": "2021-08-01T00:00:00Z",
        "horizon_slots": 4,
        "recent_kw": [6.0, 5.5, 5.2, 5.0],
    }
    r = client.post("/forecast/horizon", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["n_slots"] == 4
    assert len(data["predictions"]) == 4
    assert "slot_start" in data["predictions"][0]


def test_forecast_horizon_invalid_horizon(client):
    """horizon_slots must be >= 1."""
    payload = {"current_time": "2021-08-01T00:00:00Z", "horizon_slots": 0}
    r = client.post("/forecast/horizon", json=payload)
    assert r.status_code == 422
