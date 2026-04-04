# AI-Powered EV Charging Optimization Platform
## EECE 503N — Master Project Document

> 2026-04-02 strategic update: see `docs/MAX_IMPACT_A_PLUS_BLUEPRINT_2026-04-02.md` for the full latest maximum-impact roadmap, rubric closure sequence, and external benchmark-driven upgrade plan.

**Repository:** aliwaked-ai/AI-Project-503N
**Branch:** feature/monitoring-and-metrics
**Last verified:** 2026-03-29

---

# 1. Problem Statement

Unmanaged EV charging causes synchronized demand spikes that overload distribution transformers, degrade voltage quality, and reduce session completion rates. This system makes coordinated, slot-level charging decisions under grid constraints — specifically targeting Lebanon's intermittent EDL power supply.

**Decision automated:** Given EV sessions and grid context, the system decides:
1. Whether the grid can support the requested charging (compatible / conditional / reject)
2. How much power each EV receives at each 15-minute slot
3. Summary KPIs: energy delivered, cost, peak load, completion rate

**Why non-AI baselines are insufficient:** Simple FCFS (first-come-first-served) scheduling ignores grid constraints entirely. Threshold-based rules cannot capture the nonlinear interactions between transformer loading, cable impedance, phase balance, and charger count that the ML classifier learns from 40,000 simulated grid configurations.

---

# 2. System Architecture

## 2.1 Services

| Service | Port | Role | Technology |
|---|---|---|---|
| **EEP** (eep) | 8000 | Orchestrator — validates input, gates on grid-compat, fans out to IEPs | FastAPI, httpx async |
| **IEP-Forecast** | 8001 | Demand prediction with uncertainty bounds | 3× GradientBoostingRegressor |
| **IEP-Optimizer** | 8002 | LP charging schedule with greedy fallback | CVXPY + CLARABEL solver |
| **IEP-Governance** | 8003 | Model drift detection and retrain signaling | MAE + PSI statistics |
| **IEP-Grid-Compat** | 8004 | 2-stage grid feasibility gate | RandomForest classifier + regressor |
| MLflow | 5000 | Experiment tracking | MLflow |
| Prometheus | 9090 | Metrics collection (15-day retention) | Prometheus |
| Grafana | 3000 | Dashboards | Grafana |

## 2.2 Request Flow

```
Client → POST /schedule → EEP
  │
  ├─1─→ IEP-Grid-Compat: POST /predict
  │     Returns: compatibility_class, recommended_max_chargers
  │
  │  if not_compatible → EEP returns HTTP 422 (rejection)
  │  if conditional    → EEP caps sessions + throttles power
  │
  ├─2─→ (parallel) IEP-Optimizer: POST /optimize
  ├─2─→ (parallel) IEP-Forecast:  POST /forecast
  ├─2─→ (parallel) IEP-Governance: GET /governance/status
  │
  └───→ EEP merges results → ScheduleResponse to Client
```

**Code evidence (eep/main.py):**

| Step | Location | Verified |
|---|---|---|
| Input validation | Pydantic models L43–86 | ✅ |
| Grid-compat gate | L186–284 | ✅ |
| Session capping on conditional | L222–234 | ✅ |
| Power throttling on conditional | L240–278 | ✅ |
| Parallel fan-out (`asyncio.gather`) | L302 | ✅ |
| Response merging | L381–391 | ✅ |
| MLflow logging | L415–434 | ✅ |

**Key architectural properties:**
- **Conditional orchestration:** Grid-compat class gates whether optimizer runs
- **Parallel fan-out:** `asyncio.gather` for optimizer + forecast + governance
- **Graceful degradation:** Forecast/governance failures → degraded response; optimizer failure → HTTP 502
- **Rate limiting:** `slowapi` at 30 requests/min on `/schedule`
- **No ML in EEP:** `eep/main.py` has zero model loading or sklearn — only HTTP calls and payload construction

## 2.3 Endpoints

| Service | Endpoints |
|---|---|
| EEP | `POST /schedule`, `GET /health` |
| Forecast | `POST /forecast`, `POST /forecast/horizon`, `GET /health` |
| Optimizer | `POST /optimize`, `GET /health` |
| Governance | `POST /governance/status`, `GET /governance/status`, `POST /governance/retrain`, `GET /health` |
| Grid-Compat | `POST /predict`, `GET /model-info`, `GET /health` |

---

# 3. AI/ML Components

## 3.1 Grid Compatibility (IEP-Grid-Compat) — ⭐ Strongest AI Component

