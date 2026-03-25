# System Architecture & Flow

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        CLIENT LAYER                             │
│  ┌─────────────────┐          ┌──────────────────────────────┐  │
│  │ Streamlit        │          │ Any HTTP Client              │  │
│  │ Dashboard :8501  │          │ (curl, Postman, frontend)    │  │
│  └────────┬─────────┘          └─────────────┬────────────────┘  │
│           │                                  │                   │
│           └──────────────┬───────────────────┘                   │
│                          ▼                                       │
│              POST /api/v1/simulation/run                         │
└──────────────────────────┬───────────────────────────────────────┘
                           │
┌──────────────────────────▼───────────────────────────────────────┐
│                    GATEWAY SERVICE :8000                          │
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐     │
│  │                  Orchestrator                             │     │
│  │                                                           │     │
│  │  Step 1 ──► Predict departure times (ML Service)          │     │
│  │  Step 2 ──► Build vehicle list (energy needs, slots)      │     │
│  │  Step 3 ──► Generate base load profile (sinusoidal)       │     │
│  │  Step 4 ──► Optimize charging schedule (Optimizer)        │     │
│  │  Step 4b ─► FCFS baseline (if compare_baseline=true)      │     │
│  │  Step 5 ──► Build time series from schedule               │     │
│  │  Step 6 ──► Validate grid constraints (Optimizer)         │     │
│  │                                                           │     │
│  └──────┬───────────────────────────────────┬────────────────┘     │
│         │                                   │                      │
└─────────┼───────────────────────────────────┼──────────────────────┘
          │                                   │
          ▼                                   ▼
┌─────────────────────┐          ┌─────────────────────────┐
│  ML SERVICE :8001   │          │  OPTIMIZER SERVICE :8002 │
│  (internal only)    │          │  (internal only)         │
│                     │          │                          │
│  /predict-departure │          │  /optimize               │
│  /forecast          │          │  /validate-grid          │
│  /health            │          │  /health                 │
│                     │          │                          │
│  XGBoost models     │          │  LP Solver (scipy)       │
│  - Demand forecast  │          │  FCFS Baseline           │
│  - Departure pred.  │          │  Grid Validator          │
└─────────────────────┘          └─────────────────────────┘
```

---

## Detailed Request/Response Flow

### Step 0 — Client Sends Simulation Request

```
POST /api/v1/simulation/run
```

```json
{
  "vehicles": [
    {
      "ev_id": "EV-001",
      "battery_pct": 20,
      "target_pct": 90,
      "battery_capacity_kwh": 60,
      "max_charge_kw": 7.2,
      "arrival_time": "2025-01-15T08:00:00",
      "planned_departure_time": "2025-01-15T17:00:00"
    }
  ],
  "transformer_capacity_kw": 500,
  "building_base_load_kw": 150,
  "simulation_duration_hours": 24,
  "time_step_minutes": 15,
  "compare_baseline": true
}
```

---

### Step 1 — Gateway → ML Service: Departure Prediction

The orchestrator calls the ML Service to predict how long each vehicle will stay.

```
POST http://ml-service:8001/predict-departure
```

**Request:**
```json
{
  "arrival_time": "2025-01-15T08:00:00",
  "site_id": "0002",
  "cluster_id": "0039"
}
```

**Response:**
```json
{
  "model_version": "1.0.0",
  "predicted_stay_duration_min": 487.3,
  "predicted_departure_time": "2025-01-15T16:07:18"
}
```

> The predicted stay duration is used to calculate the departure time slot
> for each vehicle in the optimizer's scheduling window.

---

### Step 2 — Orchestrator: Build Vehicle List

The orchestrator converts each vehicle into optimizer-compatible format:

```
energy_needed = capacity × (target% - current%) / 100
arrival_slot  = (arrival_time - simulation_start) / step_minutes
departure_slot = arrival_slot + (stay_duration / step_minutes)
```

**Output per vehicle:**
```json
{
  "ev_id": "EV-001",
  "energy_needed_kwh": 42.0,
  "max_charge_kw": 7.2,
  "arrival_slot": 32,
  "departure_slot": 64
}
```

---

### Step 3 — Orchestrator: Generate Base Load Profile

A synthetic building load profile is generated for each time slot using a
sinusoidal approximation of commercial building demand:

```
Peak hours   (09:00–17:00)  →  100% of base_load
Shoulder     (07–09, 17–20) →  ramp up/down
Off-peak     (20:00–07:00)  →  40% of base_load
± 5% sinusoidal variation added
```

**Output:** Array of `num_slots` float values representing kW per time slot.

---

### Step 4 — Gateway → Optimizer: LP Scheduling

The orchestrator sends the vehicle list + base load to the optimizer.

```
POST http://optimizer:8002/optimize
```

**Request:**
```json
{
  "vehicles": [ ... ],
  "num_slots": 96,
  "slot_duration_hours": 0.25,
  "transformer_capacity_kw": 500,
  "base_load_per_slot_kw": [60.0, 60.5, ...],
  "strategy": "optimal"
}
```

#### LP Formulation (strategy = "optimal")

```
Decision variables:  x[i,k] = power allocated to vehicle i at slot k (kW)

Maximize:  Σ_i Σ_k  w_i · x[i,k] · Δt
           where w_i = urgency weight (energy_needed / available_slots)

