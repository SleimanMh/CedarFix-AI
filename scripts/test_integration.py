"""
Integration tests — 3-way comparison: AI+ML vs AI-only vs FCFS
Vehicles DO NOT have planned_departure_time → ML departure prediction activates.
"""
import requests
import json
import sys
from datetime import datetime, timedelta, timezone

GATEWAY_URL = "http://127.0.0.1:8000"

# ── Health check ──
print("Checking service health...")
try:
    h = requests.get(f"{GATEWAY_URL}/health", timeout=5).json()
    print(f"  Gateway: {h['status']}")
    for svc, status in h["services"].items():
        print(f"  {svc}: {status}")
except Exception as e:
    print(f"  Gateway unreachable: {e}")
    sys.exit(1)

# Check ML monitoring
print("\nML Model Status:")
try:
    ml = requests.get(f"{GATEWAY_URL}/api/v1/ml/metrics", timeout=5).json()
    print(f"  Model version: {ml.get('model_version')}")
    print(f"  Demand model loaded: {ml.get('demand_model_loaded')}")
    print(f"  Departure model loaded: {ml.get('departure_model_loaded')}")
    if "evaluation" in ml:
        ev = ml["evaluation"]
        print(f"  Departure MAE: {ev.get('departure_mae_min', 'N/A'):.1f} min")
        print(f"  Demand Arrival MAE: {ev.get('demand_arrival_count_mae', 'N/A'):.3f}")
except Exception as e:
    print(f"  ML monitoring unavailable: {e}")


def print_results(label, d):
    print(f"\n{'='*72}")
    print(f"  {label}")
    print(f"{'='*72}")
    print(f"  Run ID: {d['run_id']}  |  Vehicles: {d['num_vehicles']}")

    ai = d["ai_result"]
    no_ml = d.get("no_ml_result")
    bl = d.get("baseline_result")

    # 3-way comparison table
    header = f"{'Metric':<30} {'AI+ML':>10} {'AI(noML)':>10} {'FCFS':>10} {'ML Δ':>8}"
    print(f"\n  {header}")
    print(f"  {'-'*68}")

    def row(name, ai_val, no_ml_val, bl_val, fmt=".1f", unit=""):
        ml_delta = ai_val - no_ml_val if no_ml_val is not None else 0
        sign = "+" if ml_delta > 0 else ""
        av = f"{ai_val:{fmt}}{unit}"
        nv = f"{no_ml_val:{fmt}}{unit}" if no_ml_val is not None else "N/A"
        bv = f"{bl_val:{fmt}}{unit}" if bl_val is not None else "N/A"
        dv = f"{sign}{ml_delta:{fmt}}{unit}"
        print(f"  {name:<30} {av:>10} {nv:>10} {bv:>10} {dv:>8}")

    no_ml_s = no_ml if no_ml else {}
    bl_s = bl if bl else {}

    row("Satisfaction (%)",
        ai["overall_satisfaction_pct"],
        no_ml_s.get("overall_satisfaction_pct"),
        bl_s.get("overall_satisfaction_pct"), ".1f", "%")
    row("Peak Load (kW)",
        ai["peak_load_kw"],
        no_ml_s.get("peak_load_kw"),
        bl_s.get("peak_load_kw"), ".1f", "")
    row("Energy Delivered (kWh)",
        ai["total_energy_delivered_kwh"],
        no_ml_s.get("total_energy_delivered_kwh"),
        bl_s.get("total_energy_delivered_kwh"), ".1f", "")
    row("Overload Slots",
        ai["overload_slots"],
        no_ml_s.get("overload_slots"),
        bl_s.get("overload_slots"), "d", "")

    # ML metrics
    ml_met = d.get("ml_metrics")
    if ml_met:
        print(f"\n  ML Contribution:")
        print(f"    Departure predictions used: {ml_met['departure_predictions_used']}")
        print(f"    Departure predictions skipped: {ml_met['departure_predictions_skipped']}")
        avg = ml_met.get('avg_predicted_stay_min')
        print(f"    Avg ML-predicted stay: {avg:.0f} min" if avg else "    Avg ML-predicted stay: N/A")
        print(f"    Default (no-ML) stay: {ml_met['default_stay_min']:.0f} min")
        print(f"    Demand forecast windows: {ml_met['demand_forecast_windows']}")
        print(f"    Capacity reserved: {ml_met['capacity_reserved_kwh']:.1f} kWh")

    # Grid validation
    gv = ai.get("grid_validation")
    if gv:
        print(f"\n  Grid: feasible={gv['feasible']}  "
              f"transformer={gv['max_transformer_loading_pct']:.1f}%  "
              f"voltage={gv['min_bus_voltage_pu']:.4f} p.u.")
        if gv.get("warnings"):
            for w in gv["warnings"]:
                print(f"  ⚠ {w}")