**Purpose:** Predict whether a transformer/feeder/charger configuration can safely support EV charging — without running a full OpenDSS power-flow simulation at inference time.

**Pipeline:**
- **Stage 1 — Classifier:** Predicts `compatible | conditional | not_compatible`
- **Stage 2 — Regressor:** Predicts recommended max active chargers (only when compatible/conditional)

**Model:** RandomForestClassifier (300 trees, balanced class weights) + RandomForestRegressor
**Training data:** 40,000 synthetic OpenDSS simulation rows (32,000 train / 8,000 test, stratified)
**Data leakage prevention:** Simulation outputs (overload_flag, transformer_loading_pct, min_bus_voltage_pu) excluded from features

**Verified metrics** (from `classifier_metrics.json`, `regressor_metrics.json`):

| Metric | Value |
|---|---|
| Classifier macro-F1 | **0.9554** (held-out test split) |
| Regressor MAE | **0.9037** chargers |
| Regressor R² | **0.9610** |
| Regressor RMSE | 1.5828 |

**Engineered features:** `nominal_load_ratio = (base_load + n_active × charger_kw) / transformer_kva`, `nominal_headroom_kw`
**Top feature:** `nominal_load_ratio` (31.7% importance)

**AI value verdict: STRONG** — eliminates expensive power-flow simulation at inference time. This is where AI adds the most value in the system.

## 3.2 Demand Forecast (IEP-Forecast) — ⚠️ Currently Decorative

**Purpose:** Predict 15-minute demand (kW) with confidence intervals.

**Model:** 3× GradientBoostingRegressor (mean, 10th percentile, 90th percentile)
**Training data:** ACN Adaptive Charging Network dataset (Caltech campus, 2,524 sessions, 2021)
**Features:** Cyclic time encodings (hour, DOW, month), lag features (1h, 4h, 24h, 1-week), rolling statistics

**Verified metrics** (from `metrics.json`):

| Metric | Value | Note |
|---|---|---|
| MAE | **1.7722 kW** | ⚠️ Training-set metric only |
| RMSE | **4.3143 kW** | ⚠️ Training-set metric only |

> **Known limitation:** `train.py` L99 evaluates on training data (`y_pred_train = model_mean.predict(X)`). No holdout evaluation script exists. Holdout data is available at `data/processed/demand_holdout.parquet`.

> **Known limitation:** Forecast output is informational only — the optimizer does not consume forecast predictions. The optimizer uses raw session inputs and a static building load profile. This makes the forecast service closer to "decorative AI" than "decision AI."

**AI value verdict: MODERATE** — useful for operational visibility, but currently doesn't influence any scheduling decision.

## 3.3 Optimizer (IEP-Optimizer) — Not AI (Deterministic OR)

**Purpose:** Allocate charging power across 96 daily slots (15-min) to maximize energy delivery under constraints.

**Algorithm:** CVXPY Linear Program with CLARABEL solver (≤20 sessions) + greedy fallback (>20 sessions or solve timeout >2s)
**Classification:** Operations research, not machine learning

**Constraints:**
- Per-slot transformer headroom (DOE Medium Office building load profile)
- Grid availability mask (Lebanon EDL patterns: split/morning/random)
- Per-session max charge rate and active time window
- TOU tariff cost minimization (SCE TOU-EV-9)

**Measured performance:** LP solves in 0.3–1.8s for 1–20 EVs on a 2-core container

**Note:** The LP optimizer is effectively the non-AI baseline itself. It gives global optimality, determinism, and full explainability — which is why it was chosen over RL.

## 3.4 Governance (IEP-Governance) — Statistical Monitoring

**Purpose:** Detect model drift and signal retraining need.

**Metrics computed:**
- Rolling MAE (model vs actual)
- MAE degradation vs baseline (threshold: >15%)
- PSI — Population Stability Index (threshold: >0.2)

**Drift trigger:** `psi > 0.2` OR `mae_degradation_pct > 15.0` (verified: `iep-governance/main.py` L130)

> **Known limitation:** `POST /governance/retrain` is a stub — returns `{"status": "triggered", "message": "Retraining pipeline would be invoked here"}`. It does not execute retraining.

**AI value verdict: WEAK as AI** — PSI and MAE degradation are statistics, not ML. Valuable for lifecycle monitoring, but overstating it as "AI" would be a stretch.

---

# 4. Data Foundation

## 4.1 EV Session Data

**Source:** ACN Adaptive Charging Network (Caltech campus, 2021) — public, peer-reviewed dataset