Subject to:
  (1) Per-slot capacity:   Σ_i x[i,k]  ≤  transformer_kw − base_load[k]    ∀ k
  (2) Per-vehicle energy:  Σ_k x[i,k] · Δt  ≤  energy_needed[i]            ∀ i
  (3) Per-vehicle power:   0 ≤ x[i,k] ≤ max_charge_kw[i]                   ∀ i,k
  (4) Presence:            x[i,k] = 0   if k < arrival[i] or k ≥ departure[i]
```

**Response:**
```json
{
  "strategy": "optimal",
  "schedules": [
    {
      "ev_id": "EV-001",
      "power_per_slot_kw": [0, 0, ..., 7.2, 7.2, ..., 0],
      "energy_delivered_kwh": 42.0,
      "energy_needed_kwh": 42.0,
      "satisfaction_pct": 100.0
    }
  ],
  "total_energy_delivered_kwh": 42.0,
  "total_energy_needed_kwh": 42.0,
  "overall_satisfaction_pct": 100.0,
  "peak_load_kw": 157.2,
  "overload_slots": 0,
  "transformer_utilization_per_slot": [12.0, 12.1, ...]
}
```

---

### Step 4b — Gateway → Optimizer: FCFS Baseline (optional)

Same endpoint, but with `"strategy": "fcfs"`. Uses first-come-first-served
with proportional curtailment when capacity is exceeded.

---

### Step 5 — Orchestrator: Build Time Series

For each time slot `k`, the orchestrator computes:

```
ev_load[k]     = Σ  power_per_slot_kw[k]   (sum across all vehicles)
total_load[k]  = ev_load[k] + base_load[k]
utilization[k] = total_load[k] / transformer_capacity × 100
overload[k]    = total_load[k] > transformer_capacity
```

**Output per slot:**
```json
{
  "time_minutes": 480,
  "ev_load_kw": 7.2,
  "building_load_kw": 150.0,
  "total_load_kw": 157.2,
  "transformer_utilization_pct": 31.44,
  "overload": false
}
```

---

### Step 6 — Gateway → Optimizer: Grid Validation

The total load profile is sent for power-flow and thermal checks.

```
POST http://optimizer:8002/validate-grid
```

**Request:**
```json
{
  "total_load_per_slot_kw": [60.0, 60.5, ..., 157.2, ...],
  "transformer_capacity_kw": 500,
  "transformer_kva": 526.3
}
```

#### Checks Performed

| Check                    | Formula                                                  | Threshold       |
|--------------------------|----------------------------------------------------------|-----------------|
| Transformer loading      | `loading% = load / capacity × 100`                      | Warning > 80%   |
| Voltage drop (radial)    | `V_drop = I × (R·pf + X·sin(φ))` on 0.5 km feeder      | Warning < 0.95 p.u. |
| Line thermal limit       | `I = P / (√3 × V_nominal)`                              | Limit = 600 A   |

**Response:**
```json
{
  "feasible": true,
  "max_transformer_loading_pct": 31.06,
  "min_bus_voltage_pu": 0.9883,
  "max_line_current_a": 189.5,
  "overload_minutes": 0,
  "warnings": []
}
```

---

### Final Response to Client

```json
{
  "run_id": "2c0da98c",
  "status": "success",
  "simulation_duration_hours": 24,
  "time_step_minutes": 15,
  "num_vehicles": 1,

  "ai_result": {
    "strategy": "optimal",
    "ev_results": [
      {
        "ev_id": "EV-001",
        "energy_delivered_kwh": 42.0,
        "energy_needed_kwh": 42.0,
        "satisfaction_pct": 100.0
      }
    ],
    "overall_satisfaction_pct": 100.0,
    "peak_load_kw": 157.2,
    "total_energy_delivered_kwh": 42.0,
    "overload_slots": 0,
    "time_series": [ ... ],
    "grid_validation": {
      "feasible": true,
      "max_transformer_loading_pct": 31.06,
      "min_bus_voltage_pu": 0.9883,
      "max_line_current_a": 189.5,
      "overload_minutes": 0,
      "warnings": []
    }
  },

  "baseline_result": {
    "strategy": "fcfs",
    ...
  }
}
```

---

## Network Topology (Docker Compose)

```
              ┌──── exposed ────┐
              │                 │
  Internet ──►│  :8000  Gateway │──── internal bridge ────┬── ML Service  :8001
              │  :8501  Streamlit│                         │
              └─────────────────┘                         └── Optimizer   :8002
```

- Only the **Gateway** exposes ports to the host (8000 for API, 8501 for dashboard)
- **ML Service** and **Optimizer** are reachable only on the internal Docker bridge network
- Services discover each other via Docker Compose DNS names: `ml-service`, `optimizer`

---

## Data Pipeline (Offline Training)

```
data/acn_sessions.csv
        │
        ▼
ml-service/training/prepare_data.py
        │
        ├──► artifacts/demand_train.parquet    (30-min window aggregation)
        ├──► artifacts/demand_val.parquet
        ├──► artifacts/demand_test.parquet
        ├──► artifacts/departure_train.parquet  (per-session features)
        ├──► artifacts/departure_val.parquet
        ├──► artifacts/departure_test.parquet
        └──► artifacts/replay_scenarios.json    (5 representative dates)
                │
                ▼
ml-service/training/train_demand.py       ──► artifacts/demand_model.json
ml-service/training/train_departure.py    ──► artifacts/departure_model.json
ml-service/training/evaluate.py           ──► artifacts/eval_report.json
```

**Chronological split:** 70% train / 10% validation / 20% test  
**Features:** 15 demand features (temporal + lag), 11 departure features (temporal + energy)
