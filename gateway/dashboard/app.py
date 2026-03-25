"""
EV Charging Optimization Dashboard — Streamlit
3-way comparison: AI+ML vs AI-only vs FCFS, with ML monitoring panel.
"""

import json

import plotly.graph_objects as go
import requests
import streamlit as st

GATEWAY_URL = "http://localhost:8000"

st.set_page_config(page_title="EV Charging Optimizer", layout="wide")
st.title("EV Charging Optimization Dashboard")

# ── Sidebar: System Health ───────────────────────────────────────────────
with st.sidebar:
    st.header("System Status")
    try:
        health = requests.get(f"{GATEWAY_URL}/health", timeout=3).json()
        st.success("Gateway: UP")
        for svc, status in health.get("services", {}).items():
            if status == "up":
                st.success(f"{svc}: UP")
            else:
                st.warning(f"{svc}: DOWN")
    except Exception:
        st.error("Gateway: UNREACHABLE")

    st.divider()
    st.header("Grid Parameters")
    transformer_kw = st.number_input("Transformer Capacity (kW)", 50, 2000, 150)
    building_load_kw = st.number_input("Building Base Load (kW)", 10, 1000, 60)
    duration_hours = st.slider("Simulation Duration (hours)", 1, 48, 8)
    time_step = st.selectbox("Time Step (min)", [15, 30, 60], index=0)
    compare_baseline = st.checkbox("Compare with FCFS Baseline", value=True)

    st.divider()
    st.header("Electric Vehicles")
    num_evs = st.slider("Number of EVs", 1, 50, 10)

# ── EV Configuration ────────────────────────────────────────────────────
st.subheader("Vehicle Configuration")
st.caption("Vehicles WITHOUT a departure time will trigger ML departure prediction. "
           "The no-ML baseline uses a fixed 4-hour assumption instead.")
evs = []
cols = st.columns(min(num_evs, 5))
for i in range(num_evs):
    col = cols[i % len(cols)]
    with col:
        with st.expander(f"EV {i+1}", expanded=(i < 3)):
            battery = st.slider("Current SoC %", 0, 100, 20, key=f"bat_{i}")
            target = st.slider("Target SoC %", battery, 100, 90, key=f"tar_{i}")
            max_power = st.selectbox("Max Power (kW)", [3.6, 7.2, 11, 22, 50], index=1, key=f"pow_{i}")
            capacity = st.selectbox("Battery (kWh)", [40, 50, 60, 75, 100], index=2, key=f"cap_{i}")
            evs.append({
                "ev_id": f"EV-{i+1:03d}",
                "battery_pct": battery,
                "target_pct": target,
                "max_charge_kw": max_power,
                "battery_capacity_kwh": capacity,
            })

# ── Run Simulation ──────────────────────────────────────────────────────
if st.button("Run Simulation", type="primary", use_container_width=True):
    payload = {
        "vehicles": evs,
        "transformer_capacity_kw": transformer_kw,
        "building_base_load_kw": building_load_kw,
        "simulation_duration_hours": duration_hours,
        "time_step_minutes": time_step,
        "compare_baseline": compare_baseline,
    }

    with st.spinner("Running simulation..."):
        try:
            resp = requests.post(f"{GATEWAY_URL}/api/v1/simulation/run", json=payload, timeout=120)
            resp.raise_for_status()
            st.session_state["result"] = resp.json()
        except requests.ConnectionError:
            st.error("Cannot connect to gateway. Is the system running?")
        except Exception as e:
            st.error(f"Simulation failed: {e}")