| Split | Sessions | Period |
|---|---|---|
| Train | 1,631 | Mar 21 – Jul 31, 2021 |
| Validation | 600 | Aug 2021 |
| Holdout | 293 | Sep 1–14, 2021 |

**Honest limitation:** ACN reflects a California university campus (L2, 6.6 kW). Lebanon context differs in charger mix and peak hours. Documented as known transfer learning gap.

## 4.2 Grid Availability

**Source:** Published EDL statistics (HRW 2023, Wikipedia, MERIP 2024)
**Module:** `data/grid_availability.py` — parametric patterns calibrated to cited daily hours
**Monte Carlo validation:** 1,000 simulated days confirm published averages (July 2021: cited 3.5 h/day, simulated 3.26 ± 2.92 h/day)

> **Labeling:** "Scenario-based availability derived from published EDL supply statistics" — not real outage logs.

## 4.3 Grid Simulation Data

**Source:** 40,000-row synthetic dataset from OpenDSS power-flow simulations
**Module:** `iep-grid-compatibility/train_classifier.py`
**OOD evaluation:** `data/grid_compat_realism_report.json` contains out-of-distribution analysis. No real-world grid validation exists.

## 4.4 Building Load & Tariff

- **Building load:** DOE Medium Office Reference Building, Climate Zone 3C (Los Angeles), scaled to 50 kW peak
- **Tariff:** SCE TOU-EV-9 (6 rate periods, $0.11–$0.53/kWh)

---

# 5. Engineering Tradeoffs

Five documented tradeoffs in `docs/tradeoffs.md`:

| ID | Decision | Chosen | Rejected | Key evidence |
|---|---|---|---|---|
| T-001 | Scheduling algorithm | CVXPY LP (CLARABEL) | Reinforcement Learning | LP: global optimum, deterministic, 0.3–1.8s solve. RL: requires 1M+ training steps, black-box |
| T-002 | Grid-compat model | RandomForest | Neural Network | RF: macro-F1=0.955 on 3,739 rows, built-in feature importances. NN: overfitting risk on small data |
| T-003 | Grid availability | Deterministic parametric patterns | LSTM probability model | Deterministic: testable in CI, no real outage logs needed. LSTM: requires 30+ days of real data |
| T-004 | Architecture | Microservices (5 IEPs) | Monolith | Microservices: independent scaling, fault isolation, 5ms inter-service latency. Monolith: 0ms calls but no isolation |
| T-005 | Training data | ACN (Caltech, 2,524 sessions) | Lebanon-specific collection | ACN: public, validated, available now. Lebanon: 0 public EV datasets exist |

---

# 6. Testing

**Total test functions: 69** (verified by `def test_` count across all files)

| File | Tests | Scope |
|---|---|---|
| `test_eep.py` | 16 | EEP endpoint responses, KPIs, edge cases |
| `test_optimizer.py` | 11 | LP correctness, constraints, fallback |
| `test_forecast.py` | 10 | Predictions, CI bounds, horizon endpoint |
| `test_governance.py` | 9 | Drift detection, perfect/drifted records |
| `test_grid_compatibility.py` | 15 | Classification, validation, model-info |
| `test_integration.py` | 8 | Cross-service E2E, throttling, grid rejection |

**Additional validation scripts:**
- `grid_compat_sweep.py` — 43,200 parameter configurations
- `validate_grid_compat.py` — 3-tier API validator
- `grid_compat_accuracy.py` — direct model accuracy on simulation dataset

**Execution:** All tests run against live Docker containers (no mocks). Last reported result: **68 passed, 1 skipped**.

---

# 7. Observability

**Stack:** Prometheus (scraping all 5 services at `/metrics`) → Grafana (provisioned dashboard at `monitoring/grafana/dashboards/ev_platform.json`)

| Category | Metrics |
|---|---|
| HTTP (all services) | `http_requests_total` (by method/endpoint/status), `http_request_duration_seconds` (histogram — p50/p95 computable) |
| Forecast | `ev_forecast_predicted_kw_avg`, `ev_forecast_confidence_width_avg`, `ev_forecast_n_slots` |
| Optimizer | `ev_optimizer_solves_total` (by status), `ev_optimizer_solve_time_seconds`, `ev_optimizer_transformer_peak_kw` |
| Governance | `ev_governance_mae_kw`, `ev_governance_psi`, `ev_governance_drift_detected`, `ev_governance_retrain_recommended` |

