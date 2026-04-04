"""
Integration tests for IEP-Optimizer — requires containers to be running.
Run with: docker-compose up -d && python -m pytest tests/test_optimizer.py -v
"""
import pytest
import httpx

OPTIMIZER_URL = "http://localhost:8002"

VALID_SESSION = {
    "session_id": "test-001",
    "connection_time": "2021-08-01T00:00:00",
    "disconnect_time": "2021-08-01T03:00:00",
    "kwh_requested": 20.0,
    "kwh_delivered": 0.0,
    "max_charge_rate_kw": 7.4,
    "has_user_inputs": True,
}

VALID_PAYLOAD = {
    "date": "2021-08-01",
    "sessions": [VALID_SESSION],
    "grid_pattern": "morning",
}

# Controlled deterministic scenario for tariff-aware comparison:
# - 2021-03-15 is a Monday (non-summer weekday)
# - With pattern="split", modeled grid windows include both early-morning
#   availability and a later daytime window
# - Tariff is higher overnight than during 08:00-15:59 on non-summer weekdays
# - FCFS charges immediately; the optimizer can defer into the cheaper window
CONTROLLED_COST_SESSION = {
    "session_id": "cost-shift-001",
    "connection_time": "2021-03-15T00:00:00",
    "disconnect_time": "2021-03-15T12:00:00",
    "kwh_requested": 10.0,
    "kwh_delivered": 0.0,
    "max_charge_rate_kw": 7.4,
    "has_user_inputs": True,
}

CONTROLLED_COST_PAYLOAD = {
    "date": "2021-03-15",
    "sessions": [CONTROLLED_COST_SESSION],
    "grid_pattern": "split",
}


@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=OPTIMIZER_URL, timeout=30.0) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_optimize_valid(client):
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert "schedules" in data
    assert "kpis" in data
    assert "solver_status" in data


def test_optimize_solver_status_valid(client):
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.json()["solver_status"] in ("optimal", "greedy_fallback", "infeasible")


def test_optimize_session_fully_charged(client):
    """Session connecting during grid-available window should be fully charged."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    data = r.json()
    assert data["kpis"]["total_kwh_scheduled"] == pytest.approx(20.0, abs=1.0)
    assert data["kpis"]["sessions_fully_charged"] == 1


def test_optimize_charge_rate_within_limit(client):
    """No slot should exceed max_charge_rate_kw."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    for schedule in r.json()["schedules"]:
        for slot in schedule["slots"]:
            assert slot["charge_kw"] <= VALID_SESSION["max_charge_rate_kw"] + 0.01


def test_optimize_transformer_peak_within_headroom(client):
    """Transformer peak must not exceed 50 kW EV headroom."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.json()["kpis"]["transformer_peak_kw"] <= 50.0


def test_optimize_kpis_non_negative(client):
    r = client.post("/optimize", json=VALID_PAYLOAD)
    for key, val in r.json()["kpis"].items():
        if isinstance(val, (int, float)):
            assert val >= 0, f"KPI {key} is negative: {val}"


def test_optimize_empty_sessions(client):
    payload = {**VALID_PAYLOAD, "sessions": []}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    assert r.json()["schedules"] == []


def test_optimize_missing_date(client):
    r = client.post("/optimize", json={"sessions": []})
    assert r.status_code == 422


def test_optimize_invalid_grid_pattern(client):
    payload = {**VALID_PAYLOAD, "grid_pattern": "invalid"}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 422


def test_optimize_invalid_date(client):
    payload = {**VALID_PAYLOAD, "date": "not-a-date"}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 422


def test_optimize_invalid_time_window(client):
    payload = {
        **VALID_PAYLOAD,
        "sessions": [
            {
                **VALID_SESSION,
                "connection_time": "2021-08-01T03:00:00",
                "disconnect_time": "2021-08-01T00:00:00",
            }
        ],
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 422


def test_optimize_solve_time_present(client):
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert "solve_time_s" in r.json()
    assert r.json()["solve_time_s"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Baseline comparison tests
# ─────────────────────────────────────────────────────────────────────────────

def test_optimize_baseline_comparison_keys(client):
    """baseline_comparison must be present in kpis with all required keys."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    bc = r.json()["kpis"].get("baseline_comparison")
    assert bc is not None, "kpis.baseline_comparison missing from /optimize response"
    for key in (
        "fcfs_total_cost_usd",
        "fcfs_transformer_peak_kw",
        "fcfs_sessions_fully_charged",
        "cost_delta_usd",
        "peak_reduction_kw",
        "completion_delta",
    ):
        assert key in bc, f"baseline_comparison missing key: {key}"


