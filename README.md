# EV Charging Optimization and Grid Compatibility System

AI-assisted EV charging optimization that maximizes energy delivery while respecting grid constraints.

## Architecture

```
┌────────────────────────────────────┐
│  Container 1 (External)           │
│  API Gateway + Streamlit Dashboard │←── Public traffic (:8000, :8501)
└──────────┬──────────────┬──────────┘
           │ internal net │
┌──────────▼──────┐  ┌───▼──────────┐
│  Container 2    │  │  Container 3  │
│  ML Inference   │  │  Optimizer +  │
│  (:8001)        │  │  Grid Sim     │
│                 │  │  (:8002)      │
└─────────────────┘  └──────────────┘
```

- **Container 1** — API Gateway (FastAPI) + Dashboard (Streamlit) — only public endpoint
- **Container 2** — ML Service: demand forecasting + departure prediction (XGBoost on ACN-Data)
- **Container 3** — LP Optimizer + Grid Validation (simplified power flow, OpenDSS-ready)

## Quick Start (Local)

### 1. Train ML models first

```bash
cd ml-service
pip install -r requirements.txt
python -m training.prepare_data --data-path ../data/acn_sessions.csv --output-dir artifacts/
python -m training.train_demand --artifacts-dir artifacts/
python -m training.train_departure --artifacts-dir artifacts/
python -m training.evaluate --artifacts-dir artifacts/
```

### 2. Run with Docker Compose

```bash
docker-compose up -d --build
```

- API Gateway: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Dashboard: http://localhost:8501

### 3. Or run services individually

```bash
# Terminal 1: ML Service
cd ml-service && uvicorn app.main:app --port 8001

# Terminal 2: Optimizer
cd optimizer && uvicorn app.main:app --port 8002

# Terminal 3: Gateway
cd gateway && ML_SERVICE_URL=http://localhost:8001 OPTIMIZER_SERVICE_URL=http://localhost:8002 uvicorn app.main:app --port 8000

# Terminal 4: Dashboard
cd gateway && streamlit run dashboard/app.py
```

## Deploy to AWS

```bash
# Prerequisites: AWS CLI configured, EC2 key pair ready
chmod +x scripts/deploy_aws.sh
./scripts/deploy_aws.sh
```

See [scripts/deploy_aws.sh](scripts/deploy_aws.sh) for details.

## Project Structure

```
├── data/                    ACN charging sessions
│   └── acn_sessions.csv
├── ml-service/              Container 2 — ML Inference
│   ├── training/            Data pipeline + model training
│   │   ├── prepare_data.py  Parse ACN data → training datasets
│   │   ├── train_demand.py  Model 1: arrival + energy forecast
│   │   ├── train_departure.py  Model 2: stay duration prediction
│   │   └── evaluate.py      Evaluation against baselines
│   ├── app/                 FastAPI service
│   │   ├── main.py          Endpoints: /forecast, /predict-departure
│   │   └── models/          Inference wrappers
│   └── artifacts/           Trained models + metrics (generated)
├── optimizer/               Container 3 — Optimizer + Grid
│   └── app/
│       ├── main.py          Endpoints: /optimize, /validate-grid
│       ├── optimizer/
│       │   ├── lp_scheduler.py   LP-based optimal scheduler
│       │   └── fcfs_baseline.py  FCFS baseline (unmanaged charging)
│       └── grid/
│           └── validator.py      Simplified power flow (OpenDSS-ready)
├── gateway/                 Container 1 — API Gateway + Dashboard
│   ├── app/
│   │   ├── main.py          Public API
│   │   ├── routers/         Simulation endpoints
│   │   └── services/        Orchestrator (ML → Optimize → Validate)
│   └── dashboard/
│       └── app.py           Streamlit dashboard
├── docker-compose.yml       3-container deployment
├── scripts/
│   └── deploy_aws.sh        AWS EC2 deployment script
└── SYSTEM_DESIGN.md         Full system design document
```

## ML Models

### Model 1 — Demand Forecasting
Predicts EV arrival count and total energy demand per 30-min window.
Trained on ACN-Data with walk-forward cross-validation.

### Model 2 — Departure Prediction
Predicts how long each vehicle will stay based on arrival context.
Enables priority-aware scheduling (urgent vehicles get more power).

## Grid Validation

Currently uses a simplified radial feeder power flow model. Ready to integrate
OpenDSS when the `.dss` circuit file from your partner is available — just
replace the `_simplified_power_flow` function in `optimizer/app/grid/validator.py`.