> **Gap:** No Prometheus alert rules file exists yet. No explicit p50/p95 Grafana panel (computable from histogram but not pre-built).

---

# 8. Security & Robustness

| Feature | Implementation |
|---|---|
| Input validation | Pydantic models with strict types, `Literal` enums for grid patterns |
| Rate limiting | `slowapi` — 30/min on `/schedule` |
| Timeouts | httpx 10s per IEP call, 30s client timeout |
| Fallback | LP → greedy scheduler; forecast/governance degrade gracefully |
| Health checks | `/health` on all 5 services |
| CORS | `allow_origins=["*"]` ⚠️ development setting — must be restricted for production |
| `kwh_requested` lower bound | ⚠️ No `ge=0` constraint — negative values pass Pydantic and reach LP |
| `connection_time > disconnect_time` | No explicit error — session gets 0 kWh, non-catastrophic |

---

# 9. Failure Mode Analysis

## Service Crash Behavior

| Crashed service | EEP behavior | Recovery |
|---|---|---|
| `iep-grid-compatibility` | Logs warning, skips gate, proceeds to optimize | Automatic on restart |
| `iep-forecast` | Returns `forecast_summary: {degraded: true}` | Automatic on restart |
| `iep-governance` | Returns `governance_summary: null` | Automatic on restart |
| `iep-optimizer` | Returns HTTP 502 — hard failure | Correct — optimizer is required |
| `mlflow` | Each service catches exception, logs warning, continues | Non-blocking |

## Overload Scenarios

| Scenario | Actual behavior | Acceptable |
|---|---|---|
| 100 EV sessions | `n > 20` triggers greedy fallback. O(n×96) — fast | ✅ |
| Transformer at 100% utilization (headroom = 0) | LP returns empty schedule, `sessions_fully_charged = 0` | ✅ |
| Grid completely off (0 available hours) | `grid[]` all zeros, LP/greedy allocates 0 kWh | ✅ |
| `kwh_requested: -5.0` | Passes Pydantic, LP behavior unpredictable | ⚠️ Minor gap |
| `max_charge_rate_kw: 1000` | Clamped to 7.4 kW by `EVSession.clamp_charge_rate()` | ✅ |

## Model Drift Behavior

| Signal | Detection | Response |
|---|---|---|
| Forecast accuracy degrades | PSI > 0.2 OR MAE degradation > 15% → `drift_detected: true` | Retrain endpoint stub only — **no actual action** |
| Grid-compat model goes stale | No automated validation pipeline | **GAP** — no staleness detection |

---

# 10. Rubric Compliance

| § | Requirement | Status | Evidence |
|---|---|---|---|
| 3 | Problem + non-AI baseline justification | **MET** | Problem defined; T-001 provides LP vs RL baseline comparison |
| 4.1 | EEP + ≥2 IEPs | **MET** | 1 EEP + 4 IEPs, each with own container, port, Dockerfile |
| 4.2 | IEPs architecturally independent, non-trivial | **MET** | Separate Dockerfiles, requirements, distinct logic per service |
| 4.3 | Conditional + parallel orchestration | **MET** | Grid-compat gates optimizer; `asyncio.gather` for parallel fan-out |
| 5 | ≥3 tradeoffs with evidence | **MET** | 5 tradeoffs in `docs/tradeoffs.md` with measurement tables |
| 6 | Git discipline | **PARTIAL** | Feature branches exist, but only 12 commits (low for project scope) |
| 7 | MLOps lifecycle (train/eval/promote/rollback) | **PARTIAL** | MLflow tracking ✅, training scripts ✅, retrain is stub, no automated promotion/rollback |
| 8.1 | Unit + integration + E2E tests | **MET** | 69 tests, cross-service integration verified, no mocks |
| 8.2 | Regression / golden dataset / data validation | **PARTIAL** | Parameter sweep exists (43,200 configs), no formal golden dataset test |
| 9 | Docker + Kubernetes | **PARTIAL** | Docker Compose ✅ — **Kubernetes: GAP** (no manifests) |
| 10 | Cloud deployment, publicly accessible | **GAP** | Not deployed. No cloud URL. Rubric: "Local-only demos are not accepted." |
| 11 | Monitoring (Prometheus/Grafana + ML metrics) | **MET** | Full stack with domain-specific metrics per service |
| 12 | Security/robustness | **MET** | Validation, rate limiting, timeouts, graceful degradation |

**Summary:** 9 MET · 4 PARTIAL · 2 hard GAPs (§9 K8s, §10 Cloud)