def test_optimize_is_cheaper_in_controlled_tariff_shift_scenario(client):
    """
    Use a deterministic scenario where the expected relationship is defensible.

    In this case the EV is connected across both:
      - early available slots with a higher non-summer overnight tariff, and
      - later available slots with a cheaper daytime tariff.

    FCFS charges immediately, while the optimizer is explicitly cost-aware and
    can shift into the cheaper window. This is a valid place to assert that the
    optimizer beats FCFS on cost.
    """
    optimize_resp = client.post("/optimize", json=CONTROLLED_COST_PAYLOAD)
    baseline_resp = client.post("/baseline", json=CONTROLLED_COST_PAYLOAD)

    assert optimize_resp.status_code == 200
    assert baseline_resp.status_code == 200

    optimize_data = optimize_resp.json()
    baseline_data = baseline_resp.json()
    bc = optimize_data["kpis"]["baseline_comparison"]

    # Cross-check the comparison block against the standalone baseline endpoint.
    assert bc["fcfs_total_cost_usd"] == pytest.approx(
        baseline_data["kpis"]["total_cost_usd"], abs=1e-4
    )
    assert bc["fcfs_transformer_peak_kw"] == pytest.approx(
        baseline_data["kpis"]["transformer_peak_kw"], abs=1e-4
    )
    assert bc["fcfs_sessions_fully_charged"] == baseline_data["kpis"]["sessions_fully_charged"]

    # Both methods should fully charge this single-session request.
    assert optimize_data["kpis"]["sessions_fully_charged"] == 1
    assert baseline_data["kpis"]["sessions_fully_charged"] == 1

    # This assertion is intentionally limited to a scenario where the tariff
    # structure makes the cheaper-vs-FCFS relationship deterministic.
    assert optimize_data["kpis"]["total_cost_usd"] < baseline_data["kpis"]["total_cost_usd"], (
        f"Expected optimizer cost ({optimize_data['kpis']['total_cost_usd']}) to be lower than "
        f"FCFS cost ({baseline_data['kpis']['total_cost_usd']}) in the controlled tariff-shift scenario"
    )


