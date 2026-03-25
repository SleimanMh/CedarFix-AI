"""
Grid Validation — Python-based simplified power flow.

Checks whether a proposed charging schedule is safe:
- Transformer loading (%)
- Bus voltage estimation (simplified radial feeder model)
- Line current estimation

This module is designed to be replaced with OpenDSS when your friend's
circuit model is ready. The interface stays the same.

To integrate OpenDSS later:
    pip install opendssdirect.py
    Replace _simplified_power_flow() with OpenDSS calls.
"""

import math

from app.schemas import GridValidationRequest, GridValidationResponse


def validate_grid(request: GridValidationRequest) -> GridValidationResponse:
    """
    Run simplified power flow analysis on the proposed load profile.
    """
    warnings = []
    transformer_kva = request.transformer_kva
    transformer_kw = transformer_kva * 0.95  # assuming 0.95 power factor
    num_slots = len(request.total_load_per_slot_kw)

    # ── Transformer loading ──
    loading_per_slot = [
        (load / transformer_kw) * 100
        for load in request.total_load_per_slot_kw
    ]
    max_loading = max(loading_per_slot) if loading_per_slot else 0

    overload_count = sum(1 for l in loading_per_slot if l > 100)
    overload_minutes = overload_count * 15  # each slot = 15 min

    if max_loading > 80:
        warnings.append(f"Transformer loading reaches {max_loading:.1f}% (warning threshold: 80%)")
    if max_loading > 100:
        warnings.append(f"OVERLOAD: Transformer loading exceeds 100% in {overload_count} slots")

    # ── Simplified voltage drop estimation ──
    # Model: radial feeder with uniform impedance
    # V_drop ≈ (P × R + Q × X) / V_nominal
    # For a campus grid: R ≈ 0.05 Ω/km, X ≈ 0.04 Ω/km, avg feeder length ≈ 0.5 km
    # V_nominal = 480 V (three-phase secondary)
    v_nominal = 480  # V
    r_feeder = 0.05 * 0.5  # Ω (R × length)
    x_feeder = 0.04 * 0.5  # Ω
    pf = 0.95

    max_load_kw = max(request.total_load_per_slot_kw) if request.total_load_per_slot_kw else 0
    max_load_w = max_load_kw * 1000
    max_current = max_load_w / (math.sqrt(3) * v_nominal) if v_nominal > 0 else 0

    # Voltage drop at worst case
    v_drop = max_current * (r_feeder * pf + x_feeder * math.sqrt(1 - pf**2))
    min_voltage_pu = max(0.0, (v_nominal - v_drop) / v_nominal)

    if min_voltage_pu < 0.95:
        warnings.append(f"Voltage drops to {min_voltage_pu:.4f} p.u. (minimum: 0.95 p.u.)")

    # ── Line current ──
    # Thermal limit for typical campus feeder: ~600 A
    thermal_limit_a = 600
    if max_current > thermal_limit_a:
        warnings.append(f"Line current {max_current:.1f} A exceeds thermal limit {thermal_limit_a} A")

    feasible = max_loading <= 100 and min_voltage_pu >= 0.95 and max_current <= thermal_limit_a

    return GridValidationResponse(
        feasible=feasible,
        max_transformer_loading_pct=round(max_loading, 2),
        min_bus_voltage_pu=round(min_voltage_pu, 4),
        max_line_current_a=round(max_current, 2),
        overload_minutes=overload_minutes,
        warnings=warnings,
    )


# ─── OpenDSS Integration Point ──────────────────────────────────────────
# When your friend's .dss circuit file is ready, replace the function above
# with something like:
#
# import opendssdirect as dss
#
# def validate_grid_opendss(circuit_file: str, loads_per_slot: list[float]) -> GridValidationResponse:
#     dss.run_command(f"Redirect {circuit_file}")
#     for slot, load_kw in enumerate(loads_per_slot):
#         # Set EV loads for this time step
#         dss.run_command(f"Edit Load.EVChargers kW={load_kw}")
#         dss.Solution.Solve()
#         # Extract results...
#         voltages = dss.Circuit.AllBusVmagPu()
#         currents = dss.CktElement.Currents()
#     ...
