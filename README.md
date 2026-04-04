# EV Charging Orchestration Platform — Project 503N

An AI-powered EV charging orchestration platform designed for constrained grid environments (e.g. Lebanon's EDL load-shedding scenario). It combines ML-based demand forecasting, linear-program optimization, grid compatibility assessment, and model-governance monitoring into five independent FastAPI microservices.

---

## Architecture

| Service | Port | Responsibility |
|---|---|---|
| **EEP** (Orchestrator) | 8000 | Accepts schedule requests, fans out to all IEPs in parallel, returns a merged response |
| **IEP-Forecast** | 8001 | GradientBoosting demand forecast (mean + 90% CI) over 15-min slots |
| **IEP-Optimizer** | 8002 | CVXPY LP scheduler (≤ 20 EVs; greedy fallback for larger batches) respecting transformer headroom, EDL grid availability, and SCE TOU tariffs |
| **IEP-Governance** | 8003 | Rolling MAE + PSI drift detection; triggers retraining recommendation when thresholds are breached |
| **IEP-Grid-Compatibility** | 8004 | Two-stage ML pipeline (classifier + regressor) for grid overload detection and charger throttling |

Supporting infrastructure (via Docker Compose):

- **MLflow** (port 5000) — experiment tracking for all services
- **Prometheus** (port 9090) — scrapes `/metrics` from every service
- **Grafana** (port 3000) — dashboards over Prometheus data

---

## Quick-start

### 1 — Run everything with Docker Compose

```bash
docker compose up --build
```

The EEP orchestrator is then reachable at `http://localhost:8000`.

### 2 — Run services locally (development)

```bash
# Install dependencies
pip install fastapi uvicorn httpx mlflow-skinny scikit-learn cvxpy \
            pandas numpy joblib prometheus-client slowapi

# Pre-process data once
python data/preprocess.py

# Start each service in a separate terminal
cd iep-forecast          && uvicorn main:app --port 8001 --reload
cd iep-optimizer         && uvicorn main:app --port 8002 --reload
cd iep-governance        && uvicorn main:app --port 8003 --reload
cd iep-grid-compatibility && uvicorn main:app --port 8004 --reload
cd eep                   && uvicorn main:app --port 8000 --reload
```

### 3 — Run tests

```bash
# Service integration tests (requires containers running)
python -m pytest tests/ -v --ignore=tests/test_integration.py

# Full E2E integration tests
python -m pytest tests/test_integration.py -v
```

---

## Key API Endpoints

### `POST /schedule` (EEP — port 8000)

Schedule EV charging for a given day.

```json
{
  "date": "2021-07-15",
  "grid_pattern": "split",
  "sessions": [
    {
      "session_id": "ev-001",
      "connection_time": "2021-07-15T08:00:00",
      "disconnect_time": "2021-07-15T17:00:00",
      "kwh_requested": 30.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }
  ]
}
```

`grid_pattern` must be one of `"split"` | `"morning"` | `"random"`.

**Optional fields:**
- `transformer` — override transformer config (kva, base_load_kw, cable_type, etc.)
- `forecast_reservation` — 96-element array of uncertainty reservation kW per slot

> **Scale note:** The optimizer uses CVXPY's LP solver for ≤ 20 EVs (exact optimal). For larger batches it falls back to a cost-ordered greedy scheduler. The `solver_status` field indicates which path was taken (`"optimal"` or `"greedy_fallback"`).

### `POST /forecast` (IEP-Forecast — port 8001)
Returns demand predictions with confidence intervals for given feature slots.

### `POST /optimize` (IEP-Optimizer — port 8002)
Runs cost-minimized LP optimization with FCFS baseline comparison.

### `POST /predict` (IEP-Grid-Compatibility — port 8004)
Assesses grid compatibility (compatible / conditional / not_compatible) with recommended charger limits.

### `POST /governance/status` (IEP-Governance — port 8003)
Returns MAE, PSI, drift detection, and retrain recommendations.

Full OpenAPI docs are auto-generated at `http://localhost:<port>/docs`.

---

## Data

- **EV sessions**: ACN Dataset (2,524 real charging sessions from Caltech/JPL)
- **Tariff**: SCE TOU-EV-9 ($0.11 – $0.53 / kWh)
- **Building load**: DOE Commercial Reference Building profile
- **Grid availability**: Published Lebanese EDL load-shedding schedule (2 – 10 hrs outage / day)
- **Grid simulation**: OpenDSS-derived transformer loading dataset for grid compatibility training

Run `python data/preprocess.py` to regenerate processed Parquet files under `data/processed/`.

---

## Key Features

- **Cost optimization**: LP solver minimizes charging costs using TOU tariffs
- **Forecast uncertainty reservation**: Reserves transformer headroom based on prediction confidence intervals
- **Grid compatibility enforcement**: Rejects or throttles charging when grid is overloaded
- **Power throttling**: Automatically reduces per-session charge rates on conditional grids
- **Fairness under scarcity**: Greedy fallback ensures no EV is starved when >20 concurrent sessions
- **FCFS baseline comparison**: Every optimization includes cost/peak comparison vs naive first-come-first-served
- **Unmet demand transparency**: Reports exactly how much energy couldn't be delivered
- **Model governance**: PSI drift detection with gated retraining and promotion decisions

---

## Monitoring

Prometheus metrics are exposed at `/metrics` on every service.
Grafana dashboards are provisioned automatically from `monitoring/grafana/provisioning/`.

| Metric | Description |
|---|---|
| `ev_forecast_predicted_kw_avg` | Average predicted demand |
| `ev_optimizer_solves_total` | Solver calls by status (optimal/greedy) |
| `ev_optimizer_transformer_peak_kw` | Peak transformer load |
| `ev_governance_mae_kw` | Rolling forecast MAE |
| `ev_governance_psi` | Population Stability Index (drift) |
| `ev_governance_drift_detected` | 1 when drift detected |

---

## Kubernetes

K8s manifests are in `k8s/` for deployment to a cluster:

```bash
kubectl apply -f k8s/namespace.yaml
kubectl apply -f k8s/
```

---

## Project Structure

```
├── docker-compose.yml          # Full stack orchestration
├── eep/                        # EEP orchestrator service
├── iep-forecast/               # Demand forecast service + models
├── iep-optimizer/              # LP optimizer + FCFS baseline
├── iep-governance/             # Model monitoring + retraining
├── iep-grid-compatibility/     # Grid overload assessment + models
├── data/                       # Pipeline code + raw datasets
├── tests/                      # Pytest integration + E2E tests
├── scripts/                    # Standalone validation scripts
├── k8s/                        # Kubernetes deployment manifests
├── monitoring/                 # Prometheus + Grafana configs
└── docs/                       # Project documentation
```

---

## Test Suite

| File | Tests | Scope |
|---|---|---|
| test_eep.py | 26 | EEP orchestration, scheduling, physics, error handling |
| test_optimizer.py | 35 | Optimization, cost comparison, fairness, edge cases |
| test_forecast.py | 9 | Demand prediction, CI bounds, endpoints |
| test_governance.py | 9 | Drift detection, retraining, promotion gates |
| test_grid_compatibility.py | 15 | Grid assessment, semantic correctness, validation |
| test_integration.py | 8 | Cross-service E2E flows |
| **Total** | **102** | |

### Validation Scripts (in `scripts/`)

| Script | Purpose |
|---|---|
| grid_compat_accuracy.py | Offline model accuracy evaluation |
| grid_compat_realism_eval.py | OOD robustness evaluation |
| grid_compat_sweep.py | Parameter space coverage sweep |
| validate_grid_compat.py | Pre-deployment physics credibility checks |
