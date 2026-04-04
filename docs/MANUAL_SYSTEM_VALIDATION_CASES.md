# Manual Full-System Validation Cases

Last updated: 2026-04-01

Purpose: Run end-to-end and component-level checks manually through FastAPI docs, using fixed inputs and explicit pass/fail criteria to verify correctness, accuracy, and reliability.

## 1. Endpoints To Use

- EEP (full orchestration): http://localhost:8000/docs
- Forecast IEP: http://localhost:8001/docs
- Optimizer IEP: http://localhost:8002/docs
- Governance IEP: http://localhost:8003/docs
- Grid Compatibility IEP: http://localhost:8004/docs

Run each case in Swagger UI:
1. Open endpoint docs URL
2. Expand endpoint
3. Click Try it out
4. Paste JSON
5. Execute

## 2. Full-System Cases (EEP /schedule)

Endpoint for all cases in this section: POST /schedule on port 8000.

### Case FS-01: Happy Path

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "happy-001",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 20.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 100.0,
    "base_load_kw": 50.0,
    "feeder_length_km": 0.3,
    "cable_type": "B_medium",
    "r1": 0.2,
    "x1": 0.08,
    "r0": 0.4,
    "x0": 0.16,
    "phase_balance_class": "balanced",
    "num_chargers_installed": 20,
    "charger_power_kw": 7.4
  }
}
```

Pass criteria:
- HTTP 200
- `schedules` not empty
- `kpis`, `forecast_summary`, `governance_summary`, `grid_compatibility` all present
- `solver_status` in `optimal` or `greedy_fallback`

### Case FS-02: Transformer Sensitivity (Small Capacity)

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "xfmr-small",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 5.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 20.0,
    "base_load_kw": 0.0,
    "charger_power_kw": 7.4
  }
}
```

### Case FS-03: Transformer Sensitivity (Large Capacity)

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "xfmr-large",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 5.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 200.0,
    "base_load_kw": 0.0,
    "charger_power_kw": 7.4
  }
}
```

Pass criteria for FS-02 and FS-03 pair:
- Both return HTTP 200
- `kpis.transformer_utilization_pct` from FS-02 is greater than FS-03

### Case FS-04: Charger Power Cap Sensitivity

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "rate-cap",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 5.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 100.0,
    "base_load_kw": 50.0,
    "charger_power_kw": 3.3
  }
}
```

Pass criteria:
- HTTP 200
- For each returned slot, `charge_kw <= 3.3`

### Case FS-05: Overload Rejection Safety

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "overload-001",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 10.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 10.0,
    "base_load_kw": 5.0,
    "charger_power_kw": 7.4,
    "num_chargers_installed": 20
  }
}
```

Pass criteria:
- HTTP 422
- Response detail indicates incompatible or overloaded grid condition

### Case FS-06: Empty Sessions Stability

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [],
  "grid_pattern": "morning",
  "transformer": {
    "transformer_kva": 100.0,
    "base_load_kw": 50.0,
    "charger_power_kw": 7.4
  }
}
```

Pass criteria:
- HTTP 200
- `schedules` is empty
- `kpis.total_kwh_scheduled == 0`

### Case FS-07: Repeatability Check

Use FS-01 input 5 times.

Pass criteria:
- No request returns 5xx
- Schema remains consistent every run
- `request_id` changes per call
- KPIs are stable (small numeric jitter allowed)

## 3. Component Accuracy Cases

### Case C-01: Forecast Horizon Shape

Endpoint: POST /forecast/horizon on port 8001

Input:
```json
{
  "current_time": "2021-08-01T00:00:00",
  "horizon_hours": 3
}
```

Pass criteria:
- HTTP 200
- `predictions` is present and non-empty
- `model_version` is present
- CI bounds are structurally valid (`lower_ci <= upper_ci`)

### Case C-02: Optimizer KPI Formula Sanity

Endpoint: POST /optimize on port 8002

Input:
```json
{
  "date": "2021-08-01",
  "sessions": [
    {
      "session_id": "opt-001",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 10.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ],
  "grid_pattern": "morning",
  "transformer_kva": 100.0,
  "base_load_kw": 50.0,
  "charger_power_kw": 7.4
}
```

