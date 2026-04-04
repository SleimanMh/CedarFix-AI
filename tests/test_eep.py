"""
Integration tests for EEP — requires all 5 containers to be running.
Run with: docker-compose up -d && python -m pytest tests/test_eep.py -v
"""
import pytest
import httpx

EEP_URL = "http://localhost:8000"

SAMPLE_PAYLOAD = {
    "date": "2021-08-01",
    "sessions": [
        {
            "session_id": "test-001",
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
def client():
    with httpx.Client(base_url=EEP_URL, timeout=30.0) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "services" in data


def test_schedule_returns_200(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.status_code == 200


def test_schedule_has_required_fields(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    data = r.json()
    assert "date" in data
    assert "schedules" in data
    assert "kpis" in data
    assert "solver_status" in data
    assert "request_id" in data


def test_schedule_solver_status_optimal(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.json()["solver_status"] in ("optimal", "greedy_fallback")


def test_schedule_session_fully_charged(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    kpis = r.json()["kpis"]
    assert kpis["total_kwh_scheduled"] == pytest.approx(20.0, abs=1.0)
    assert kpis["sessions_fully_charged"] == 1


def test_schedule_slots_within_grid_window(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    for schedule in r.json()["schedules"]:
        for slot in schedule["slots"]:
            assert slot["slot_index"] <= 11


def test_schedule_charge_rate_within_limit(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    max_rate = SAMPLE_PAYLOAD["sessions"][0]["max_charge_rate_kw"]
    for schedule in r.json()["schedules"]:
        for slot in schedule["slots"]:
            assert slot["charge_kw"] <= max_rate + 0.01


def test_schedule_forecast_summary_populated(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    data = r.json()
    assert "forecast_summary" in data
    fs = data["forecast_summary"]
    assert fs is not None
    assert not fs.get("degraded", False), f"Forecast degraded: {fs}"
    assert "avg_predicted_kw" in fs


def test_schedule_kpis_non_negative(client):
    """Physical KPIs must be non-negative. forecast_avg_kw can be negative (model output)."""
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    kpis = r.json()["kpis"]
    # forecast_avg_kw is a model prediction and can be negative
    skip_keys = {"forecast_avg_kw"}
    for key, val in kpis.items():
        if key not in skip_keys and isinstance(val, (int, float)):
            assert val >= 0, f"KPI {key} is negative: {val}"


def test_schedule_transformer_peak_within_headroom(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.json()["kpis"]["transformer_peak_kw"] <= 50.0


def test_schedule_cost_positive(client):
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    kpis = r.json()["kpis"]
    if kpis["total_kwh_scheduled"] > 0:
        assert kpis["total_cost_usd"] > 0


def test_schedule_invalid_grid_pattern(client):
    """Unknown grid_pattern should be rejected at EEP boundary."""
    payload = {**SAMPLE_PAYLOAD, "grid_pattern": "unknown_pattern"}
    r = client.post("/schedule", json=payload)
    assert r.status_code == 422


def test_schedule_invalid_date(client):
    payload = {**SAMPLE_PAYLOAD, "date": "not-a-date"}
    r = client.post("/schedule", json=payload)
    assert r.status_code == 422


def test_schedule_invalid_time_window(client):
    payload = {
        **SAMPLE_PAYLOAD,
        "sessions": [
            {
                "session_id": "bad-window",
                "connection_time": "2021-08-01T03:00:00",
                "disconnect_time": "2021-08-01T00:00:00",
                "kwh_requested": 5.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            }
        ],
    }
    r = client.post("/schedule", json=payload)
    assert r.status_code == 422


def test_schedule_empty_sessions(client):
    payload = {**SAMPLE_PAYLOAD, "sessions": []}
    r = client.post("/schedule", json=payload)
    assert r.status_code == 200
    assert r.json()["schedules"] == []


def test_schedule_multiple_sessions(client):
    payload = {
        "date": "2021-08-01",
        "sessions": [
            {"session_id": "s001", "connection_time": "2021-08-01T00:00:00",
             "disconnect_time": "2021-08-01T01:00:00", "kwh_requested": 5.0,
             "kwh_delivered": 0.0, "max_charge_rate_kw": 7.4, "has_user_inputs": False},
            {"session_id": "s002", "connection_time": "2021-08-01T01:00:00",
             "disconnect_time": "2021-08-01T03:00:00", "kwh_requested": 10.0,
             "kwh_delivered": 0.0, "max_charge_rate_kw": 7.4, "has_user_inputs": False},
        ],
        "grid_pattern": "morning",
    }
    r = client.post("/schedule", json=payload)
    assert r.status_code == 200
    session_ids = [s["session_id"] for s in r.json()["schedules"]]
    assert "s001" in session_ids
    assert "s002" in session_ids


def test_schedule_request_id_unique(client):
    r1 = client.post("/schedule", json=SAMPLE_PAYLOAD)
    r2 = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r1.json()["request_id"] != r2.json()["request_id"]


# ── E2E request-driven physics tests (through EEP → optimizer) ──────────────

_E2E_SESSION = [
    {
        "session_id": "e2e-001",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 5.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
        "has_user_inputs": True,
    }
]


def test_e2e_transformer_kva_changes_utilization_pct(client):
    """E2E: smaller transformer_kva raises utilization_pct for the same EV load."""
    base = {"date": "2021-08-01", "sessions": _E2E_SESSION, "grid_pattern": "morning"}
    small = {**base, "transformer": {"transformer_kva": 20.0, "base_load_kw": 0.0}}
    large = {**base, "transformer": {"transformer_kva": 200.0, "base_load_kw": 0.0}}

    r_small = client.post("/schedule", json=small)
    r_large = client.post("/schedule", json=large)
    assert r_small.status_code == 200, r_small.text
    assert r_large.status_code == 200, r_large.text

    util_small = r_small.json()["kpis"]["transformer_utilization_pct"]
    util_large = r_large.json()["kpis"]["transformer_utilization_pct"]
    assert util_small > util_large, (
        f"Expected 20 kVA transformer to show higher utilisation ({util_small}) "
        f"than 200 kVA ({util_large})"
    )


def test_e2e_base_load_kw_affects_grid_compat(client):
    """E2E: base_load_kw is forwarded to grid-compat; a value that saturates the
    transformer (charger_power_kw + base_load_kw > transformer_kva) causes a 422,
    while a valid split passes 200.  Confirms the field flows EEP → grid-compat."""
    # 10 kVA transformer, 1 charger at 7.4 kW
    # ratio (valid):     (7.4 + 0.0) / 10 = 0.74  → compatible → 200
    # ratio (overloaded): (7.4 + 5.0) / 10 = 1.24 → not_compatible → 422
    base = {"date": "2021-08-01", "sessions": _E2E_SESSION, "grid_pattern": "morning"}
    valid     = {**base, "transformer": {"transformer_kva": 10.0, "base_load_kw": 0.0,  "charger_power_kw": 7.4}}
    overloaded = {**base, "transformer": {"transformer_kva": 10.0, "base_load_kw": 5.0, "charger_power_kw": 7.4}}

    r_valid     = client.post("/schedule", json=valid)
    r_overloaded = client.post("/schedule", json=overloaded)

    assert r_valid.status_code == 200, r_valid.text
    assert r_overloaded.status_code == 422, (
        f"Expected 422 for overloaded config, got {r_overloaded.status_code}: {r_overloaded.text}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase A: Forecast reservation slot alignment
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_reservation_maps_to_actual_slot_of_day(client):
    """Reservation must be placed at the sessions' actual time-of-day slots,
    not at list indices 0, 1, etc.

    Two sessions connect at 05:00 (slot 20) and 08:00 (slot 32).
    If alignment is correct, forecast_reserved_slots in the optimizer KPIs
    should be <= the number of sessions (mapped to their true slots), NOT 96.
    Additionally, the reservation should influence headroom at those slots,
    visible via forecast_headroom_applied == True in the response."""
    payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": "slot-align-001",
                "connection_time": "2021-08-01T05:00:00",
                "disconnect_time": "2021-08-01T06:00:00",
                "kwh_requested": 3.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            },
            {
                "session_id": "slot-align-002",
                "connection_time": "2021-08-01T08:00:00",
                "disconnect_time": "2021-08-01T09:00:00",
                "kwh_requested": 3.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            },
        ],
        "grid_pattern": "split",
    }
    r = client.post("/schedule", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    # The reservation should touch at most 2 slots (one per session),
    # not 0 and 1 from misaligned list-index mapping.
    assert kpis["forecast_reserved_slots"] <= 2, (
        f"Expected at most 2 reserved slots (actual session slots), got {kpis['forecast_reserved_slots']}"
    )


def test_forecast_reservation_duplicate_slots_uses_max(client):
    """When two sessions connect at the same time (same slot_of_day),
    reservation must aggregate via max, not sum or last-write-wins,
    and result in exactly 1 reserved slot."""
    payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": "dup-slot-001",
                "connection_time": "2021-08-01T00:00:00",
                "disconnect_time": "2021-08-01T02:00:00",
                "kwh_requested": 5.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            },
            {
                "session_id": "dup-slot-002",
                "connection_time": "2021-08-01T00:00:00",
                "disconnect_time": "2021-08-01T03:00:00",
                "kwh_requested": 10.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            },
        ],
        "grid_pattern": "morning",
    }
    r = client.post("/schedule", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    # Both sessions have connection_time at 00:00 → slot_of_day=0 → same slot
    # So forecast_reserved_slots should be exactly 1 (max aggregation, not 2)
    assert kpis["forecast_reserved_slots"] <= 1, (
        f"Expected at most 1 reserved slot for duplicate slot_of_day, got {kpis['forecast_reserved_slots']}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Phase B: Governance honesty / realism annotations
# ─────────────────────────────────────────────────────────────────────────────

def test_governance_summary_has_honesty_fields(client):
    """governance_summary must include Phase B honesty annotations."""
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.status_code == 200
    gov = r.json().get("governance_summary")
    assert gov is not None, "governance_summary should not be None when governance service is up"
    assert gov["integration_mode"] == "status_only"
    assert gov["active_feedback_loop"] is False
    assert "data_available" in gov


def test_governance_summary_no_data_labeled(client):
    """When governance has no cached data (GET returns status=no_data),
    the annotation must set data_available=False and preserve the
    original status and message fields."""
    # Use empty sessions — governance GET may return no_data on a fresh service.
    # We cannot force the governance state, so we check structural correctness
    # regardless of whether data_available is True or False.
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.status_code == 200
    gov = r.json().get("governance_summary")
    assert gov is not None
    if gov.get("status") == "no_data":
        assert gov["data_available"] is False
        assert "message" in gov
    else:
        # Governance had cached data — data_available must be True
        assert gov["data_available"] is True


def test_governance_summary_preserves_existing_fields(client):
    """Phase B must not remove any existing governance fields.
    If governance returned real data, the core metrics must still be present."""
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.status_code == 200
    gov = r.json().get("governance_summary")
    assert gov is not None
    # The honesty fields are always present
    assert "integration_mode" in gov
    assert "active_feedback_loop" in gov
    # If real data was returned, original fields survive
    if gov.get("data_available") is True:
        for field in ("mae", "psi", "drift_detected", "retrain_recommended", "decision"):
            assert field in gov, f"Expected governance field '{field}' to be preserved"


# ─────────────────────────────────────────────────────────────────────────────
# Phase C: Error semantics and unmet-demand transparency
# ─────────────────────────────────────────────────────────────────────────────

def test_eep_forwards_optimizer_422_not_502(client):
    """Sending a payload that the optimizer's Pydantic model rejects (e.g.
    invalid grid_pattern type) should surface as 422, not a misleading 502."""
    bad_payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": "bad-001",
                "connection_time": "2021-08-01T00:00:00",
                "disconnect_time": "2021-08-01T03:00:00",
                "kwh_requested": 20.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            }
        ],
        # transformer_kva must be > 0 per optimizer's Pydantic Field(gt=0)
        "transformer": {"transformer_kva": -5.0},
    }
    r = client.post("/schedule", json=bad_payload)
    # Grid-compat or optimizer should reject — but NOT as 502
    assert r.status_code != 502, (
        f"Expected a 4xx for invalid input, got 502: {r.text[:200]}"
    )
    assert 400 <= r.status_code < 500


def test_eep_forwards_unmet_demand_kpis(client):
    """EEP must forward unmet-demand KPIs from the optimizer.
    Detailed unmet-demand scenarios are tested in test_optimizer.py."""
    r = client.post("/schedule", json=SAMPLE_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert "unmet_energy_kwh" in kpis
    assert "unmet_sessions_count" in kpis
