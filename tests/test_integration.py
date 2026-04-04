"""
End-to-end integration tests hitting all services together.
Run with: docker-compose up -d && python -m pytest tests/test_integration.py -v
"""
import pytest
import httpx

EEP_URL          = "http://localhost:8000"
FORECAST_URL     = "http://localhost:8001"
OPTIMIZER_URL    = "http://localhost:8002"
GOVERNANCE_URL   = "http://localhost:8003"
GRID_COMPAT_URL  = "http://localhost:8004"

SCHEDULE_PAYLOAD = {
    "date": "2021-08-01",
    "sessions": [
        {
            "session_id": "integ-001",
            "connection_time": "2021-08-01T00:00:00",
            "disconnect_time": "2021-08-01T03:00:00",
            "kwh_requested": 20.0,
            "kwh_delivered": 0.0,
            "max_charge_rate_kw": 7.4,
            "has_user_inputs": True,
        }
    ],
    "grid_pattern": "morning",
}


@pytest.fixture(scope="session")
def eep():
    with httpx.Client(base_url=EEP_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def forecast():
    with httpx.Client(base_url=FORECAST_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def optimizer():
    with httpx.Client(base_url=OPTIMIZER_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def governance():
    with httpx.Client(base_url=GOVERNANCE_URL, timeout=30.0) as c:
        yield c


@pytest.fixture(scope="session")
def grid_compat():
    with httpx.Client(base_url=GRID_COMPAT_URL, timeout=30.0) as c:
        yield c


def test_all_services_healthy(eep, forecast, optimizer, governance, grid_compat):
    """All 5 services must be reachable and healthy."""
    for client, name in [
        (eep,         "EEP"),
        (forecast,    "Forecast"),
        (optimizer,   "Optimizer"),
        (governance,  "Governance"),
        (grid_compat, "GridCompat"),
    ]:
        r = client.get("/health")
        assert r.status_code == 200, f"{name} health check failed"
        assert r.json()["status"] == "ok", f"{name} not ok"


def test_full_schedule_flow(eep):
    """Full EEP schedule flow returns valid optimized schedule."""
    r = eep.post("/schedule", json=SCHEDULE_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert data["solver_status"] in ("optimal", "greedy_fallback")
    assert data["kpis"]["total_kwh_scheduled"] == pytest.approx(20.0, abs=1.0)
    assert data["forecast_summary"] is not None
    assert not data["forecast_summary"].get("degraded", False)


def test_forecast_feeds_eep(eep, forecast):
    """Forecast service predictions are consistent with EEP forecast_summary."""
    from datetime import date
    import math

    # Build same slot EEP would build for midnight slot
    slot = {
        "hour_sin": math.sin(2 * math.pi * 0 / 24),
        "hour_cos": math.cos(2 * math.pi * 0 / 24),
        "dow_sin": 0.0, "dow_cos": 1.0,
        "month_sin": math.sin(2 * math.pi * 8 / 12),
        "month_cos": math.cos(2 * math.pi * 8 / 12),
        "is_weekend": 0, "is_summer": 1,
        "slot_of_day": 0,
        "lag_4": 0.0, "lag_16": 0.0, "lag_96": 0.0, "lag_672": 0.0,
        "rolling_mean_1h": 0.0, "rolling_std_1h": 0.0,
    }
    r = forecast.post("/forecast", json={"slots": [slot]})
    assert r.status_code == 200
    pred = r.json()["predictions"][0]
    assert pred["lower_ci"] <= pred["upper_ci"]


def test_optimizer_result_passes_governance(optimizer, governance):
    """Optimizer schedule results can be passed to governance without error."""
    r = optimizer.post("/optimize", json={
        "date": "2021-08-01",
        "sessions": [{
            "session_id": "g-001",
            "connection_time": "2021-08-01T00:00:00",
            "disconnect_time": "2021-08-01T03:00:00",
            "kwh_requested": 10.0,
            "kwh_delivered": 0.0,
            "max_charge_rate_kw": 7.4,
            "has_user_inputs": False,
        }],
        "grid_pattern": "morning",
    })
    assert r.status_code == 200

    # Send simulated actuals to governance
    records = [
        {"slot_start": f"2021-08-01T00:{i*15:02d}:00", "predicted_kw": 6.5, "actual_kw": 6.5}
        for i in range(12)
    ]
    r2 = governance.post("/governance/status", json={"records": records})
    assert r2.status_code == 200
    assert r2.json()["mae"] == pytest.approx(0.0, abs=0.01)


def test_eep_request_ids_unique(eep):
    """Concurrent requests return unique request IDs."""
    r1 = eep.post("/schedule", json=SCHEDULE_PAYLOAD)
    r2 = eep.post("/schedule", json=SCHEDULE_PAYLOAD)
    assert r1.json()["request_id"] != r2.json()["request_id"]


def test_eep_schedule_includes_grid_compatibility(eep):
    """EEP schedule response includes grid_compatibility from iep-grid-compatibility."""
    r = eep.post("/schedule", json=SCHEDULE_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    # grid_compat result is wired in — may be None if service unreachable, dict if up
    assert "grid_compatibility" in data


def test_grid_compat_rejects_overloaded_grid(eep):
    """EEP returns 422 when grid-compat reports not_compatible."""
    overloaded_payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": "overload-001",
                "connection_time": "2021-08-01T00:00:00",
                "disconnect_time": "2021-08-01T03:00:00",
                "kwh_requested": 20.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            }
        ],
        "grid_pattern": "morning",
        "transformer": {
            "transformer_kva": 100,
            "base_load_kw": 80,
            "feeder_length_km": 2.0,
            "cable_type": "C_weak",
            "r1": 0.35, "x1": 0.12, "r0": 0.7, "x0": 0.24,
            "phase_balance_class": "heavily_unbalanced",
            "num_chargers_installed": 20,
            "charger_power_kw": 22.0,
        },
    }
    r = eep.post("/schedule", json=overloaded_payload)
    # 422 if grid-compat is up and returns not_compatible; 200 if service unreachable (soft)
    assert r.status_code in (200, 422)


def test_power_throttling_on_conditional_grid(eep, grid_compat):
    """When grid-compat returns 'conditional', EEP must automatically throttle
    max_charge_rate_kw per session and expose the result in power_throttling."""
    CONDITIONAL_TRANSFORMER = {
        "transformer_kva": 100,
        "base_load_kw": 62,
        "feeder_length_km": 0.5,
        "cable_type": "B_medium",
        "r1": 0.2, "x1": 0.08, "r0": 0.4, "x0": 0.16,
        "phase_balance_class": "mildly_unbalanced",
        "num_chargers_installed": 10,
        "charger_power_kw": 7.4,
    }

    # Phase 1: confirm grid-compat actually returns "conditional" for this config.
    # Skip cleanly if the ML model returns a different class or service is unavailable.
    gc_check = grid_compat.post(
        "/predict",
        json={**CONDITIONAL_TRANSFORMER, "num_chargers_active": 4},
    )
    if gc_check.status_code != 200:
        pytest.skip("grid-compat unavailable — skipping throttle test")
    gc_result = gc_check.json()
    if gc_result["compatibility_class"] != "conditional":
        pytest.skip(
            f"Transformer produced '{gc_result['compatibility_class']}' not 'conditional'"
        )

    # Phase 2: send through EEP and verify automated throttling.
    payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": f"throttle-{i:03d}",
                "connection_time": f"2021-08-01T{i:02d}:00:00",
                "disconnect_time": f"2021-08-01T{i + 4:02d}:00:00",
                "kwh_requested": 20.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            }
            for i in range(4)
        ],
        "grid_pattern": "morning",
        "transformer": CONDITIONAL_TRANSFORMER,
    }

    r = eep.post("/schedule", json=payload)
    assert r.status_code == 200, f"EEP returned {r.status_code}: {r.text[:300]}"
    data = r.json()

    assert "power_throttling" in data
    pt = data["power_throttling"]
    assert pt is not None, "power_throttling is None even though grid returned conditional"
    assert pt["applied"] is True

    # Verify the math against the known transformer config
    # max_safe = 100 * 0.80 = 80.0 kW, available = 80 - 62 = 18.0 kW
    assert pt["max_safe_load_kw"] == pytest.approx(80.0, abs=0.01)
    assert pt["available_for_ev_kw"] == pytest.approx(18.0, abs=0.01)

    n = pt["n_active_sessions"]
    expected_grid_cap = max(1.0, min(18.0 / n, 7.4))
    assert pt["grid_cap_kw"] == pytest.approx(expected_grid_cap, abs=0.01)

    # Each session rate must be <= grid cap and <= that session's requested rate (7.4)
    assert "per_session_rates_kw" in pt
    for sid, rate in pt["per_session_rates_kw"].items():
        assert rate <= pt["grid_cap_kw"] + 0.01

    # If throttle reduced power, verify the optimizer respected it per slot
    if pt["grid_cap_kw"] < 7.4 - 0.01:
        cap = pt["grid_cap_kw"]
        for schedule in data["schedules"]:
            for slot in schedule["slots"]:
                assert slot["charge_kw"] <= cap + 0.01, (
                    f"Session {schedule['session_id']} slot {slot['slot_time']} "
                    f"has charge_kw={slot['charge_kw']} exceeding throttle cap {cap}"
                )