Pass criteria:
- HTTP 200
- `kpis.avg_available_headroom_kw >= 0`
- `kpis.transformer_utilization_pct` approximately equals `kpis.transformer_peak_kw / transformer_kva * 100`
- `kpis.baseline_comparison` exists

### Case C-03: Grid Compatibility Physics (Compatible)

Endpoint: POST /predict on port 8004

Input:
```json
{
  "transformer_kva": 100.0,
  "base_load_kw": 50.0,
  "feeder_length_km": 0.3,
  "cable_type": "B_medium",
  "r1": 0.2,
  "x1": 0.08,
  "r0": 0.4,
  "x0": 0.16,
  "phase_balance_class": "balanced",
  "num_chargers_installed": 20,
  "charger_power_kw": 7.4,
  "num_chargers_active": 3
}
```

Pass criteria:
- HTTP 200
- `nominal_load_ratio` approximately `(3 * 7.4 + 50) / 100 = 0.722`
- `nominal_headroom_kw` approximately `100 - (3 * 7.4 + 50) = 27.8`

### Case C-04: Grid Compatibility Physics (Not Compatible)

Endpoint: POST /predict on port 8004

Input:
```json
{
  "transformer_kva": 100.0,
  "base_load_kw": 50.0,
  "feeder_length_km": 0.3,
  "cable_type": "B_medium",
  "r1": 0.2,
  "x1": 0.08,
  "r0": 0.4,
  "x0": 0.16,
  "phase_balance_class": "balanced",
  "num_chargers_installed": 20,
  "charger_power_kw": 7.4,
  "num_chargers_active": 10
}
```

Pass criteria:
- HTTP 200
- `compatibility_class == "not_compatible"`
- `nominal_load_ratio` approximately `(10 * 7.4 + 50) / 100 = 1.24`
- `nominal_headroom_kw` approximately `100 - (10 * 7.4 + 50) = -24`

### Case C-05: Governance Decision Output

Endpoint: POST /governance/status on port 8003

Input:
```json
{
  "records": [
    {
      "slot_start": "2021-08-01T00:00:00",
      "predicted_kw": 5.0,
      "actual_kw": 5.2
    },
    {
      "slot_start": "2021-08-01T00:15:00",
      "predicted_kw": 3.0,
      "actual_kw": 3.1
    },
    {
      "slot_start": "2021-08-01T00:30:00",
      "predicted_kw": 2.0,
      "actual_kw": 2.8
    }
  ]
}
```

Pass criteria:
- HTTP 200
- Returns: `mae`, `psi`, `drift_detected`, `retrain_recommended`, `decision`
- Decision text is consistent with computed metrics direction

## 4. Reliability Validation

### Case R-01: Health Endpoints

Check:
- GET /health on ports 8000, 8001, 8002, 8003, 8004

Pass criteria:
- All return HTTP 200 with `status: ok`

### Case R-02: Metrics Exposure

Check:
- GET /metrics on ports 8000, 8001, 8002, 8003, 8004

Pass criteria:
- All return HTTP 200 and non-empty Prometheus text payload

### Case R-03: Automated Test Suite Baseline

Run:
```bash
python -m pytest tests/ --ignore=tests/test_integration.py -q
```

Pass criteria:
- Current expected result: `78 passed`

## 5. Final Acceptance Checklist

Mark PASS only if all are true:

- [ ] FS-01 passed
- [ ] FS-02 and FS-03 sensitivity relation passed
- [ ] FS-04 charger cap respected in all slots
- [ ] FS-05 overload safely rejected
- [ ] FS-06 empty sessions handled correctly
- [ ] FS-07 repeatability stable over 5 runs
- [ ] C-01 forecast output shape valid
- [ ] C-02 optimizer KPI math sanity valid
- [ ] C-03 and C-04 grid physics consistency valid
- [ ] C-05 governance decision fields valid
- [ ] R-01 all health checks green
- [ ] R-02 all metrics endpoints available
- [ ] R-03 test suite passes at expected baseline

If every checkbox is PASS, the system is functioning correctly and reliably for current scope.