now = datetime.now(timezone.utc)

# ════════════════════════════════════════════════════════════════
#  SCENARIO 1: ML Departure Prediction — Heavy Contention
#   - 20 EVs, ALL arrive at once (t=0), NO planned_departure
#   - Tight: 100 kW transformer, 40 kW base → 60 kW for EVs
#   - 20 EVs × 7.2 kW = 144 kW demand vs 60 kW available
#   - LP must defer some charging → later slots vulnerable to truncation
#   - ML predicts ~3h stays, no-ML assumes 4h
#   - Truncation at 3h penalizes no-ML's deferred charging
# ════════════════════════════════════════════════════════════════
print("\n\n▶ SCENARIO 1: ML Departure Prediction (20 EVs, all arriving at once)")

vehicles_s1 = []
for i in range(20):
    vehicles_s1.append({
        "ev_id": f"EV-{i+1:03d}",
        "battery_pct": 15 + (i * 3) % 25,
        "target_pct": 85 + (i % 3) * 5,
        "max_charge_kw": 7.2,
        "battery_capacity_kwh": [50, 60, 75][i % 3],
        "arrival_time": now.isoformat(),  # ALL arrive at once
        # NO planned_departure_time → ML departure prediction kicks in!
    })

payload1 = {
    "vehicles": vehicles_s1,
    "transformer_capacity_kw": 100,
    "building_base_load_kw": 40,       # 60 kW for EVs
    "simulation_duration_hours": 8,
    "time_step_minutes": 15,
    "compare_baseline": True,
}

r1 = requests.post(f"{GATEWAY_URL}/api/v1/simulation/run", json=payload1, timeout=120)
if r1.status_code != 200:
    print(f"  ERROR: {r1.status_code} - {r1.text}")
    sys.exit(1)
print_results("SCENARIO 1: ML Departure Prediction — AI+ML should beat AI-only and FCFS", r1.json())


# ════════════════════════════════════════════════════════════════
#  SCENARIO 2: Heavy contention + ML
#   - 25 EVs, NO planned departures
#   - Very tight: 100 kW transformer, 40 kW base → 60 kW for EVs
#   - ML departure predictions determine each vehicle's window
#   - No-ML assumes 4h for all → inaccurate scheduling
#   - 6h simulation window
# ════════════════════════════════════════════════════════════════
print("\n\n▶ SCENARIO 2: Heavy contention (25 EVs, 100 kW transformer, no departures)")

vehicles_s2 = []
for i in range(25):
    arrival = now + timedelta(minutes=i * 8)
    vehicles_s2.append({
        "ev_id": f"HEAVY-{i+1:02d}",
        "battery_pct": 10 + (i * 5) % 35,
        "target_pct": 80 + (i % 4) * 5,
        "max_charge_kw": [7.2, 7.2, 11.0, 7.2, 22.0][i % 5],
        "battery_capacity_kwh": [50, 60, 60, 75, 40][i % 5],
        "arrival_time": arrival.isoformat(),
        # NO planned_departure_time
    })

payload2 = {
    "vehicles": vehicles_s2,
    "transformer_capacity_kw": 100,
    "building_base_load_kw": 40,
    "simulation_duration_hours": 6,
    "time_step_minutes": 15,
    "compare_baseline": True,
}

r2 = requests.post(f"{GATEWAY_URL}/api/v1/simulation/run", json=payload2, timeout=120)
if r2.status_code != 200:
    print(f"  ERROR: {r2.status_code} - {r2.text}")
    sys.exit(1)
print_results("SCENARIO 2: Heavy Contention + ML — ML departure prediction matters most", r2.json())


