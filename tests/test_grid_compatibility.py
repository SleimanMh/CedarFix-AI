"""
Integration tests for iep-grid-compatibility service (port 8004).

Run with services up:
    docker compose up -d
    pytest tests/test_grid_compatibility.py -v
"""

import pytest
import requests

BASE_URL = "http://localhost:8004"

# ── Shared fixtures ────────────────────────────────────────────────────────────

COMPATIBLE_PAYLOAD = {
    # Small load on large transformer — should be compatible
    "transformer_kva": 500,
    "base_load_kw": 30,
    "feeder_length_km": 0.1,
    "cable_type": "A_strong",
    "r1": 0.1, "x1": 0.05, "r0": 0.2, "x0": 0.1,
    "phase_balance_class": "balanced",
    "num_chargers_installed": 5,
    "num_chargers_active": 2,
    "charger_power_kw": 7.4,
}

INCOMPATIBLE_PAYLOAD = {
    # Extreme overload — should be not_compatible
    "transformer_kva": 100,
    "base_load_kw": 80,
    "feeder_length_km": 2.0,
    "cable_type": "C_weak",
    "r1": 0.35, "x1": 0.12, "r0": 0.7, "x0": 0.24,
    "phase_balance_class": "heavily_unbalanced",
    "num_chargers_installed": 20,
    "num_chargers_active": 20,
    "charger_power_kw": 22.0,
}


# ── Health ────────────────────────────────────────────────────────────────────

def test_health():
    resp = requests.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["models_loaded"] is True


# ── /predict — response structure ────────────────────────────────────────────

def test_predict_returns_200():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    assert resp.status_code == 200


def test_predict_has_required_fields():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    data = resp.json()
    assert "compatibility_class" in data
    assert "confidence" in data
    assert "class_probabilities" in data
    assert "recommended_max_active_chargers" in data
    assert "stage2_applied" in data
    assert "nominal_load_ratio" in data
    assert "nominal_headroom_kw" in data


def test_predict_confidence_in_range():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    data = resp.json()
    assert 0.0 <= data["confidence"] <= 1.0


def test_predict_class_probabilities_sum_to_one():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    probs = resp.json()["class_probabilities"]
    assert abs(sum(probs.values()) - 1.0) < 0.01
    assert set(probs.keys()) == {"compatible", "conditional", "not_compatible"}


# ── /predict — semantic correctness ──────────────────────────────────────────

def test_overloaded_grid_predicted_not_compatible():
    resp = requests.post(f"{BASE_URL}/predict", json=INCOMPATIBLE_PAYLOAD, timeout=10)
    assert resp.status_code == 200
    data = resp.json()
    assert data["compatibility_class"] == "not_compatible"
    assert data["recommended_max_active_chargers"] == 0
    assert data["stage2_applied"] is False


def test_not_compatible_skips_stage2():
    resp = requests.post(f"{BASE_URL}/predict", json=INCOMPATIBLE_PAYLOAD, timeout=10)
    data = resp.json()
    assert data["stage2_applied"] is False
    assert data["recommended_max_active_chargers"] == 0


def test_nominal_load_ratio_is_computed_correctly():
    payload = {**COMPATIBLE_PAYLOAD}
    # nominal_load_ratio = (base_load + n_active * charger_kw) / transformer_kva
    # = (30 + 2 * 7.4) / 500 = 44.8 / 500 = 0.0896
    resp = requests.post(f"{BASE_URL}/predict", json=payload, timeout=10)
    data = resp.json()
    expected = (30 + 2 * 7.4) / 500
    assert abs(data["nominal_load_ratio"] - expected) < 0.01


def test_recommended_max_chargers_non_negative():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    assert resp.json()["recommended_max_active_chargers"] >= 0


def test_recommended_max_chargers_does_not_exceed_installed():
    resp = requests.post(f"{BASE_URL}/predict", json=COMPATIBLE_PAYLOAD, timeout=10)
    data = resp.json()
    assert data["recommended_max_active_chargers"] <= COMPATIBLE_PAYLOAD["num_chargers_installed"]


# ── /predict — input validation ───────────────────────────────────────────────

def test_invalid_cable_type_returns_422():
    payload = {**COMPATIBLE_PAYLOAD, "cable_type": "D_nonexistent"}
    resp = requests.post(f"{BASE_URL}/predict", json=payload, timeout=10)
    assert resp.status_code == 422


def test_invalid_phase_balance_returns_422():
    payload = {**COMPATIBLE_PAYLOAD, "phase_balance_class": "totally_wrong"}
    resp = requests.post(f"{BASE_URL}/predict", json=payload, timeout=10)
    assert resp.status_code == 422


def test_active_chargers_exceeding_installed_returns_422():
    payload = {**COMPATIBLE_PAYLOAD, "num_chargers_active": 100, "num_chargers_installed": 5}
    resp = requests.post(f"{BASE_URL}/predict", json=payload, timeout=10)
    assert resp.status_code == 422


def test_missing_required_field_returns_422():
    payload = {k: v for k, v in COMPATIBLE_PAYLOAD.items() if k != "transformer_kva"}
    resp = requests.post(f"{BASE_URL}/predict", json=payload, timeout=10)
    assert resp.status_code == 422


# ── /model-info ───────────────────────────────────────────────────────────────

def test_model_info_returns_metrics():
    resp = requests.get(f"{BASE_URL}/model-info", timeout=5)
    assert resp.status_code == 200
    data = resp.json()
    assert "classifier" in data
    assert "regressor" in data
    assert data["classifier"]["macro_f1"] > 0.9
    assert data["regressor"]["r2"] > 0.9