---

# 11. Known Gaps (Priority Order)

| # | Gap | Rubric impact | Effort |
|---|---|---|---|
| **1** | **No cloud deployment** | §10: 0 pts, instant fail | 4–6h |
| **2** | **No Kubernetes manifests** | §9: partial only | 2–3h |
| **3** | **Forecast evaluated on training data only** | Honesty/defense risk | 30min |
| **4** | **No automated model promotion/rollback** | §7: partial only | 1–2h |
| **5** | **Forecast doesn't feed optimizer** | Forecast is decorative | 2–3h |
| **6** | **Retrain endpoint is a stub** | §7: governance loop incomplete | 1–2h |
| **7** | **No explicit AI vs non-AI baseline comparison** | §3: cannot quantify AI value | 2h |
| **8** | **README lists 4 services** (actually 5) | Stale documentation | 15min |
| **9** | **No Prometheus alert rules** | §11: partial | 30min |
| **10** | **`kwh_requested` has no lower bound** | §12: minor input gap | 15min |

---

# 12. Upgrade Roadmap

Concrete, measurable improvements ordered by rubric impact:

| # | What | Where | Measurable target | Baseline |
|---|---|---|---|---|
| **U-1** | Forecast holdout evaluation | `iep-forecast/evaluate.py` (new) | Report train MAE vs holdout MAE, CI coverage | Training MAE=1.77 (current, optimistic) |
| **U-2** | MLOps promotion gate | `scripts/promote_model.py` (new) | If holdout MAE < baseline×1.15 AND macro-F1 > 0.93 → promote, else rollback. Log to MLflow. | Manual/no promotion (current) |
| **U-3** | AI vs FCFS comparison endpoint | `POST /schedule/compare` on EEP | Δ cost_savings_usd, overload_minutes_avoided, completion_rate | FCFS = arrival order, no optimization |
| **U-4** | Forecast → optimizer integration | `iep-optimizer/main.py`, `eep/main.py` | Replace static building_load.py headroom with forecast-predicted demand | Static DOE profile (current) |
| **U-5** | Explainability for grid-compat | `iep-grid-compatibility/main.py` — add `explain` to `/predict` response | Top-3 feature importances + counterfactual ("reduce chargers by X to reach compatible") | No explanation (current) |
| **U-6** | Stochastic LP (grid uncertainty) | `iep-optimizer/main.py` | Replace binary `grid[t]` with `P(grid_on[t])` from forecast CI | Deterministic grid mask (current) |

**Priority for A closure:** U-1 → U-2 → U-3 (30min, 1-2h, 2h)
**Priority for A+ closure:** U-4 → U-5 (makes forecast non-decorative, adds explainability)

---

# 13. Professor Defense Guide

Hard questions a professor or jury would ask, with honest answers:

| Question | Honest answer | Risk level |
|---|---|---|
| "Forecast MAE is 1.77 — on what dataset?" | Training set only. No holdout eval exists yet. | 🔴 High |
| "How does the forecast influence scheduling?" | It doesn't. Optimizer uses raw sessions + static building load. Forecast is informational only. | 🔴 High |
| "Show me your Kubernetes manifests." | They don't exist. This is a hard rubric requirement (§9). | 🔴 High |
| "Show me the live cloud endpoint." | Not deployed. Rubric §10: "Local-only demos are not accepted." | 🔴 High |
| "Your retrain endpoint — does it actually retrain?" | No. Returns stub string `"Retraining pipeline would be invoked here"`. | 🟡 Medium |
| "Where is the promotion/rollback logic?" | Doesn't exist. MLflow is used for logging only. | 🟡 Medium |
| "What is your non-AI baseline comparison?" | LP vs RL documented in tradeoffs.md, but no runtime FCFS comparison exists. | 🟡 Medium |
| "What happens with negative kwh_requested?" | No `ge=0` constraint. LP behavior is unpredictable. | 🟡 Medium |
| "Grid-compat trained on synthetic data — does it transfer to real grids?" | Trained on OpenDSS simulations. OOD analysis in `grid_compat_realism_report.json`. No real-world validation. | 🟡 Medium |
| "Your metrics.py is copy-pasted 5 times — why not a shared package?" | Pragmatic decision. Avoided inter-service dependency complexity. Could be a shared Docker layer. | 🟢 Low |

