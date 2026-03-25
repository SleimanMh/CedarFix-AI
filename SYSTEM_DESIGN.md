# System Design Document
# AI-Assisted EV Charging Optimization and Grid Compatibility System

**Course:** AI in Industry / AI Systems  
**Document Type:** Technical System Design Proposal  
**Version:** 1.0  
**Date:** March 2026

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [System Architecture Overview](#2-system-architecture-overview)
3. [Cloud Deployment and Containerization](#3-cloud-deployment-and-containerization)
4. [ML Components](#4-ml-components)
5. [Optimization Component](#5-optimization-component)
6. [Grid Validation Layer](#6-grid-validation-layer)
7. [Data Requirements](#7-data-requirements)
8. [Validation Methodology](#8-validation-methodology)
9. [Experimental Design](#9-experimental-design)
10. [Live Demonstration Plan](#10-live-demonstration-plan)
11. [Risk and Limitations](#11-risks-and-limitations)

---

## 1. Problem Statement

### 1.1 Context

The accelerating adoption of Electric Vehicles (EVs) introduces a structural challenge for power grid operators: EV charging demand is **clustered in time and space**. Vehicles tend to arrive and charge simultaneously — at workplaces in the morning, at shopping centers during peak hours, and at residential chargers in the evening. This clustering creates sharp load spikes that can exceed the rated capacity of local transformers, causing hardware stress, voltage instability, and in the worst case, outages.

Existing charging management approaches are largely reactive: a vehicle arrives, connects, and immediately draws maximum power. No system-level coordination considers what other vehicles will arrive in the next hour, when the current vehicles intend to leave, or how the aggregate draw compares to grid capacity.

### 1.2 Target Deployment Environments

This system is designed for **capacity-constrained charging environments**, including:

- University or corporate campus charging lots (20–200 chargers, shared transformer)
- Fleet depot overnight charging (buses, delivery vehicles, taxis)
- Commercial building parking with on-site solar or battery storage

### 1.3 Core Problem Definition

Given:
- A set of EVs currently connected to chargers
- A forecast of EVs arriving in the near future
- A grid capacity constraint (transformer rating, line capacity)
- Each EV's energy requirement and departure deadline

**Decide:** How much power to allocate to each charger at each time step to maximize the fraction of energy demand that is satisfied before departure, without overloading the grid.

### 1.4 Why AI Is Necessary

A rule-based system can enforce capacity limits reactively, but cannot:
- Anticipate demand arriving in the next 30–60 minutes
- Predict which vehicles will leave soon and therefore need priority
- Adapt allocation strategies across different days, seasons, and demand patterns

This justifies the use of ML forecasting and a learned optimization approach.

---

## 2. System Architecture Overview

### 2.1 High-Level Pipeline

```
Historical EV charging data (ACN-Data, synthetic)
         │
         ▼
┌─────────────────────────────┐
│  ML Service 1               │  ← Internal Container A
│  EV Arrival & Demand        │
│  Forecasting                │
└─────────────┬───────────────┘
              │  Predicted arrivals, predicted demand
              ▼
┌─────────────────────────────┐
│  ML Service 2               │  ← Internal Container A (same service)
│  Departure Time Prediction  │
└─────────────┬───────────────┘
              │  Predicted stay durations per vehicle
              ▼
┌─────────────────────────────┐
│  Optimization Engine        │  ← Internal Container B
│  Power Allocation Scheduler │
└─────────────┬───────────────┘
              │  Charging schedule (kW per charger per slot)
              ▼
┌─────────────────────────────┐
│  Grid Validation Service    │  ← Internal Container B (same service)
│  Simulink / Power Flow      │
└─────────────┬───────────────┘
              │  Validated or adjusted schedule + grid metrics
              ▼
┌─────────────────────────────┐
│  API Gateway + Dashboard    │  ← External Container (public endpoint)
│  REST API + Streamlit/Dash  │
└─────────────────────────────┘
```

### 2.2 Architectural Principles

| Principle | Rationale |
|-----------|-----------|
| **Microservice separation** | ML inference, optimization, and grid validation have different compute profiles and can fail independently |
| **Internal vs. external endpoints** | ML and optimization services are never directly exposed; only the API Gateway faces the internet |
| **Stateless inference** | Each scheduling cycle is independent; state is persisted in a shared database, not in containers |
| **Offline-first ML** | Models are trained offline on historical data and loaded at container startup; no online learning during demo |

### 2.3 Data Flow Summary

Each scheduling cycle (triggered every 5–15 minutes):

1. The API Gateway collects the current grid state (connected vehicles, current loads).
2. It calls the **ML Forecasting Service** to obtain a demand forecast for the next N time windows.
3. It calls the **Departure Prediction Service** to obtain estimated departure times for connected vehicles.
4. It forwards this information to the **Optimization Engine**, which computes a power allocation plan.
5. The plan is passed to the **Grid Validation Service**, which simulates the resulting load on the transformer and returns safety metrics.
6. If the plan is feasible, it is committed. If it violates constraints, the optimizer is re-queried with tighter bounds.
7. The API Gateway stores the decision and exposes it via REST API and dashboard.

---

## 3. Cloud Deployment and Containerization

### 3.1 Container Architecture

The system is designed around **three Docker containers** with clearly separated responsibilities.

---

#### Container 1 — External Endpoint: API Gateway + Dashboard
**Exposure:** Public HTTPS endpoint  
**Responsibilities:**
- Serves the REST API consumed by charger hardware, SCADA systems, or third-party clients
- Hosts the real-time monitoring dashboard (Streamlit or Plotly Dash)
- Authenticates requests (API key or OAuth2)
- Routes internal requests to Container 2 and Container 3 over a private network
- Stores and retrieves scheduling history from a cloud database (e.g., PostgreSQL on managed cloud)

**Why external:** This is the only surface exposed to users, operators, and hardware. Keeping it separate limits the attack surface and allows independent scaling.

---

#### Container 2 — Internal Endpoint: ML Inference Service
**Exposure:** Internal network only (not reachable from the internet)  
**Responsibilities:**
- Serves Model 1: EV Arrival and Energy Demand Forecasting
- Serves Model 2: Departure Time / Charging Duration Prediction
- Loads pre-trained model artifacts at startup (from cloud object storage, e.g., S3 or Azure Blob)
- Exposes a lightweight internal REST or gRPC API consumed only by Container 1

**Why internal:** Raw ML inference endpoints should never be public. Model artifacts may contain proprietary training data, and direct access could be used to probe model behavior adversarially.

---

#### Container 3 — Internal Endpoint: Optimization + Grid Validation Service
**Exposure:** Internal network only  
**Responsibilities:**
- Receives forecasted demand (from Container 2) and current vehicle state (from Container 1)
- Runs the power allocation optimization (LP/MIP/heuristic)
- Runs the grid simulation to validate the resulting schedule
- Returns the final allocation plan and grid metrics to Container 1

**Why internal:** Optimization runs can be computationally intensive. Isolating this service allows resource limits (CPU/RAM) to be configured without impacting the API response time.

---

### 3.2 Deployment Platform Options

| Platform | Notes |
|----------|-------|
| **AWS ECS / Fargate** | Managed containers, easy IAM-based internal networking |
| **Azure Container Apps** | Serverless scaling, built-in internal/external ingress separation |
| **Google Cloud Run** | Per-request billing, easy for controlled demo loads |
| **Kubernetes (EKS/GKE)** | Most flexible; use if already familiar with K8s |

For the **course project**, a minimal viable deployment is:
- One cloud VM (e.g., AWS EC2 t3.medium or Azure B2s) running Docker Compose
- Internal containers on a private Docker bridge network
- External container exposed via HTTPS using a reverse proxy (nginx or Traefik)
- A cloud-managed PostgreSQL instance for persistence

This keeps cost under $10/month for the demo period while demonstrating correct container isolation.

### 3.3 Networking and Security

- All inter-container communication uses the private Docker network; Container 2 and Container 3 publish **no ports to the host**.
- Container 1 communicates with Container 2 and 3 using service names on the internal network (e.g., `http://ml-service:8001`).
- Inbound traffic to Container 1 is TLS-terminated.
- API keys are stored as environment variables injected at deploy time, never baked into images.
- Model artifacts are pulled from object storage at container startup, not bundled in the image, so the image itself contains no proprietary data.

### 3.4 Deployment Diagram

```
Internet
   │
   │ HTTPS (443)
   ▼
┌──────────────────────────────────────────┐
│         Cloud VM / Container Host        │
│                                          │
│  ┌───────────────────────────────────┐   │
│  │  Container 1 (External)           │   │
│  │  nginx + API Gateway + Dashboard  │◄──┼── Public traffic
│  └──────────┬──────────────┬─────────┘   │
│             │ internal net │             │
│  ┌──────────▼──────┐  ┌───▼──────────┐  │
│  │  Container 2    │  │  Container 3  │  │
│  │  ML Inference   │  │  Optimizer +  │  │
│  │  (internal)     │  │  Grid Sim     │  │
│  └─────────────────┘  └───────────────┘  │
│                                          │
│  ┌───────────────────────────────────┐   │
│  │  Managed PostgreSQL (cloud DB)    │   │
│  └───────────────────────────────────┘   │
└──────────────────────────────────────────┘
```

---

## 4. ML Components

### 4.1 Model 1 — EV Arrival and Energy Demand Forecasting

#### Purpose

The optimization layer needs to plan **ahead of actual arrivals**. Without a forecast, the scheduler can only react to vehicles already connected, which limits its ability to reserve capacity for imminent arrivals or smooth demand. This model provides a short-horizon forecast of how many EVs will arrive and how much total energy they will require in the next scheduling window (30–60 minutes).

#### Input Features

| Feature Category | Examples |
|-----------------|---------|
| Temporal | Hour of day, day of week, month, public holiday flag |
| Recent history | EV arrival rate over the past 1h, 2h, 4h |
| Site context | Building base load (non-EV), number of currently connected vehicles |
| Weather | Temperature, precipitation, cloud cover |
| Contextual | Special events, semester calendar (for campus sites) |

#### Output Variables

- `predicted_ev_arrivals`: integer count expected in the next window
- `predicted_energy_demand_kWh`: total energy demand expected from arriving vehicles

#### Candidate Model Architectures

| Architecture | Characteristics | Appropriate When |
|-------------|-----------------|-----------------|
| Gradient Boosted Trees (XGBoost / LightGBM) | Fast training, interpretable feature importance, no temporal structure | Features adequately encode time context |
| Random Forest | Robust to outliers, lower risk of overfitting | Small dataset |
| LSTM / GRU | Captures sequential dependencies automatically | Dataset has clear temporal patterns over weeks/months |

#### Training Strategy

- Train on historical session data from the deployment site (or ACN-Data as a proxy dataset)
- Features are engineered from raw timestamps; temporal features are cyclically encoded (sin/cos hour encoding)
- Cross-validation is performed using a **walk-forward** (time-series split) strategy — never shuffle-split, which leaks future information into training

#### Evaluation Metrics

- Mean Absolute Error (MAE) on arrival count
- Root Mean Squared Error (RMSE) on energy demand
- Calibration of uncertainty bounds (if probabilistic outputs are used)

---

### 4.2 Model 2 — Departure Time / Charging Duration Prediction

#### Purpose

The optimizer must decide how urgently each vehicle needs power. A vehicle departing in 20 minutes at 20% state of charge has a completely different priority than one staying for 8 hours. This model predicts the expected stay duration for each vehicle upon arrival, enabling priority-aware scheduling.

#### Input Features

| Feature Category | Examples |
|-----------------|---------|
| Session context | Arrival time, day of week, arrival SoC |
| Vehicle profile | Battery capacity (kWh), charger power limit (kW) |
| Historical pattern | Median stay duration for this user at this time slot (if user ID available) |
| Site context | Station type (workplace, retail, depot) |

#### Output

- `predicted_stay_duration_minutes`: continuous regression target
  - Alternatively: `predicted_departure_time` as an absolute timestamp

#### Candidate Model Architectures

The problem is a regression task on tabular features. Gradient boosted trees are the primary candidate. A neural network baseline (feedforward MLP) is included for comparison.

#### Training Strategy

- Per-session historical data is used
- Target leakage is carefully audited: no features derived from session end time can appear in training
- Model is evaluated on held-out future sessions using time-based splitting

#### Evaluation Metrics

- MAE on stay duration prediction (minutes)
- Percentage of sessions where predicted departure is within ±15 minutes of actual
- Impact on downstream delivery rate: if departure prediction is accurate, does the optimizer achieve higher satisfaction?

---

## 5. Optimization Component

### 5.1 Problem Formulation

At each scheduling cycle, the optimizer receives:
- Set of connected vehicles: `{v_1, ..., v_n}`, each with remaining energy requirement `e_i` and predicted departure time `t_i`
- Forecasted arriving vehicles from Model 1: estimated count and energy per time window
- Grid capacity: transformer limit `P_max` (kW), individual charger limits `p_i^max` (kW)

**Decision variables:** `x_{i,k}` = power allocated to vehicle `i` in time slot `k` (kW)

**Objective:** Maximize the fraction of requested energy delivered before departure:

$$\text{maximize} \sum_{i} \min\left(\sum_{k \leq t_i} x_{i,k} \cdot \Delta t,\ e_i\right) / \sum_i e_i$$

**Subject to:**
- $\sum_i x_{i,k} \leq P_{max}$ for all time slots $k$ (transformer limit)
- $0 \leq x_{i,k} \leq p_i^{max}$ for all vehicles $i$ and slots $k$ (charger limit)
- Battery and ramp-rate constraints per vehicle

### 5.2 Baseline Contrast

The AI-optimized schedule is explicitly compared against a **first-come, first-served (FCFS) at maximum power** baseline. In this baseline, vehicles draw maximum power immediately upon connection, with no coordination beyond hard curtailment when the aggregate exceeds `P_max` (which is handled by proportional reduction). This baseline is computationally trivial and represents current industry practice for unmanaged charging.

### 5.3 Baseline Definition (Formal)

In the FCFS baseline: $x_{i,k} = \min(p_i^{max},\ \text{available capacity at step } k)$, where available capacity is distributed in FCFS order with no future planning.

### 5.4 Solution Approaches

| Approach | Trade-off |
|----------|----------|
| Linear Programming (LP) | Optimal, fast for moderate problem sizes; requires linearizing binary constraints |
| Mixed-Integer Programming (MIP) | Handles discrete decisions (on/off, charger selection); slower for large instances |
| Model Predictive Control (MPC) | Continuously re-solves LP over a rolling horizon; well-suited to online operation |
| Greedy Heuristic (earliest deadline first) | Sub-optimal but interpretable; useful as a secondary baseline |

For the course project, a **rolling-horizon LP** (MPC-style) is the primary implementation target, with the greedy heuristic as a fallback.

---

## 6. Grid Validation Layer

### 6.1 Purpose

The optimization layer minimizes load at the aggregate level, but does not model internal grid physics. The grid validation layer checks whether the proposed charging schedule is safe from a power systems perspective:

- Does the aggregate load violate transformer thermal limits?
- Does distributed EV load cause voltage deviations on feeder nodes?
- Are there line capacity violations?

### 6.2 Simulation Approaches

#### Option A — MATLAB / Simulink
The existing `ev_grid_model.slx` and `ev_grid_simulation.m` files in the repository provide a starting point. The Simulink model can simulate transformer behavior, feeder voltage, and reactive power effects. The optimizer outputs a schedule, which is injected as a time-varying load profile into the simulation. The simulation returns thermal violation flags and voltage profiles.

**Suitable for:** Accurate power flow simulation, transformer thermal modeling, presentations that require showing a Simulink scope output.

#### Option B — Python-Based Simplified Power Flow
A simplified power flow model (e.g., using the DC power flow approximation or PyPSA) treats the campus grid as a radial distribution feeder with a single transformer and N load nodes. This approach has lower fidelity but is faster, fully reproducible, and does not require a MATLAB license.

**Suitable for:** Automated testing, CI/CD validation, presentations on machines without MATLAB.

#### Recommended Strategy: Hybrid
Use the Python-based model for automated evaluation runs (including all experimental scenarios in Section 9). Use the Simulink model selectively for a high-fidelity demonstration during the live presentation, showing its output on the dashboard.

### 6.3 Validation Criteria

The grid validator returns a binary feasibility flag and the following metrics for each simulation run:

| Metric | Threshold |
|--------|-----------|
| Transformer loading (%) | Must not exceed 100% (warn at 80%) |
| Min bus voltage (p.u.) | Must be ≥ 0.95 p.u. |
| Max line current (A) | Must be ≤ rated thermal limit |
| Overload minutes per hour | Target: 0 for AI system; expected > 0 for FCFS baseline under peak conditions |

---

## 7. Data Requirements

### 7.1 Primary Dataset — ACN-Data

The **Adaptive Charging Network (ACN-Data)** dataset from Caltech is the primary data source. It contains real EV charging sessions from the JPL and Caltech campuses, including:

- Arrival and departure timestamps
- Energy delivered (kWh)
- Peak current requested
- Charger ID and station location

This dataset provides authentic behavioral patterns for training Models 1 and 2 and for constructing realistic simulation scenarios.

**Access:** Publicly available at `ev.caltech.edu/dataset`. The file `acn_sessions.json` already present in the workspace corresponds to this dataset.

### 7.2 Synthetic Data Augmentation

For scenarios not well-represented in ACN-Data (e.g., extreme peak events, grid outage scenarios), synthetic sessions are generated by parameterizing known distributions of arrival rates, SoC on arrival, and stay durations. This is used exclusively for stress-testing the validation scenarios, not for model training.

### 7.3 Grid Topology Data

A representative radial distribution feeder topology is used:
- Single 500 kVA transformer (representative of a campus or commercial building)
- 50 load nodes, with 20 charger nodes (Level 2, 7.2 kW each) and 30 building load nodes
- Base building load profile drawn from EnergyPlus typical commercial building simulations

### 7.4 Feature Engineering Requirements

| Feature | Derivation |
|---------|-----------|
| Session SoC on arrival | Estimated from energy delivered vs. battery capacity |
| Station historical load profile | Rolling window aggregation from session history |
| Temporal features | Cyclical sin/cos encoding of hour and day-of-week |
| Residual transformer capacity | `P_max - current_aggregate_load` at each step |

---

## 8. Validation Methodology

> **This is the most important section of the document.** All design choices — model architecture, optimization formulation, container isolation — must ultimately be justified by measurable experimental results. This section defines exactly how the system will be evaluated and what claims it supports.

### 8.1 Overall Validation Framework

The validation framework has three layers:

| Layer | Question Asked | Method |
|-------|---------------|--------|
| **Component validation** | Are the ML models accurate? Does the optimizer find better solutions than baselines? | Offline evaluation on held-out sessions |
| **System integration validation** | Does the end-to-end pipeline run correctly, and is the grid always safe? | Simulation runs on fixed scenarios |
| **Presentation-time live validation** | Can professors interact with the system and see measurable differences in real time? | Live demo with replay scenarios |

---

### 8.2 Component Validation

#### ML Model 1 — Demand Forecasting

**Protocol:**
- Split ACN-Data sessions chronologically: 70% train, 10% validation, 20% test (held-out final months)
- Walk-forward cross-validation on the training set
- Report MAE and RMSE on the test set for both output variables

**Acceptance criterion:** Arrival count MAE ≤ 1.5 vehicles per 30-minute window; energy demand RMSE ≤ 5 kWh per window.

**Comparison:** Report against a naive persistence baseline (forecast = last observed value) and a calendar-average baseline (forecast = historical mean for this hour and day of week). The ML model must outperform both baselines on the test set to justify its inclusion.

---

#### ML Model 2 — Departure Time Prediction

**Protocol:**
- Same temporal split as Model 1
- Evaluate MAE on stay duration in minutes
- Report the percentage of predictions within ±15 and ±30 minutes of actual departure

**Acceptance criterion:** MAE ≤ 30 minutes; ≥60% of predictions within ±15 minutes.

**Ablation study:** Run the optimizer with (a) ground truth departure times, (b) ML-predicted departure times, and (c) a fixed-duration assumption (e.g., "all vehicles stay 4 hours"). Compare downstream delivery rates. This quantifies the practical value of the departure prediction model.

---

#### Optimization Engine

**Protocol:**
- Run the optimizer on all test set days using replay simulation (described below)
- Compare against two baselines:
  - Baseline A: FCFS at maximum power (unmanaged charging)
  - Baseline B: Greedy earliest-deadline-first (simple heuristic)

**Evaluation metrics:**
- Charging deadline satisfaction rate (% of sessions fully charged by departure)
- Transformer overload minutes per day
- Peak grid load (kW)
- Average energy delivery rate (%)

---

### 8.3 System Integration Validation — Simulation Scenarios

The following four scenarios are run as end-to-end system tests. Each scenario replays historical or synthetic session arrival data through the full pipeline (forecast → optimize → grid simulate) and records outcomes.

---

#### Scenario 1 — Normal Weekday Demand

**Description:** A typical weekday with moderate EV arrivals, representative of the median day in ACN-Data.

**What this tests:** Baseline system correctness. The AI system should achieve high satisfaction rates with no transformer overload.

**Success criterion:**
- Satisfaction rate ≥ 90%
- Zero transformer overload minutes
- Peak load ≤ 90% of transformer capacity

---

#### Scenario 2 — Peak Demand Event

**Description:** A day with unusually high concurrent arrivals (top 5th percentile of arrival rates in the dataset). For example: Monday morning return from a long weekend at a campus site.

**What this tests:** The optimizer's ability to distribute load under congestion. The FCFS baseline will overload the transformer in this scenario; the AI system should avoid overload while still maximizing satisfaction.

**Key comparison metric:** Transformer overload minutes — AI system vs. FCFS baseline.

**Success criterion:**
- AI system: 0 overload minutes, satisfaction rate ≥ 75%
- FCFS baseline: expected ≥ 20 overload minutes (to be documented)

---

#### Scenario 3 — Temporary Grid Capacity Reduction (Simulated Outage)

**Description:** Midway through the simulation, transformer capacity is reduced by 40% for 30 minutes (simulating a partial outage, equipment fault, or demand response signal from the utility).

**What this tests:** Graceful degradation and real-time re-optimization when constraints tighten mid-session.

**Evaluation focus:**
- Does the optimizer re-allocate power correctly within the new limit?
- Are priority vehicles (high SoC deficit, early departure) protected?
- How many vehicles lose energy compared to normal operation?

**Success criterion:**
- No transformer overload during the constrained period
- High-priority vehicles (predicted departure within 1 hour) receive ≥ 80% of their needed energy

---

#### Scenario 4 — High EV Penetration (Stress Test)

**Description:** Scale the number of simultaneous vehicles to 150% of the typical observed maximum (achieved by compressing the session timeline or duplicating arrivals). This simulates future growth in EV adoption at the site.

**What this tests:** Whether the system degrades gracefully as load increases. The FCFS baseline will produce hard overloads; the AI system should maintain grid safety, accepting lower satisfaction rates as the necessary trade-off.

**Key insight to communicate:** The AI system does not violate grid constraints even when demand exceeds available capacity — it simply allocates less to each vehicle. The FCFS system either overloads the grid or arbitrarily cuts off vehicles.

---

### 8.4 Summary Evaluation Metrics Table

| Metric | Definition | Target (AI System) | FCFS Baseline (expected) |
|--------|-----------|-------------------|--------------------------|
| **Transformer overload minutes/day** | Minutes per simulated day where aggregate load exceeds rated capacity | 0 | 5–30 (scenario-dependent) |
| **Peak grid load (kW)** | Maximum instantaneous aggregate load | ≤ 90% of P_max | ≥ 100% of P_max (Scenario 2+) |
| **Charging deadline satisfaction rate (%)** | % of sessions where ≥ 90% of requested energy is delivered by departure | ≥ 75% (Scenario 2) | 50–65% (Scenario 2) |
| **Average energy delivery rate (%)** | Mean fraction of requested energy delivered across all sessions | ≥ 85% (Scenario 1) | ≥ 85% (Scenario 1, similar) |
| **Worst-case vehicle energy deficit (kWh)** | Maximum energy shortfall across all sessions in a scenario | Minimized by optimizer | Not controlled |
| **Electricity cost ($/day)** | If time-of-use pricing is available: total energy cost under the schedule | Lower than FCFS | Baseline reference |
| **Re-optimization response time (seconds)** | Time from constraint change to new schedule being committed | ≤ 5 seconds | N/A |

---

### 8.5 Reproducibility and Fairness of Comparison

To ensure the comparison between the AI system and the FCFS baseline is fair:

- Both systems operate on **identical input data** (same session arrivals, same transformer capacity, same charger hardware model)
- Both systems are evaluated on **the same four scenarios**
- The FCFS baseline is implemented faithfully: it does not benefit from any forecast or optimization; it simply grants maximum power to each vehicle as it connects, with proportional reduction only when the aggregate limit is reached
- All random seeds for synthetic data generation are fixed and documented

---

## 9. Experimental Design

### 9.1 Evaluation Environment

All scenarios are run in a **replay simulation environment**:
- Historical sessions from ACN-Data are replayed in simulated time (fast-forward)
- The ML models provide forecasts based on available historical context at each simulated time step (no look-ahead)
- The optimizer runs at each simulated time step with a 15-minute scheduling horizon
- The grid simulator runs after each scheduling decision

### 9.2 Experimental Matrix

| Scenario | AI System | FCFS Baseline | Greedy Heuristic Baseline |
|----------|-----------|---------------|--------------------------|
| Scenario 1 (Normal) | ✓ | ✓ | ✓ |
| Scenario 2 (Peak) | ✓ | ✓ | ✓ |
| Scenario 3 (Outage) | ✓ | ✓ | ✗ |
| Scenario 4 (Stress) | ✓ | ✓ | ✓ |

Results are presented as tables and time-series plots for each scenario, showing the evolution of grid load, satisfaction rate, and overload events over the simulated day.

### 9.3 Ablation Studies

To isolate the contribution of each AI component:

| Ablation | What is disabled | Question answered |
|---------|-----------------|------------------|
| No demand forecast | Optimizer uses only currently connected vehicles | How much does forecasting help? |
| No departure prediction | Optimizer assumes fixed 4-hour stay for all vehicles | How much does departure prediction help? |
| No grid simulation | Schedule is applied without validation | How often would unsafe schedules be issued? |

Each ablation is run on Scenario 2 (the stress case where differences are most visible).

---

## 10. Live Demonstration Plan

> This section describes exactly what professors will see during the final presentation, in what order, and what each step demonstrates. The goal is to provide interactive, visual evidence that the system works as designed.

### 10.1 Setup Before the Presentation

- The three Docker containers are running on the cloud VM (confirmed live, not recorded)
- The dashboard is accessible via a public URL on a projected screen
- A replay session dataset (a selected "interesting" day from ACN-Data — a peak day with a simulated outage) is loaded and ready to run
- Both the AI system and the FCFS baseline are configured in the dashboard so they can be switched in real time

### 10.2 Demonstration Script

#### Step 1 — System Architecture Walk-Through (3 minutes)

Show the deployment diagram on screen. Point to the three live containers:
- Open a browser tab showing the public dashboard (Container 1)
- If possible, show the container health status from the cloud console (demonstrating that Container 2 and 3 are running but have no public ports open)

**Talking point:** "The optimizer and ML models are internal services. The only entry point to the system is this dashboard and API. This is how production AI systems are structured for security and maintainability."

---

#### Step 2 — Baseline vs. AI on Normal Day (4 minutes)

- Run Scenario 1 (normal demand) with the FCFS baseline; show grid load evolution on the dashboard
- Run Scenario 1 with the AI system; show the same chart
- Both should perform similarly well on a normal day — this builds credibility ("we are not cherry-picking")

**Expected result:** Both systems achieve ≥ 85% satisfaction, no overload. The AI system's load curve is visibly smoother.

**Talking point:** "On a typical day, both systems are fine. The value of AI becomes visible under stress."

---

#### Step 3 — Peak Demand Event (5 minutes)

- Switch to Scenario 2 (peak arrival event)
- Run FCFS baseline live: the dashboard's transformer load gauge turns red as the load exceeds capacity; overload minutes counter increments in real time
- Reset; run AI system: the load gauge stays in the green or amber zone; the optimizer spreads load across time slots

**Key visual:** Side-by-side bar chart comparing overload minutes and satisfaction rates. This is the central result slide.

**Interaction for professors:** Adjust the transformer capacity limit slider in the dashboard from 100% to 80% (simulating a demand response signal). Show that the AI system re-optimizes immediately and the gauge adjusts, while explaining what would happen with FCFS (it would have no way to respond).

---

#### Step 4 — Live Outage Event (3 minutes)

- During the ongoing Scenario 2 replay, click the "Simulate Grid Event" button (which reduces transformer capacity by 40% for 5 simulated minutes)
- The dashboard shows:
  - A notification: "Grid capacity constraint updated"
  - The optimizer's response: power is redistributed within seconds
  - The priority queue: vehicles with near-term departures retain full allocation; others are throttled

**Talking point:** "This demonstrates real-time constraint handling. A utility signal arrives, the system re-plans within seconds, and no overload occurs."

---

#### Step 5 — ML Component Walkthrough (3 minutes)

- Show the ML Forecasting tab of the dashboard: a live rolling plot of predicted vs. actual EV arrivals over the replay timeline
- Show the departure time prediction accuracy panel: scatter plot of predicted vs. actual stay duration for sessions that have already concluded in the replay

**Talking point:** "These models are trained offline on real ACN-Data sessions. During operation, they provide the optimizer with a 30-minute lookahead — which is why the system can pre-emptively smooth demand rather than react after the fact."

---

#### Step 6 — API Demonstration (2 minutes)

- Open a terminal or API testing tool (e.g., the API docs page via `/docs` if using FastAPI) and show a raw call to the scheduling endpoint
- Show the JSON response containing the per-charger power allocation plan and the grid validation result

**Talking point:** "Any charger hardware or SCADA system can consume this API. We expose only one endpoint publicly. The ML and optimizer are invisible to external callers."

---

#### Step 7 — Results Summary (3 minutes)

Present the pre-computed results table (Section 8.4) comparing AI vs. FCFS across all four scenarios. Highlight:

1. The AI system achieves **zero transformer overload** in all scenarios
2. Satisfaction rates are **15–25 percentage points higher** than FCFS under peak conditions
3. ML departure prediction reduces energy shortfall compared to fixed-duration assumption

---

### 10.3 Contingency Plan

In case of connectivity issues on presentation day:

| Issue | Mitigation |
|-------|-----------|
| Cloud VM unreachable | All scenarios are pre-recorded as 2-minute screen captures uploaded to a shared drive |
| Slow API responses | Replay can be run locally using Docker Compose on the presentation laptop |
| MATLAB Simulink license unavailable | Python-based grid simulation is functionally equivalent for demo purposes |
| Cold-start ML model latency | Models are pre-loaded into Container 2 via a warm-up request sent 30 minutes before the presentation |

---

## 11. Risks and Limitations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| ACN-Data does not represent the target deployment site | ML models may not generalize | Evaluate on multiple splits; report generalization bounds |
| Optimization may be too slow for real-time use | Schedule latency > 5 seconds | Pre-compute schedules for the next T steps during idle time |
| Grid simulation fidelity is insufficient | Validated schedules may still cause real-world problems | Use conservative safety margins (e.g., 85% of rated capacity as effective limit) |
| Departure time predictions are inaccurate for new users | Priority scheduling based on wrong departure time | Use conservative (later) departure estimates; add a buffer to ensure enough energy is reserved |
| Cloud deployment costs | Budget overrun for long-running demo environments | Use spot/preemptible instances; shut down between sessions |

---

## Appendix A — Glossary

| Term | Definition |
|------|-----------|
| **SoC** | State of Charge — the remaining battery capacity expressed as a percentage of total capacity |
| **FCFS** | First-Come, First-Served — the baseline policy of granting maximum charging power immediately upon connection |
| **p.u.** | Per unit — a normalized unit system used in power engineering where rated values equal 1.0 |
| **MPC** | Model Predictive Control — a control strategy that repeatedly solves an optimization problem over a receding future horizon |
| **LP** | Linear Programming — optimization over linear objectives and constraints |
| **MIP** | Mixed-Integer Programming — LP with some decision variables restricted to integers |
| **Transformer thermal limit** | The maximum continuous power (kVA or kW) the transformer can carry without overheating |

---

## Appendix B — References and Related Work

1. **ACN-Data**: Lee, Z.J. et al. "ACN-Data: Analysis and Applications of an Open EV Charging Dataset." ACM e-Energy, 2019.
2. **Adaptive Charging Network**: Caltech EV research group, https://ev.caltech.edu
3. **EV charging optimization survey**: Tan, K.M. et al. "Integration of Electric Vehicles in Smart Grid: A Review on Vehicle to Grid Technologies and Optimization Techniques." Renewable and Sustainable Energy Reviews, 2016.
4. **PyPSA**: Brown, T. et al. "PyPSA: Python for Power System Analysis." Journal of Open Research Software, 2018.
5. **Model Predictive Control for EV charging**: Ma, Z. et al. "Decentralized Charging Control of Large Populations of Plug-in Electric Vehicles." IEEE Transactions on Control Systems Technology, 2013.

---

*Document prepared for academic course project — AI in Industry / AI Systems*
*This document describes system design and validation methodology only. No production deployment is implied.*