# ── Display Results ─────────────────────────────────────────────────────
if "result" in st.session_state:
    result = st.session_state["result"]
    ai = result["ai_result"]
    no_ml = result.get("no_ml_result")
    baseline = result.get("baseline_result")
    ml_met = result.get("ml_metrics")

    # ══════════════════════════════════════════════════════════════════════
    #  ML CONTRIBUTION PANEL
    # ══════════════════════════════════════════════════════════════════════
    if ml_met:
        st.header("🤖 ML Model Contribution")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric("Departures Predicted by ML",
                      ml_met["departure_predictions_used"],
                      help="Vehicles whose departure time was predicted by the ML model")
        with mcol2:
            avg_stay = ml_met.get("avg_predicted_stay_min")
            st.metric("Avg ML-Predicted Stay",
                      f"{avg_stay:.0f} min" if avg_stay else "N/A",
                      delta=f"vs {ml_met['default_stay_min']:.0f} min fixed" if avg_stay else None,
                      help="ML-predicted stay vs the fixed 4h assumption used by no-ML baseline")
        with mcol3:
            st.metric("Demand Forecast Windows",
                      ml_met["demand_forecast_windows"],
                      help="Future time windows where ML predicted incoming EV demand")
        with mcol4:
            st.metric("Capacity Reserved by ML",
                      f"{ml_met['capacity_reserved_kwh']:.1f} kWh",
                      help="Energy capacity proactively reserved for predicted future arrivals")

        if ml_met["departure_predictions_used"] > 0 and no_ml:
            improvement = ai["overall_satisfaction_pct"] - no_ml["overall_satisfaction_pct"]
            st.info(f"**ML Impact**: Departure prediction + demand forecasting "
                    f"{'improved' if improvement > 0 else 'changed'} satisfaction by "
                    f"**{improvement:+.1f}%** compared to the same optimizer without ML.")

    # ══════════════════════════════════════════════════════════════════════
    #  KEY PERFORMANCE INDICATORS — 3-way comparison
    # ══════════════════════════════════════════════════════════════════════
    st.header("Key Performance Indicators")

    strategies = [("AI + ML", ai, "blue")]
    if no_ml:
        strategies.append(("AI (no ML)", no_ml, "orange"))
    if baseline:
        strategies.append(("FCFS", baseline, "red"))

    kpi_cols = st.columns(len(strategies))
    for idx, (name, strat, color) in enumerate(strategies):
        with kpi_cols[idx]:
            st.subheader(name)
            delta_vs_fcfs = None
            if baseline and strat != baseline:
                delta_vs_fcfs = strat["overall_satisfaction_pct"] - baseline["overall_satisfaction_pct"]

            st.metric("Satisfaction",
                      f"{strat['overall_satisfaction_pct']:.1f}%",
                      delta=f"{delta_vs_fcfs:+.1f}% vs FCFS" if delta_vs_fcfs is not None else None)
            st.metric("Peak Load", f"{strat['peak_load_kw']:.1f} kW")
            st.metric("Energy Delivered", f"{strat['total_energy_delivered_kwh']:.1f} kWh")
            st.metric("Overload Slots", f"{strat['overload_slots']}")

    # ── Comparison bar chart ──
    st.subheader("Satisfaction Comparison")
    fig_bar = go.Figure()
    colors = {"AI + ML": "#1f77b4", "AI (no ML)": "#ff7f0e", "FCFS": "#d62728"}
    for name, strat, color in strategies:
        fig_bar.add_trace(go.Bar(
            x=[name], y=[strat["overall_satisfaction_pct"]],
            name=name, marker_color=colors.get(name, color),
            text=[f"{strat['overall_satisfaction_pct']:.1f}%"],
            textposition="auto",
        ))
    fig_bar.update_layout(yaxis_title="Satisfaction (%)", height=350, showlegend=False,
                          yaxis=dict(range=[0, 105]))
    st.plotly_chart(fig_bar, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    #  LOAD PROFILE CHART — all strategies
    # ══════════════════════════════════════════════════════════════════════
    st.header("Load Profile Comparison")
    fig = go.Figure()

    ai_ts = ai["time_series"]
    times = [p["time_minutes"] / 60 for p in ai_ts]

    fig.add_trace(go.Scatter(
        x=times, y=[p["total_load_kw"] for p in ai_ts],
        name="AI+ML Total Load", line=dict(color="#1f77b4", width=2),
    ))
    fig.add_trace(go.Scatter(
        x=times, y=[p["building_load_kw"] for p in ai_ts],
        name="Building Load", line=dict(color="gray", dash="dot"),
    ))

    if no_ml:
        no_ml_ts = no_ml["time_series"]
        fig.add_trace(go.Scatter(
            x=times, y=[p["total_load_kw"] for p in no_ml_ts],
            name="AI (no ML) Total Load", line=dict(color="#ff7f0e", width=2, dash="dashdot"),
        ))

    if baseline:
        bl_ts = baseline["time_series"]
        fig.add_trace(go.Scatter(
            x=times, y=[p["total_load_kw"] for p in bl_ts],
            name="FCFS Total Load", line=dict(color="#d62728", width=2, dash="dash"),
        ))

    fig.add_hline(y=transformer_kw, line_dash="dash", line_color="darkred",
                  annotation_text=f"Transformer Limit ({transformer_kw} kW)")

    fig.update_layout(
        xaxis_title="Time (hours)", yaxis_title="Load (kW)", height=500,
        legend=dict(yanchor="top", y=0.99, xanchor="left", x=0.01),
    )
    st.plotly_chart(fig, use_container_width=True)

    # ── Transformer Utilization ──
    st.header("Transformer Utilization")
    fig2 = go.Figure()
    fig2.add_trace(go.Scatter(
        x=times, y=[p["transformer_utilization_pct"] for p in ai_ts],
        name="AI+ML", fill="tozeroy", line=dict(color="#1f77b4"),
    ))
    if no_ml:
        fig2.add_trace(go.Scatter(
            x=times, y=[p["transformer_utilization_pct"] for p in no_ml_ts],
            name="AI (no ML)", line=dict(color="#ff7f0e", dash="dashdot"),
        ))
    if baseline:
        fig2.add_trace(go.Scatter(
            x=times, y=[p["transformer_utilization_pct"] for p in bl_ts],
            name="FCFS", line=dict(color="#d62728", dash="dash"),
        ))
    fig2.add_hline(y=100, line_dash="dash", line_color="red", annotation_text="100% Limit")
    fig2.add_hline(y=80, line_dash="dot", line_color="orange", annotation_text="80% Warning")
    fig2.update_layout(xaxis_title="Time (hours)", yaxis_title="Utilization (%)", height=400)
    st.plotly_chart(fig2, use_container_width=True)

    # ══════════════════════════════════════════════════════════════════════
    #  PER-VEHICLE RESULTS — 3-column comparison
    # ══════════════════════════════════════════════════════════════════════
    st.header("Per-Vehicle Results")
    ev_cols = st.columns(len(strategies))

    for idx, (name, strat, color) in enumerate(strategies):
        with ev_cols[idx]:
            st.subheader(name)
            for ev in strat["ev_results"]:
                pct = ev["satisfaction_pct"]
                clr = "green" if pct >= 90 else "orange" if pct >= 50 else "red"
                st.markdown(f"**{ev['ev_id']}**: {ev['energy_delivered_kwh']:.1f}/{ev['energy_needed_kwh']:.1f} kWh "
                            f"(:{clr}[{pct:.0f}%])")

    # ══════════════════════════════════════════════════════════════════════
    #  ML MODEL MONITORING PANEL
    # ══════════════════════════════════════════════════════════════════════
    st.header("🔍 ML Model Monitoring")

    try:
        ml_status = requests.get(f"{GATEWAY_URL}/api/v1/ml/metrics", timeout=5).json()

        mcol1, mcol2 = st.columns(2)

        with mcol1:
            st.subheader("Model 1: Demand Forecasting")
            if "evaluation" in ml_status:
                ev_metrics = ml_status["evaluation"]
                st.metric("Arrival Count MAE", f"{ev_metrics.get('demand_arrival_count_mae', 0):.3f}")
                st.metric("Arrival Count RMSE", f"{ev_metrics.get('demand_arrival_count_rmse', 0):.3f}")
                st.metric("Total kWh MAE", f"{ev_metrics.get('demand_total_kwh_mae', 0):.2f}")
                st.metric("Total kWh RMSE", f"{ev_metrics.get('demand_total_kwh_rmse', 0):.2f}")

            if "models" in ml_status and "demand_forecast" in ml_status["models"]:
                m = ml_status["models"]["demand_forecast"]
                st.caption(f"**Type**: {m['type']}")
                st.caption(f"**Description**: {m['description']}")
                with st.expander("Input Features"):
                    for feat in m.get("input_features", []):
                        st.code(feat)

        with mcol2:
            st.subheader("Model 2: Departure Prediction")
            if "evaluation" in ml_status:
                st.metric("Stay Duration MAE", f"{ev_metrics.get('departure_mae_min', 0):.1f} min")
                st.metric("Stay Duration RMSE", f"{ev_metrics.get('departure_rmse_min', 0):.1f} min")
                st.metric("Within 15 min", f"{ev_metrics.get('departure_within_15min_pct', 0):.1f}%")
                st.metric("Within 30 min", f"{ev_metrics.get('departure_within_30min_pct', 0):.1f}%")

            if "models" in ml_status and "departure_prediction" in ml_status["models"]:
                m = ml_status["models"]["departure_prediction"]
                st.caption(f"**Type**: {m['type']}")
                st.caption(f"**Description**: {m['description']}")
                with st.expander("Input Features"):
                    for feat in m.get("input_features", []):
                        st.code(feat)

        if "evaluation" in ml_status and "acceptance_checks" in ml_status["evaluation"]:
            st.subheader("Acceptance Tests")
            checks = ml_status["evaluation"]["acceptance_checks"]
            for check, passed in checks.items():
                if passed:
                    st.success(f"✅ {check}")
                else:
                    st.warning(f"⚠️ {check}")

        st.caption(f"Model version: {ml_status.get('model_version', 'unknown')}")

    except Exception as e:
        st.warning(f"ML monitoring unavailable: {e}")

    # ── Grid Validation ──
    if ai.get("grid_validation"):
        st.header("Grid Validation")
        gv = ai["grid_validation"]
        st.json(gv)

    # ── Raw JSON ──
    with st.expander("Raw API Response"):
        st.json(result)