**Strongest defenses available:**
- Grid-compat ML pipeline: macro-F1=0.9554, 40K training rows, no data leakage, OOD-evaluated
- Architecture: genuine conditional + parallel orchestration (not a monolith with fake boundaries)
- Testing: 69 tests, no mocks, real Docker containers, parametric sweep of 43,200 configs
- Observability: production-grade Prometheus/Grafana with domain-specific ML metrics

---

# 14. Score Summary

| Dimension | Rating | Notes |
|---|---|---|
| Architecture | ⭐⭐⭐⭐⭐ | Genuine microservices, conditional gate, parallel fan-out, graceful degradation |
| AI substance | ⭐⭐⭐☆☆ | Grid-compat is strong; forecast is decorative; governance is statistics |
| Testing | ⭐⭐⭐⭐☆ | 69 tests, integration coverage, edge cases. No golden dataset. |
| Observability | ⭐⭐⭐⭐☆ | Prometheus + Grafana + domain ML metrics. No alert rules yet. |
| MLOps maturity | ⭐⭐☆☆☆ | MLflow tracking only. No automation. Retrain is stub. |
| Deployment readiness | ⭐⭐☆☆☆ | Docker Compose works locally. No K8s, no cloud. |
| Documentation | ⭐⭐⭐⭐☆ | Tradeoffs documented with evidence. README stale (4 vs 5 services). |
| Security | ⭐⭐⭐☆☆ | Rate limiting + validation present. CORS open. No secrets management. |
| **Overall verdict** | **A- ready** | Two hard rubric gaps (K8s + cloud) currently prevent A grade. |

---

# 15. Key File Map

```
eep/main.py                               Orchestrator: validation, grid gate, parallel fan-out
iep-forecast/main.py                      Forecast inference API (slot-based + horizon)
iep-forecast/train.py                     GBR model training with MLflow logging
iep-optimizer/main.py                     LP optimizer + greedy fallback
iep-governance/main.py                    Drift detection (MAE, PSI)
iep-grid-compatibility/main.py            2-stage classifier + regressor inference
iep-grid-compatibility/train_classifier.py  Classifier training pipeline
data/preprocess.py                        ACN data → features → train/val/holdout splits
data/grid_availability.py                 Lebanon EDL availability (parametric, cited sources)
data/grid_simulator.py                    Markov chain grid simulator for LSTM training data
data/building_load.py                     DOE Medium Office baseline load profile
data/tariff.py                            SCE TOU-EV-9 tariff schedule
docker-compose.yml                        All 8 services with health checks
eep/metrics.py                            Prometheus instrumentation (copied to each service)
docs/tradeoffs.md                         5 engineering tradeoffs with evidence
docs/rubric_extracted.txt                 Full rubric text
tests/test_integration.py                 Cross-service E2E tests
tests/validate_grid_compat.py             3-tier compatibility API validator
tests/grid_compat_sweep.py                43,200-configuration parameter sweep
iep-grid-compatibility/models/classifier_metrics.json   Verified classifier metrics
iep-grid-compatibility/models/regressor_metrics.json    Verified regressor metrics
iep-forecast/models/metrics.json          Forecast metrics (training-set only)
data/grid_compat_realism_report.json      OOD evaluation for grid-compat model
```

---

# 16. Runbook

**Start all services:**
```bash
docker compose up -d --build
```

**Verify health:**
```bash
curl http://localhost:8000/health   # EEP
curl http://localhost:8001/health   # Forecast
curl http://localhost:8002/health   # Optimizer
curl http://localhost:8003/health   # Governance
curl http://localhost:8004/health   # Grid-Compat
```

**Run tests (requires services running):**
```bash
python -m pytest tests/ -v
```

**Sample schedule request:**
```bash
curl -X POST http://localhost:8000/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "date": "2021-08-01",
    "sessions": [{
      "session_id": "ev-001",
      "connection_time": "2021-08-01T00:00:00",
      "disconnect_time": "2021-08-01T03:00:00",
      "kwh_requested": 20.0,
      "kwh_delivered": 0.0,
      "max_charge_rate_kw": 7.4,
      "has_user_inputs": true
    }],
    "grid_pattern": "morning"
  }'
```

**View metrics:**
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)
- MLflow: http://localhost:5000

---

*All claims verified against source code and artifact files on 2026-03-29.*
*Consolidated from: COMPREHENSIVE_ANALYSIS_AND_ACTION_PLAN.md, QUICK_REFERENCE_CARD.md, REALISTIC_AI_STRATEGY.md, SESSION_SUMMARY_EVERYTHING_WE_DID.md, deep_audit_report_2026-03-29.md, HANDOFF.md, and full_system_audit.md*
