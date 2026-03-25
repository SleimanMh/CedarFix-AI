"""
FCFS (First-Come, First-Served) baseline scheduler.

Represents unmanaged charging: each vehicle draws maximum power immediately
upon connection. When aggregate exceeds transformer limit, power is
proportionally curtailed across all active vehicles.

This is the baseline the AI system is compared against.
"""

import numpy as np

from app.schemas import EVVehicle, EVSchedule


def fcfs_schedule(
    vehicles: list[EVVehicle],
    num_slots: int,
    slot_duration_hours: float,
    transformer_capacity_kw: float,
    base_load_per_slot_kw: list[float],
) -> list[EVSchedule]:
    """
    FCFS baseline: each vehicle gets max power when present.
    If total exceeds capacity, proportionally curtail.
    """
    n_vehicles = len(vehicles)

    # Track remaining energy per vehicle
    remaining = np.array([v.energy_needed_kwh for v in vehicles])
    allocation = np.zeros((n_vehicles, num_slots))

    for k in range(num_slots):
        available_kw = max(0, transformer_capacity_kw - base_load_per_slot_kw[k])
        requested = np.zeros(n_vehicles)

        for i, v in enumerate(vehicles):
            if v.arrival_slot <= k < v.departure_slot and remaining[i] > 0:
                # Max power the vehicle can use (limited by remaining energy)
                max_power = min(v.max_charge_kw, remaining[i] / slot_duration_hours)
                requested[i] = max_power

        total_requested = requested.sum()

        if total_requested <= available_kw:
            # No curtailment needed
            allocation[:, k] = requested
        else:
            # Proportional curtailment
            if total_requested > 0:
                ratio = available_kw / total_requested
                allocation[:, k] = requested * ratio

        # Update remaining energy
        for i in range(n_vehicles):
            energy_step = allocation[i, k] * slot_duration_hours
            remaining[i] = max(0, remaining[i] - energy_step)

    # Build response
    schedules = []
    for i, v in enumerate(vehicles):
        energy = float(allocation[i].sum() * slot_duration_hours)
        sat = min(100.0, (energy / v.energy_needed_kwh) * 100) if v.energy_needed_kwh > 0 else 100.0
        schedules.append(EVSchedule(
            ev_id=v.ev_id,
            power_per_slot_kw=allocation[i].tolist(),
            energy_delivered_kwh=round(energy, 3),
            energy_needed_kwh=v.energy_needed_kwh,
            satisfaction_pct=round(sat, 1),
        ))

    return schedules