# ════════════════════════════════════════════════════════════════
#  SCENARIO 3: Mixed — some vehicles have departures, some don't
#   - 20 EVs: 8 with departures, 12 without (ML kicks in for 12)
#   - This shows the hybrid: ML helps even when partial info available
#   - 150 kW transformer, 70 kW base
# ════════════════════════════════════════════════════════════════
print("\n\n▶ SCENARIO 3: Mixed (8 known departures + 12 ML-predicted)")

vehicles_s3 = []

# 8 EVs WITH planned departures (urgent, 2h window)
for i in range(8):
    arrival = now + timedelta(minutes=i * 5)
    vehicles_s3.append({
        "ev_id": f"KNOWN-{i+1:02d}",
        "battery_pct": 20,
        "target_pct": 90,
        "max_charge_kw": 7.2,
        "battery_capacity_kwh": 60,
        "arrival_time": arrival.isoformat(),
        "planned_departure_time": (arrival + timedelta(hours=2)).isoformat(),
    })

# 12 EVs WITHOUT planned departures (ML predicts)
for i in range(12):
    arrival = now + timedelta(minutes=30 + i * 10)
    vehicles_s3.append({
        "ev_id": f"UNKNOWN-{i+1:02d}",
        "battery_pct": 25 + (i * 4) % 20,
        "target_pct": 85,
        "max_charge_kw": [7.2, 11.0][i % 2],
        "battery_capacity_kwh": [50, 60, 75][i % 3],
        "arrival_time": arrival.isoformat(),
        # NO planned_departure_time → ML predicts
    })

payload3 = {
    "vehicles": vehicles_s3,
    "transformer_capacity_kw": 150,
    "building_base_load_kw": 70,
    "simulation_duration_hours": 8,
    "time_step_minutes": 15,
    "compare_baseline": True,
}

r3 = requests.post(f"{GATEWAY_URL}/api/v1/simulation/run", json=payload3, timeout=120)
if r3.status_code != 200:
    print(f"  ERROR: {r3.status_code} - {r3.text}")
    sys.exit(1)

d3 = r3.json()
print_results("SCENARIO 3: Mixed — ML helps with unknown departures", d3)

# Show breakdown by known vs unknown departure
print("\n  Per-group satisfaction:")
for group, prefix in [("Known departures", "KNOWN"), ("ML-predicted departures", "UNKNOWN")]:
    for strategy_name, result_key in [("AI+ML", "ai_result"), ("AI(noML)", "no_ml_result"), ("FCFS", "baseline_result")]:
        strat = d3.get(result_key)
        if not strat:
            continue
        evs = [e for e in strat["ev_results"] if e["ev_id"].startswith(prefix)]
        if evs:
            avg_sat = sum(e["satisfaction_pct"] for e in evs) / len(evs)
            total_del = sum(e["energy_delivered_kwh"] for e in evs)
            total_need = sum(e["energy_needed_kwh"] for e in evs)
            print(f"    {group} [{strategy_name}]: {avg_sat:.1f}% avg satisfaction  "
                  f"({total_del:.1f}/{total_need:.1f} kWh)")


print("\n\n" + "="*72)
print("  SUMMARY")
print("="*72)

for scenario, resp in [("Scenario 1", r1), ("Scenario 2", r2), ("Scenario 3", r3)]:
    d = resp.json()
    ai_s = d["ai_result"]["overall_satisfaction_pct"]
    no_ml_s = d["no_ml_result"]["overall_satisfaction_pct"] if d.get("no_ml_result") else 0
    fcfs_s = d["baseline_result"]["overall_satisfaction_pct"] if d.get("baseline_result") else 0
    ml_delta = ai_s - no_ml_s
    fcfs_delta = ai_s - fcfs_s
    ml_pred = d.get("ml_metrics", {}).get("departure_predictions_used", 0)
    print(f"  {scenario}:  AI+ML={ai_s:.1f}%  AI(noML)={no_ml_s:.1f}%  FCFS={fcfs_s:.1f}%  "
          f"ML Δ={ml_delta:+.1f}%  FCFS Δ={fcfs_delta:+.1f}%  "
          f"(ML predicted {ml_pred} departures)")

print("\n✓ All scenarios completed!")
