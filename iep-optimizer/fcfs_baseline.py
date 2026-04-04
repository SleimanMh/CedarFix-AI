"""
FCFS (First-Come, First-Served) baseline scheduler.

Unmanaged charging: each EV draws maximum power immediately on connection.
When aggregate demand exceeds transformer headroom, power is proportionally
curtailed across all simultaneously requesting EVs.

This is the non-AI comparison baseline for the LP optimizer.
Returns KPIs only (no slot schedules) — the caller uses these purely for the
baseline_comparison block appended to /optimize and /baseline responses.
"""

import numpy as np

SLOT_DURATION_H = 0.25   # 15-minute slots
NUM_SLOTS = 96


def run_fcfs(
    rates: np.ndarray,       # (96,)    $/kWh  — tariff profile
    headroom: np.ndarray,    # (96,)    kW     — transformer headroom for EVs
    grid: np.ndarray,        # (96,)    0/1    — grid availability mask
    active: np.ndarray,      # (n, 96)  0/1    — session active windows
    max_rates: np.ndarray,   # (n,)     kW     — per-session charge rate cap
    kwh_needed: np.ndarray,  # (n,)     kWh    — energy required per session
) -> dict:
    """
    Run FCFS scheduling and return KPIs.

    Differences from LP optimizer:
      - Slots processed in time order (arrival first, not cheapest first)
      - No tariff awareness — charges whenever the EV is connected
      - No global optimisation — purely local, greedy per slot

    Returns
    -------
    dict with keys:
        total_cost_usd          : float
        transformer_peak_kw     : float
        sessions_fully_charged  : int
    """
    n = int(kwh_needed.shape[0])
    if n == 0:
        return {
            "total_cost_usd": 0.0,
            "transformer_peak_kw": 0.0,
            "sessions_fully_charged": 0,
        }

    x = np.zeros((n, NUM_SLOTS), dtype=float)
    remaining = kwh_needed.astype(float).copy()

    # ── Process slots in chronological order (FCFS — no cost awareness) ──────
    for t in range(NUM_SLOTS):
        if grid[t] == 0:          # grid outage — no charging possible
            continue
        slot_cap = float(headroom[t])
        if slot_cap <= 0:
            continue

        # Each active EV requests as much as it needs (up to max_rate)
        requested = np.zeros(n, dtype=float)
        for i in range(n):
            if active[i, t] == 0 or remaining[i] <= 0:
                continue
            # Cap to energy still needed to avoid over-charging
            max_deliverable_kw = min(
                float(max_rates[i]),
                remaining[i] / SLOT_DURATION_H,
            )
            requested[i] = max_deliverable_kw

        total_requested = float(requested.sum())
        if total_requested <= 0:
            continue

        if total_requested <= slot_cap:
            x[:, t] = requested
        else:
            # Proportional curtailment — fair among all requesting EVs
            ratio = slot_cap / total_requested
            x[:, t] = requested * ratio

        # Deduct delivered energy from each session's remaining need
        for i in range(n):
            remaining[i] = max(0.0, remaining[i] - x[i, t] * SLOT_DURATION_H)

    # ── KPIs ─────────────────────────────────────────────────────────────────
    total_cost_usd = float(
        np.sum(x * rates[np.newaxis, :]) * SLOT_DURATION_H
    )
    ev_load_per_slot: np.ndarray = x.sum(axis=0)
    transformer_peak_kw = float(ev_load_per_slot.max())

    sessions_fully_charged = 0
    for i in range(n):
        delivered = float(x[i].sum() * SLOT_DURATION_H)
        if kwh_needed[i] <= 0 or delivered >= float(kwh_needed[i]) - 1e-3:
            sessions_fully_charged += 1

    return {
        "total_cost_usd":         round(total_cost_usd, 4),
        "transformer_peak_kw":    round(transformer_peak_kw, 3),
        "sessions_fully_charged": sessions_fully_charged,
    }