def test_baseline_endpoint(client):
    """Standalone /baseline endpoint returns valid FCFS KPIs."""
    r = client.post("/baseline", json=VALID_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert "solve_time_s" in data
    assert data["kpis"]["total_cost_usd"] >= 0
    assert data["kpis"]["transformer_peak_kw"] >= 0


# ─────────────────────────────────────────────────────────────────────────────
# Forecast uncertainty reservation tests (Fix #6)
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_reservation_kpis_absent_by_default(client):
    """Without forecast_reservation, headroom KPIs show not applied."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["forecast_headroom_applied"] is False
    assert kpis["forecast_reserved_kwh"] == 0.0
    assert kpis["avg_reservation_kw"] == 0.0


def test_forecast_reservation_reduces_headroom(client):
    """
    A/B comparison: same sessions, with vs without uncertainty reservation.
    The reservation tightens headroom → optimizer must spread load differently.
    """
    # A: no reservation (baseline behavior)
    r_a = client.post("/optimize", json=VALID_PAYLOAD)
    assert r_a.status_code == 200
    kpis_a = r_a.json()["kpis"]

    # B: with a non-trivial reservation (5 kW uncertainty buffer in all 96 slots)
    payload_b = {
        **VALID_PAYLOAD,
        "forecast_reservation": [5.0] * 96,
    }
    r_b = client.post("/optimize", json=payload_b)
    assert r_b.status_code == 200
    kpis_b = r_b.json()["kpis"]

    # Reservation KPIs must be active
    assert kpis_b["forecast_headroom_applied"] is True
    assert kpis_b["forecast_reserved_kwh"] > 0
    assert kpis_b["avg_reservation_kw"] == pytest.approx(5.0, abs=0.01)

    # Both should still fully charge the session (enough headroom remains)
    assert kpis_b["sessions_fully_charged"] == kpis_a["sessions_fully_charged"]

    # Peak should be at most equal (tighter headroom → same or lower peak)
    assert kpis_b["transformer_peak_kw"] <= kpis_a["transformer_peak_kw"] + 0.01


# ─────────────────────────────────────────────────────────────────────────────
# Fix #7: Scheduling quality — urgency, fairness, new KPIs
# ─────────────────────────────────────────────────────────────────────────────

def test_new_kpis_present(client):
    """Fix #7: min_session_kwh, fairness_index, avg_laxity must be in kpis."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    for key in ("min_session_kwh", "fairness_index", "avg_laxity", "avg_available_headroom_kw"):
        assert key in kpis, f"KPI {key} missing from response"
    assert 0.0 <= kpis["fairness_index"] <= 1.0
    assert kpis["avg_available_headroom_kw"] >= 0.0


def test_urgency_tiebreak(client):
    """Fix #7: Tight-laxity EV charges in earlier slots than loose-laxity EV
    when all slots have the same cost (morning pattern, overnight tariff)."""
    tight_session = {
        "session_id": "tight",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T01:00:00",  # 4 slots
        "kwh_requested": 1.85,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    loose_session = {
        "session_id": "loose",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",  # 12 slots
        "kwh_requested": 1.85,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    payload = {
        "date": "2021-08-01",
        "sessions": [tight_session, loose_session],
        "grid_pattern": "morning",
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()

    # Compute average slot index for each EV
    for sched in data["schedules"]:
        slots = [s["slot_index"] for s in sched["slots"]]
        avg_slot = sum(slots) / len(slots) if slots else 0
        if sched["session_id"] == "tight":
            tight_avg = avg_slot
        else:
            loose_avg = avg_slot

    # Tight-laxity EV should use earlier slots on average
    assert tight_avg <= loose_avg, (
        f"Expected tight EV avg slot ({tight_avg}) <= loose EV avg slot ({loose_avg})"
    )


def test_greedy_fairness_no_starvation(client):
    """Fix #7: Under scarcity with >20 EVs (greedy fallback), no EV gets zero energy."""
    sessions_25 = []
    for i in range(25):
        sessions_25.append({
            "session_id": f"ev-{i+1:02d}",
            "connection_time": "2021-08-01T00:00:00",
            "disconnect_time": "2021-08-01T03:00:00",
            "kwh_requested": 15.0,
            "kwh_delivered": 0.0,
            "max_charge_rate_kw": 7.4,
        })
    payload = {
        "date": "2021-08-01",
        "sessions": sessions_25,
        "grid_pattern": "morning",
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()

    # Should hit greedy fallback (n>20)
    assert data["solver_status"] == "greedy_fallback"

    # No EV should get zero energy
    assert data["kpis"]["min_session_kwh"] > 0, "Some EV got zero energy — starvation detected"

    # Fairness should be high
    assert data["kpis"]["fairness_index"] >= 0.95, (
        f"Fairness index {data['kpis']['fairness_index']} < 0.95"
    )


# ── Request-driven physics tests ────────────────────────────────────────────


def test_backward_compat_old_payload_still_works(client):
    """Old payloads without new fields must succeed (backward compat)."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    data = r.json()
    assert "kpis" in data
    assert data["kpis"]["transformer_utilization_pct"] >= 0


def test_transformer_kva_changes_utilization_pct(client):
    """Higher transformer_kva → lower utilization_pct for the same EV load."""
    session = {
        "session_id": "xfmr-test",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 5.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    small_xfmr = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "transformer_kva": 50.0,
        "base_load_kw": 0.0,
    }
    large_xfmr = {**small_xfmr, "transformer_kva": 200.0}

    r_small = client.post("/optimize", json=small_xfmr)
    r_large = client.post("/optimize", json=large_xfmr)
    assert r_small.status_code == 200
    assert r_large.status_code == 200

    util_small = r_small.json()["kpis"]["transformer_utilization_pct"]
    util_large = r_large.json()["kpis"]["transformer_utilization_pct"]

    assert util_small > util_large, (
        f"Expected smaller transformer to show higher utilization pct "
        f"({util_small} vs {util_large})"
    )


def test_base_load_kw_reduces_available_headroom_and_energy(client):
    """Higher base_load_kw leaves less headroom; a constrained session delivers less energy."""
    # Small transformer so building load meaningfully bites into headroom.
    # transformer_kva=5, base_load=0 → headroom ≈ 5 kW; 15 kWh fully achievable.
    # transformer_kva=5, base_load=4 → headroom ≈ 3.6 kW overnight; 15 kWh not achievable.
    session = {
        "session_id": "base-load-test",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 15.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    low_base = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "transformer_kva": 5.0,
        "base_load_kw": 0.0,
        "charger_power_kw": 7.4,
    }
    high_base = {**low_base, "base_load_kw": 4.0}

    r_low = client.post("/optimize", json=low_base)
    r_high = client.post("/optimize", json=high_base)
    assert r_low.status_code == 200
    assert r_high.status_code == 200

    kwh_low  = r_low.json()["kpis"]["total_kwh_scheduled"]
    kwh_high = r_high.json()["kpis"]["total_kwh_scheduled"]

    assert kwh_high < kwh_low, (
        f"Expected high base_load to deliver less energy ({kwh_high} >= {kwh_low})"
    )


def test_charger_power_kw_caps_per_slot_charge_rate(client):
    """charger_power_kw=3.3 must prevent any slot from exceeding 3.3 kW."""
    session = {
        "session_id": "rate-cap-test",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 5.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,   # session requests 7.4 kW
    }
    payload = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "charger_power_kw": 3.3,     # site cap overrides session rate
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["schedules"], "Expected at least one scheduled slot"

    for slot in data["schedules"][0]["slots"]:
        assert slot["charge_kw"] <= 3.3 + 1e-4, (
            f"Slot {slot['slot_index']} charge_kw {slot['charge_kw']} exceeds charger_power_kw=3.3"
        )


# ── Edge-case / stability tests ─────────────────────────────────────────────


def test_edge_very_small_transformer_kva(client):
    """transformer_kva=2.0 → tiny headroom, system responds 200, energy ≤ 0.5 kWh."""
    session = {
        "session_id": "edge-tiny-xfmr",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 20.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    payload = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "transformer_kva": 2.0,
        "base_load_kw": 0.0,
        "charger_power_kw": 7.4,
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()
    # With a 2 kW transformer and a 3-hour morning window, at most 2 kW × 3 h = 6 kWh
    assert data["kpis"]["total_kwh_scheduled"] <= 6.5
    assert data["kpis"]["transformer_peak_kw"] <= 2.0 + 1e-3


def test_edge_base_load_exceeds_transformer_capacity(client):
    """base_load_kw > transformer_kva → zero headroom → no EV energy delivered, no crash."""
    session = {
        "session_id": "edge-no-headroom",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 10.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    payload = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "transformer_kva": 5.0,
        "base_load_kw": 200.0,    # building alone saturates (and exceeds) transformer
        "charger_power_kw": 7.4,
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()
    # headroom is clipped to 0 everywhere → no charging possible
    assert data["kpis"]["total_kwh_scheduled"] == pytest.approx(0.0, abs=1e-3)
    assert data["kpis"]["transformer_peak_kw"] == pytest.approx(0.0, abs=1e-3)


def test_edge_very_low_charger_power_kw(client):
    """charger_power_kw=0.5 → no slot ever exceeds 0.5 kW."""
    session = {
        "session_id": "edge-low-rate",
        "connection_time": "2021-08-01T00:00:00",
        "disconnect_time": "2021-08-01T03:00:00",
        "kwh_requested": 5.0,
        "kwh_delivered": 0.0,
        "max_charge_rate_kw": 7.4,
    }
    payload = {
        "date": "2021-08-01",
        "sessions": [session],
        "grid_pattern": "morning",
        "charger_power_kw": 0.5,
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    data = r.json()
    for slot in data["schedules"][0]["slots"]:
        assert slot["charge_kw"] <= 0.5 + 1e-4, (
            f"Slot {slot['slot_index']} charge_kw {slot['charge_kw']} exceeds charger_power_kw=0.5"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Phase A: Forecast observability KPIs
# ─────────────────────────────────────────────────────────────────────────────

def test_forecast_observability_kpis_zero_without_reservation(client):
    """New forecast observability KPIs must be zero when no reservation is supplied."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["forecast_reserved_slots"] == 0
    assert kpis["forecast_binding_slots"] == 0
    assert kpis["forecast_headroom_reduction_pct"] == 0.0


def test_forecast_observability_kpis_positive_with_reservation(client):
    """New forecast observability KPIs must become positive when a reservation is applied."""
    payload = {
        **VALID_PAYLOAD,
        "forecast_reservation": [5.0] * 96,
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["forecast_reserved_slots"] == 96
    assert kpis["forecast_binding_slots"] > 0, "Expected at least one binding slot"
    assert kpis["forecast_headroom_reduction_pct"] > 0.0


def test_forecast_observability_kpis_in_empty_session_response(client):
    """Empty-session response must include the new forecast observability KPI fields."""
    payload = {**VALID_PAYLOAD, "sessions": []}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    for key in ("forecast_reserved_slots", "forecast_binding_slots", "forecast_headroom_reduction_pct"):
        assert key in kpis, f"KPI {key} missing from empty-session response"
    assert kpis["forecast_reserved_slots"] == 0
    assert kpis["forecast_binding_slots"] == 0
    assert kpis["forecast_headroom_reduction_pct"] == 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Phase C: Unmet-demand transparency
# ─────────────────────────────────────────────────────────────────────────────

def test_unmet_demand_kpis_present(client):
    """Optimizer response must include unmet-demand KPI fields."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert "unmet_energy_kwh" in kpis
    assert "unmet_sessions_count" in kpis


def test_unmet_demand_zero_when_fully_charged(client):
    """When all sessions are fully charged, unmet metrics must be zero."""
    r = client.post("/optimize", json=VALID_PAYLOAD)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    if kpis["sessions_fully_charged"] == len(VALID_PAYLOAD["sessions"]):
        assert kpis["unmet_energy_kwh"] == 0.0
        assert kpis["unmet_sessions_count"] == 0


def test_unmet_demand_empty_sessions(client):
    """Empty sessions → zero unmet demand."""
    payload = {**VALID_PAYLOAD, "sessions": []}
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["unmet_energy_kwh"] == 0.0
    assert kpis["unmet_sessions_count"] == 0


def test_unmet_demand_positive_for_constrained_scenario(client):
    """A session requiring 50 kWh in 30 min at 7.4 kW max is physically
    impossible — unmet demand must be positive."""
    payload = {
        "date": "2021-08-01",
        "sessions": [
            {
                "session_id": "unmet-001",
                "connection_time": "2021-08-01T00:00:00",
                "disconnect_time": "2021-08-01T00:30:00",
                "kwh_requested": 50.0,
                "kwh_delivered": 0.0,
                "max_charge_rate_kw": 7.4,
                "has_user_inputs": True,
            }
        ],
        "grid_pattern": "morning",
    }
    r = client.post("/optimize", json=payload)
    assert r.status_code == 200
    kpis = r.json()["kpis"]
    assert kpis["unmet_energy_kwh"] > 0, (
        f"Expected positive unmet_energy_kwh, got {kpis['unmet_energy_kwh']}"
    )
    assert kpis["unmet_sessions_count"] == 1
