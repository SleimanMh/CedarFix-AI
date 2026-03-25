"""
LP-based power allocation scheduler.

Solves the charging optimization problem from SYSTEM_DESIGN.md Section 5:

  maximize  Σ_i Σ_k  w_i · x_{i,k} · Δt
  subject to:
      Σ_i x_{i,k}  ≤  P_max - base_load_k - reserved_k   for each slot k
      0 ≤ x_{i,k}  ≤  p_i^max                             for each (i,k)
      Σ_k x_{i,k} · Δt  ≤  e_i                            for each vehicle i
      x_{i,k} = 0  if vehicle i is not present in slot k

When ML predictions are provided, reserved_k is computed from predicted
future EV arrivals — the optimizer saves capacity for vehicles that haven't
arrived yet but are expected by the ML model.

Uses scipy.optimize.linprog (interior-point LP solver).
"""

import numpy as np
from scipy.optimize import linprog

from app.schemas import EVVehicle, EVSchedule, FutureArrival


def _build_reservation_profile(
    future_arrivals: list[FutureArrival],
    num_slots: int,
    slot_duration_hours: float,
) -> np.ndarray:
    """
    Convert ML-predicted future arrivals into a per-slot capacity reservation (kW).

    For each predicted arrival at slot s with N predicted EVs at avg_charge_kw:
    - Reserve N * avg_charge_kw in slots [s, s + slots_needed)
    - slots_needed estimated from predicted_kwh / (count * charge_rate * slot_hours)
    """
    reserved = np.zeros(num_slots)

    for fa in future_arrivals:
        if fa.predicted_count < 0.1 or fa.slot >= num_slots:
            continue

        power_kw = fa.predicted_count * fa.avg_charge_kw
        # Estimate how many slots these future EVs will need
        if fa.predicted_count > 0 and fa.avg_charge_kw > 0:
            energy_per_ev = fa.predicted_kwh / max(1, fa.predicted_count)
            slots_needed = max(1, int(np.ceil(
                energy_per_ev / (fa.avg_charge_kw * slot_duration_hours)
            )))
        else:
            slots_needed = 4  # default: 1 hour

        start = fa.slot
        end = min(num_slots, start + slots_needed)
        reserved[start:end] += power_kw

    return reserved


def optimize_schedule(
    vehicles: list[EVVehicle],
    num_slots: int,
    slot_duration_hours: float,
    transformer_capacity_kw: float,
    base_load_per_slot_kw: list[float],
    predicted_future_arrivals: list[FutureArrival] | None = None,
) -> list[EVSchedule]:
    """
    Solve the LP to maximize total energy delivered across all vehicles,
    weighted by urgency (vehicles with tighter deadlines get priority).
    """
    n_vehicles = len(vehicles)
    n_vars = n_vehicles * num_slots  # x_{i,k} for each vehicle × slot

    # Build presence matrix: vehicle i is present in slot k?
    presence = np.zeros((n_vehicles, num_slots), dtype=bool)
    for i, v in enumerate(vehicles):
        start = max(0, v.arrival_slot)
        end = min(num_slots, v.departure_slot)
        presence[i, start:end] = True

    # ── Objective: maximize Σ w_i · x_{i,k} · Δt ──
    # Mild urgency bonus gives priority to time-constrained vehicles
    # without creating extreme distribution bias.
    weights = np.zeros(n_vars)
    for i, v in enumerate(vehicles):
        available_slots = max(1, presence[i].sum())
        urgency = v.energy_needed_kwh / (available_slots * slot_duration_hours * v.max_charge_kw + 1e-6)
        w = 1.0 + 0.5 * urgency
        for k in range(num_slots):
            weights[i * num_slots + k] = w * slot_duration_hours if presence[i, k] else 0

    # linprog minimizes, so negate for maximization
    c = -weights

    # ── ML Reservation: capacity reserved for predicted future arrivals ──
    # Reserve a FRACTION of predicted demand (not 100%) to balance current vs future.
    # Also cap reservation so current vehicles always get at least 50% of available capacity.
    RESERVATION_FRACTION = 0.10  # reserve 10% of predicted demand
    if predicted_future_arrivals:
        reserved = _build_reservation_profile(
            predicted_future_arrivals, num_slots, slot_duration_hours
        )
        reserved *= RESERVATION_FRACTION
        # Cap: never reserve more than 50% of available capacity per slot
        for k in range(num_slots):
            headroom = transformer_capacity_kw - base_load_per_slot_kw[k]
            reserved[k] = min(reserved[k], 0.5 * max(0, headroom))
    else:
        reserved = np.zeros(num_slots)

    # ── Constraints ──
    A_ub_rows = []
    b_ub_vals = []

    # 1) Per-slot capacity: Σ_i x_{i,k} ≤ P_available_k - reserved_k
    for k in range(num_slots):
        row = np.zeros(n_vars)
        for i in range(n_vehicles):
            if presence[i, k]:
                row[i * num_slots + k] = 1.0
        A_ub_rows.append(row)
        available = transformer_capacity_kw - base_load_per_slot_kw[k] - reserved[k]
        b_ub_vals.append(max(0, available))

    # 2) Per-vehicle energy cap: Σ_k x_{i,k} · Δt ≤ e_i
    for i, v in enumerate(vehicles):
        row = np.zeros(n_vars)
        for k in range(num_slots):
            if presence[i, k]:
                row[i * num_slots + k] = slot_duration_hours
        A_ub_rows.append(row)
        b_ub_vals.append(v.energy_needed_kwh)

    A_ub = np.array(A_ub_rows)
    b_ub = np.array(b_ub_vals)

    # ── Bounds: 0 ≤ x_{i,k} ≤ p_i^max (or 0 if not present) ──
    bounds = []
    for i, v in enumerate(vehicles):
        for k in range(num_slots):
            if presence[i, k]:
                bounds.append((0, v.max_charge_kw))
            else:
                bounds.append((0, 0))

    # ── Solve ──
    # Use interior-point (barrier) method to get the analytic centre of optimal
    # solutions.  Simplex returns a vertex which can be highly unequal when the
    # LP has many equivalent optima (degenerate).  Interior-point produces a
    # balanced allocation that promotes proportional fairness.
    result = linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds, method="highs-ipm")

    if not result.success:
        # Fallback: return zero allocation (optimizer couldn't find solution)
        return _zero_schedules(vehicles, num_slots)

    x = result.x.reshape(n_vehicles, num_slots)

    # ── Build response ──
    schedules = []
    for i, v in enumerate(vehicles):
        power_per_slot = x[i].tolist()
        energy = float(np.sum(x[i]) * slot_duration_hours)
        sat = min(100.0, (energy / v.energy_needed_kwh) * 100) if v.energy_needed_kwh > 0 else 100.0
        schedules.append(EVSchedule(
            ev_id=v.ev_id,
            power_per_slot_kw=power_per_slot,
            energy_delivered_kwh=round(energy, 3),
            energy_needed_kwh=v.energy_needed_kwh,
            satisfaction_pct=round(sat, 1),
        ))

    return schedules


def _zero_schedules(vehicles: list[EVVehicle], num_slots: int) -> list[EVSchedule]:
    return [
        EVSchedule(
            ev_id=v.ev_id,
            power_per_slot_kw=[0.0] * num_slots,
            energy_delivered_kwh=0.0,
            energy_needed_kwh=v.energy_needed_kwh,
            satisfaction_pct=0.0,
        )
        for v in vehicles
    ]
