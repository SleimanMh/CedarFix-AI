"""
IEP Optimizer — FastAPI service for EV charging schedule optimization.

Optimizes EV charging schedules to minimize electricity cost subject to:
  - Transformer headroom constraints (building_load.py)
  - Lebanon EDL grid availability (grid_availability.py)
  - SCE TOU tariff rates (tariff.py)
  - Per-session energy delivery requirements

Runnable from repo root:
    cd iep-optimizer && uvicorn main:app --host 0.0.0.0 --port 8002
"""

import os
import sys
import time
import logging
from pathlib import Path
from datetime import datetime, date, timedelta
from typing import Literal

import numpy as np
import cvxpy as cp
import mlflow
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator, model_validator

# ── make data modules importable ─────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent.parent))

from data.tariff import get_slot_rate_profile
from data.building_load import get_transformer_headroom
from data.grid_availability import get_availability_for_optimizer
from metrics import (
    setup_metrics,
    ev_optimizer_solves_total,
    ev_optimizer_solve_time_seconds,
    ev_optimizer_transformer_peak_kw,
    ev_optimizer_sessions_gauge,
)
from fcfs_baseline import run_fcfs

# ── logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("iep-optimizer")

# ── MLflow setup ─────────────────────────────────────────────────────────────
MLFLOW_URI = os.environ.get("MLFLOW_TRACKING_URI", "./mlruns")
mlflow.set_tracking_uri(MLFLOW_URI)

EXPERIMENT_NAME = "iep-optimizer"
try:
    mlflow.set_experiment(EXPERIMENT_NAME)
except Exception as exc:
    logger.warning("MLflow experiment setup failed: %s", exc)

# ── constants ─────────────────────────────────────────────────────────────────
SLOTS_PER_DAY = 96
SLOT_DURATION_H = 0.25       # each slot = 15 minutes = 0.25 hours
CVXPY_TIME_LIMIT = 2.0       # seconds before falling back to greedy
UNCERTAINTY_BUFFER_ALPHA = 0.5  # fraction of forecast uncertainty reserved as headroom buffer
URGENCY_EPSILON = 1e-4           # LP tiebreak weight for laxity-based urgency (≪ min tariff)

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────────────────────────────────────

class EVSession(BaseModel):
    session_id: str
    connection_time: str        # ISO datetime, e.g. "2021-07-15T08:00:00+00:00"
    disconnect_time: str        # ISO datetime
    kwh_requested: float = Field(ge=0)  # Energy needed (kWh); use kwh_delivered as fallback
    kwh_delivered: float = Field(ge=0)  # Actual energy delivered (kWh) — fallback
    max_charge_rate_kw: float = Field(default=7.4, ge=0)
    has_user_inputs: bool = True

    @model_validator(mode="after")
    def validate_and_clamp(self) -> "EVSession":
        try:
            conn = datetime.fromisoformat(self.connection_time)
            disc = datetime.fromisoformat(self.disconnect_time)
        except ValueError as exc:
            raise ValueError("connection_time and disconnect_time must be valid ISO datetimes") from exc

        if conn.tzinfo is not None:
            conn = conn.replace(tzinfo=None)
        if disc.tzinfo is not None:
            disc = disc.replace(tzinfo=None)
        if disc <= conn:
            raise ValueError("disconnect_time must be after connection_time")

        # Clamp to non-negative only; site-level cap applied at array-build time
        # using req.charger_power_kw so the optimizer is truly request-driven.
        self.max_charge_rate_kw = max(self.max_charge_rate_kw, 0.0)
        return self


class OptimizeRequest(BaseModel):
    date: str                                           # "YYYY-MM-DD"
    sessions: list[EVSession]
    grid_pattern: Literal["split", "morning", "random"] = "split"
    forecast_reservation: list[float] | None = None     # optional 96-element kW uncertainty buffer
    # Site infrastructure — drive headroom physics and per-session rate caps.
    # Defaults match legacy constants so old payloads continue to work.
    transformer_kva: float = Field(default=100.0, gt=0, description="Transformer capacity in kVA (≈ kW at unity PF)")
    base_load_kw: float    = Field(default=50.0,  ge=0, description="Building base load peak in kW")
    charger_power_kw: float = Field(default=7.4,  gt=0, description="Maximum per-charger power in kW")

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise ValueError("date must be in YYYY-MM-DD format") from exc
        return value


class SlotSchedule(BaseModel):
    slot_index: int
    slot_time: str      # "HH:MM"
    charge_kw: float


class EVSchedule(BaseModel):
    session_id: str
    slots: list[SlotSchedule]
    total_kwh_scheduled: float
    cost_usd: float


class OptimizeResponse(BaseModel):
    date: str
    schedules: list[EVSchedule]
    kpis: dict
    solver_status: str          # "optimal", "greedy_fallback", "infeasible"
    solve_time_s: float


class BaselineResponse(BaseModel):
    date: str
    kpis: dict          # FCFS KPIs: total_cost_usd, transformer_peak_kw, sessions_fully_charged
    solve_time_s: float


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _slot_time_str(slot_index: int) -> str:
    """Return 'HH:MM' for a given 0-based slot index (15-min resolution)."""
    minutes = slot_index * 15
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _parse_date(date_str: str) -> datetime:
    """Parse 'YYYY-MM-DD' into a midnight UTC datetime."""
    d = date.fromisoformat(date_str)
    return datetime(d.year, d.month, d.day)


def _active_slots(
    session: EVSession,
    day_start: datetime,
) -> np.ndarray:
    """
    Returns a binary 96-element array indicating which 15-min slots
    fall entirely within [connection_time, disconnect_time).

    A slot t is active when:
        slot_start = day_start + t * 15min  >= connection_time
        slot_end   = day_start + (t+1)*15min <= disconnect_time
    """
    def _parse_iso(s: str) -> datetime:
        dt = datetime.fromisoformat(s)
        # Strip timezone for uniform naive comparison with day_start
        if dt.tzinfo is not None:
            dt = dt.replace(tzinfo=None)
        return dt

    conn = _parse_iso(session.connection_time)
    disc = _parse_iso(session.disconnect_time)

    active = np.zeros(SLOTS_PER_DAY, dtype=float)
    for t in range(SLOTS_PER_DAY):
        slot_start = day_start + timedelta(minutes=15 * t)
        slot_end   = day_start + timedelta(minutes=15 * (t + 1))
        if slot_start >= conn and slot_end <= disc:
            active[t] = 1.0
    return active


def _kwh_needed(session: EVSession) -> float:
    """Energy to schedule: prefer kwh_requested, fall back to kwh_delivered."""
    return session.kwh_requested if session.kwh_requested > 0 else session.kwh_delivered


# ─────────────────────────────────────────────────────────────────────────────
# Greedy fallback scheduler
# ─────────────────────────────────────────────────────────────────────────────

def _greedy_schedule(
    n: int,
    rates: np.ndarray,
    headroom: np.ndarray,
    grid: np.ndarray,
    active: np.ndarray,          # shape (n, 96)
    max_rates: np.ndarray,       # shape (n,)
    kwh_needed: np.ndarray,      # shape (n,)
) -> np.ndarray:
    """
    Fair round-robin greedy scheduler: cheapest slots first, proportional
    allocation per slot so no EV is starved by index ordering.

    Returns x[n, 96] charge power matrix (kW).
    """
    x = np.zeros((n, SLOTS_PER_DAY), dtype=float)
    remaining = kwh_needed.copy()
    available_headroom = headroom.copy()

    # Process slots in ascending tariff-rate order (cheapest first)
    slot_order = np.argsort(rates)

    for t in slot_order:
        if grid[t] == 0:
            continue
        slot_headroom = available_headroom[t]
        if slot_headroom <= 0:
            continue

        # Collect eligible EVs and their max demand for this slot
        eligible = []
        for i in range(n):
            if active[i, t] == 0 or remaining[i] <= 0:
                continue
            want_kw = min(max_rates[i], remaining[i] / SLOT_DURATION_H)
            if want_kw > 0:
                eligible.append((i, want_kw))

        if not eligible:
            continue

        # Proportional allocation: each EV gets a fair share of headroom
        total_want = sum(w for _, w in eligible)
        for i, want_kw in eligible:
            if total_want <= slot_headroom:
                alloc_kw = want_kw
            else:
                alloc_kw = want_kw * (slot_headroom / total_want)

            x[i, t] = alloc_kw
            remaining[i] -= alloc_kw * SLOT_DURATION_H
            remaining[i] = max(remaining[i], 0.0)

        used = sum(x[i, t] for i, _ in eligible)
        available_headroom[t] = slot_headroom - used

    return x


# ─────────────────────────────────────────────────────────────────────────────
# CVXPY optimizer
# ─────────────────────────────────────────────────────────────────────────────

def _cvxpy_schedule(
    n: int,
    rates: np.ndarray,
    headroom: np.ndarray,
    grid: np.ndarray,
    active: np.ndarray,
    max_rates: np.ndarray,
    kwh_needed: np.ndarray,
) -> tuple[np.ndarray, str, float]:
    """
    Solve the LP via CVXPY.

    Returns:
        x          — charge power matrix (n, 96)
        status_str — "optimal" or failure string
        solve_time — wall-clock seconds
    """
    x = cp.Variable((n, SLOTS_PER_DAY), nonneg=True)

    # Cost: sum_i sum_t  x[i,t] * rate[t] * 0.25 hr
    cost = cp.sum(cp.multiply(x, rates[np.newaxis, :]) * SLOT_DURATION_H)

    # Urgency tiebreak: penalise later slots more for tight-laxity EVs.
    # laxity[i] = available_grid_on_slots[i] - slots_needed[i]; higher = more flexible.
    # w[i,t] = t / (96 * max(laxity, 1)) — negligible vs cost but breaks ties.
    slot_indices = np.arange(SLOTS_PER_DAY, dtype=float)
    grid_on_active = np.sum(active * grid[np.newaxis, :], axis=1)  # (n,)
    slots_needed = np.where(max_rates > 0, kwh_needed / (max_rates * SLOT_DURATION_H), 0.0)
    laxity = np.maximum(grid_on_active - slots_needed, 1.0)  # (n,)
    w = slot_indices[np.newaxis, :] / (SLOTS_PER_DAY * laxity[:, np.newaxis])  # (n, 96)
    urgency = URGENCY_EPSILON * cp.sum(cp.multiply(x, w))

    constraints = []

    # (a) Transformer headroom per slot — vectorized
    constraints.append(cp.sum(x, axis=0) <= headroom)

    # (b) Energy delivery per session — capped to achievable amount.
    # Without the cap, sessions whose active window doesn't overlap any grid-on
    # slot produce an infeasible LP.
    achievable_kwh = max_rates * SLOT_DURATION_H * grid_on_active  # (n,)
    target_kwh = np.minimum(kwh_needed, achievable_kwh)            # (n,)
    for i in range(n):
        if target_kwh[i] > 0:
            constraints.append(
                cp.sum(x[i, :]) * SLOT_DURATION_H >= float(target_kwh[i])
            )

    # (c) Max charge rate × active × grid — vectorized upper bound matrix
    upper_bound = max_rates[:, np.newaxis] * active * grid[np.newaxis, :]  # (n, 96)
    constraints.append(x <= upper_bound)

    problem = cp.Problem(cp.Minimize(cost + urgency), constraints)

    t0 = time.perf_counter()
    try:
        problem.solve(solver=cp.CLARABEL, time_limit=CVXPY_TIME_LIMIT)
    except Exception as exc:
        logger.warning("CVXPY solver exception: %s", exc)
        return np.zeros((n, SLOTS_PER_DAY)), "solver_error", time.perf_counter() - t0

    elapsed = time.perf_counter() - t0

    if problem.status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE) and x.value is not None:
        return np.clip(x.value, 0.0, None), problem.status, elapsed

    return np.zeros((n, SLOTS_PER_DAY)), str(problem.status), elapsed


# ─────────────────────────────────────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="IEP Optimizer",
    description="EV charging schedule optimizer for the Lebanese EDL grid scenario.",
    version="1.0.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
setup_metrics(app, "iep-optimizer")

@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/baseline", response_model=BaselineResponse)
def baseline(req: OptimizeRequest) -> BaselineResponse:
    """FCFS non-AI baseline — for isolated testing and 3-way comparison."""
    t0 = time.perf_counter()
    logger.info(
        "baseline  transformer_kva=%.1f  base_load_kw=%.1f  charger_power_kw=%.2f",
        req.transformer_kva, req.base_load_kw, req.charger_power_kw,
    )
    day_start = _parse_date(req.date)
    month = day_start.month
    is_weekend = day_start.weekday() >= 5

    headroom = get_transformer_headroom(day_start, peak_kw=req.base_load_kw, transformer_kw=req.transformer_kva)
    grid     = get_availability_for_optimizer(day_start, pattern=req.grid_pattern).astype(float)
    rates    = np.array(get_slot_rate_profile(month, is_weekend), dtype=float)

    n = len(req.sessions)
    if n == 0:
        return BaselineResponse(
            date=req.date,
            kpis={"total_cost_usd": 0.0, "transformer_peak_kw": 0.0, "sessions_fully_charged": 0},
            solve_time_s=0.0,
        )

    active          = np.zeros((n, SLOTS_PER_DAY), dtype=float)
    max_rates_arr   = np.zeros(n, dtype=float)
    kwh_needed_arr  = np.zeros(n, dtype=float)
    for i, sess in enumerate(req.sessions):
        active[i]         = _active_slots(sess, day_start)
        max_rates_arr[i]  = min(max(sess.max_charge_rate_kw, 0.0), req.charger_power_kw)
        kwh_needed_arr[i] = _kwh_needed(sess)

    kpis = run_fcfs(rates, headroom, grid, active, max_rates_arr, kwh_needed_arr)
    return BaselineResponse(
        date=req.date,
        kpis=kpis,
        solve_time_s=round(time.perf_counter() - t0, 4),
    )


@app.post("/optimize", response_model=OptimizeResponse)
def optimize(req: OptimizeRequest) -> OptimizeResponse:
    t_total_start = time.perf_counter()
    logger.info(
        "optimize  transformer_kva=%.1f  base_load_kw=%.1f  charger_power_kw=%.2f",
        req.transformer_kva, req.base_load_kw, req.charger_power_kw,
    )

    # ── 1. Parse date metadata ────────────────────────────────────────────────
    day_start = _parse_date(req.date)
    month = day_start.month
    is_weekend = day_start.weekday() >= 5   # Mon=0 … Sun=6

    # ── 2-4. Load environment arrays ─────────────────────────────────────────
    headroom: np.ndarray = get_transformer_headroom(day_start, peak_kw=req.base_load_kw, transformer_kw=req.transformer_kva)  # (96,) kW
    grid: np.ndarray     = get_availability_for_optimizer(              # (96,) 0/1
        day_start, pattern=req.grid_pattern
    ).astype(float)
    rates: np.ndarray    = np.array(                                    # (96,) $/kWh
        get_slot_rate_profile(month, is_weekend), dtype=float
    )

    # ── 2b. Apply forecast uncertainty headroom reservation ───────────────
    forecast_headroom_applied = False
    forecast_reserved_kwh = 0.0
    avg_reservation_kw = 0.0
    if (req.forecast_reservation is not None
            and len(req.forecast_reservation) == SLOTS_PER_DAY):
        reservation = np.clip(
            np.array(req.forecast_reservation, dtype=float), 0.0, None
        )
        headroom = np.maximum(headroom - reservation, 0.0)
        forecast_headroom_applied = True
        forecast_reserved_kwh = round(float(np.sum(reservation) * SLOT_DURATION_H), 4)
        avg_reservation_kw = round(float(np.mean(reservation)), 4)

    sessions = req.sessions
    n = len(sessions)

    if n == 0:
        # No sessions — return empty response immediately
        return OptimizeResponse(
            date=req.date,
            schedules=[],
            kpis={
                "transformer_peak_kw": 0.0,
                "transformer_utilization_pct": 0.0,
                "total_cost_usd": 0.0,
                "total_kwh_scheduled": 0.0,
                "grid_constrained_slots": int(np.sum(grid == 0)),
                "sessions_fully_charged": 0,
                "min_session_kwh": 0.0,
                "fairness_index": 1.0,
                "avg_laxity": 0.0,
                "forecast_headroom_applied": forecast_headroom_applied,
                "forecast_reserved_kwh": forecast_reserved_kwh,
                "avg_reservation_kw": avg_reservation_kw,
                "forecast_reserved_slots": 0,
                "forecast_binding_slots": 0,
                "forecast_headroom_reduction_pct": 0.0,
                "unmet_energy_kwh": 0.0,
                "unmet_sessions_count": 0,
                "baseline_comparison": {
                    "fcfs_total_cost_usd": 0.0,
                    "fcfs_transformer_peak_kw": 0.0,
                    "fcfs_sessions_fully_charged": 0,
                    "cost_delta_usd": 0.0,
                    "peak_reduction_kw": 0.0,
                    "completion_delta": 0,
                },
            },
            solver_status="optimal",
            solve_time_s=0.0,
        )

    # ── 5. Build per-session arrays ───────────────────────────────────────────
    active    = np.zeros((n, SLOTS_PER_DAY), dtype=float)
    max_rates = np.zeros(n, dtype=float)
    kwh_needed_arr = np.zeros(n, dtype=float)

    for i, sess in enumerate(sessions):
        active[i]        = _active_slots(sess, day_start)
        max_rates[i]     = min(max(sess.max_charge_rate_kw, 0.0), req.charger_power_kw)
        kwh_needed_arr[i] = _kwh_needed(sess)

    # ── 6. CVXPY optimization ─────────────────────────────────────────────────
    # Always attempt LP first — CLARABEL's 2s time limit is the guard.
    # If the solver times out or fails, fall back to the fair greedy scheduler.
    solve_time: float = 0.0
    x, cvxpy_status, solve_time = _cvxpy_schedule(
        n, rates, headroom, grid, active, max_rates, kwh_needed_arr
    )

    solver_status: str
    if cvxpy_status in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE):
        solver_status = "optimal"
        logger.info("CVXPY solved optimally in %.3fs", solve_time)
    else:
        logger.warning(
            "CVXPY status '%s' (%.3fs) — falling back to greedy", cvxpy_status, solve_time
        )
        x = _greedy_schedule(n, rates, headroom, grid, active, max_rates, kwh_needed_arr)
        solver_status = "greedy_fallback"

    solve_time_total = time.perf_counter() - t_total_start

    # ── 7. Build response ─────────────────────────────────────────────────────
    schedules: list[EVSchedule] = []
    total_cost_usd = 0.0
    total_kwh_scheduled = 0.0
    sessions_fully_charged = 0

    for i, sess in enumerate(sessions):
        ev_slots: list[SlotSchedule] = []
        ev_kwh = 0.0
        ev_cost = 0.0

        for t in range(SLOTS_PER_DAY):
            kw = float(x[i, t])
            if kw > 1e-6:
                ev_slots.append(SlotSchedule(
                    slot_index=t,
                    slot_time=_slot_time_str(t),
                    charge_kw=round(kw, 4),
                ))
                kwh_this_slot = kw * SLOT_DURATION_H
                ev_kwh  += kwh_this_slot
                ev_cost += kwh_this_slot * rates[t]

        schedules.append(EVSchedule(
            session_id=sess.session_id,
            slots=ev_slots,
            total_kwh_scheduled=round(ev_kwh, 4),
            cost_usd=round(ev_cost, 6),
        ))

        total_kwh_scheduled += ev_kwh
        total_cost_usd      += ev_cost

        needed = kwh_needed_arr[i]
        if needed <= 0 or ev_kwh >= needed - 1e-3:
            sessions_fully_charged += 1

    # Per-slot total EV load for KPI calculations
    ev_load_per_slot: np.ndarray = x.sum(axis=0)   # (96,)
    transformer_peak_kw = float(ev_load_per_slot.max()) if n > 0 else 0.0

    # Fairness & laxity KPIs
    ev_kwh_list = [sched.total_kwh_scheduled for sched in schedules]
    min_session_kwh = min(ev_kwh_list) if ev_kwh_list else 0.0
    kwh_arr = np.array(ev_kwh_list)
    if n > 0 and (kwh_arr ** 2).sum() > 0:
        fairness_index = float((kwh_arr.sum() ** 2) / (n * (kwh_arr ** 2).sum()))
    else:
        fairness_index = 1.0

    # Average laxity: how flexible are the sessions' windows?
    laxity_vals = []
    for i, sess in enumerate(sessions):
        grid_on_active = float(np.sum(active[i] * grid))
        slots_needed_i = kwh_needed_arr[i] / (float(max_rates[i]) * SLOT_DURATION_H) if max_rates[i] > 0 else 0
        laxity_vals.append(max(grid_on_active - slots_needed_i, 0.0))
    avg_laxity = float(np.mean(laxity_vals)) if laxity_vals else 0.0

    # Phase C: unmet-demand transparency
    unmet_energy_kwh = 0.0
    unmet_sessions_count = 0
    for i, sched in enumerate(schedules):
        needed = kwh_needed_arr[i]
        delivered = sched.total_kwh_scheduled
        if needed > 0 and delivered < needed - 1e-3:
            unmet_energy_kwh += needed - delivered
            unmet_sessions_count += 1
    unmet_energy_kwh = round(unmet_energy_kwh, 4)

    kpis = {
        "transformer_peak_kw":         round(transformer_peak_kw, 3),
        "transformer_utilization_pct": round(transformer_peak_kw / req.transformer_kva * 100.0, 2),
        "avg_available_headroom_kw":   round(float(np.mean(headroom)), 3),
        "total_cost_usd":              round(total_cost_usd, 4),
        "total_kwh_scheduled":         round(total_kwh_scheduled, 4),
        "grid_constrained_slots":      int(np.sum(grid == 0)),
        "sessions_fully_charged":      sessions_fully_charged,
        "min_session_kwh":             round(min_session_kwh, 4),
        "fairness_index":              round(fairness_index, 4),
        "avg_laxity":                  round(avg_laxity, 2),
        "forecast_headroom_applied":   forecast_headroom_applied,
        "forecast_reserved_kwh":       forecast_reserved_kwh,
        "avg_reservation_kw":          avg_reservation_kw,
        "forecast_reserved_slots":     int(np.sum(np.array(req.forecast_reservation or []) > 0)),
        "forecast_binding_slots":      int(np.sum(
            (np.array(req.forecast_reservation or [0.0] * 96)[:SLOTS_PER_DAY] > 0)
            & (ev_load_per_slot > 0)
        )),
        "forecast_headroom_reduction_pct": round(
            float(np.sum(np.clip(req.forecast_reservation or [], 0, None))
                  / max(float(np.sum(headroom)) + float(np.sum(np.clip(req.forecast_reservation or [], 0, None))), 1e-9)
                  * 100), 2
        ) if forecast_headroom_applied else 0.0,
        "unmet_energy_kwh":            unmet_energy_kwh,
        "unmet_sessions_count":        unmet_sessions_count,
    }

    # ── 9. FCFS baseline comparison (pure NumPy, ~1ms) ───────────────────────
    _fcfs = run_fcfs(rates, headroom, grid, active, max_rates, kwh_needed_arr)
    kpis["baseline_comparison"] = {
        "fcfs_total_cost_usd":         _fcfs["total_cost_usd"],
        "fcfs_transformer_peak_kw":    _fcfs["transformer_peak_kw"],
        "fcfs_sessions_fully_charged": _fcfs["sessions_fully_charged"],
        "cost_delta_usd":              round(kpis["total_cost_usd"] - _fcfs["total_cost_usd"], 4),
        "peak_reduction_kw":           round(_fcfs["transformer_peak_kw"] - kpis["transformer_peak_kw"], 3),
        "completion_delta":            kpis["sessions_fully_charged"] - _fcfs["sessions_fully_charged"],
    }

    # ── 8. MLflow logging ─────────────────────────────────────────────────────
    try:
        with mlflow.start_run():
            mlflow.log_params({
                "date":         req.date,
                "n_sessions":   n,
                "grid_pattern": req.grid_pattern,
            })
            mlflow.log_metrics({
                "solve_time_s":          round(solve_time_total, 4),
                "transformer_peak_kw":   kpis["transformer_peak_kw"],
                "total_cost_usd":        kpis["total_cost_usd"],
                "forecast_headroom_applied": int(forecast_headroom_applied),
                "forecast_reserved_kwh":  forecast_reserved_kwh,
            })
    except Exception as exc:
        logger.warning("MLflow logging failed: %s", exc)

    ev_optimizer_solves_total.labels(status=solver_status).inc()
    ev_optimizer_solve_time_seconds.observe(solve_time_total)
    ev_optimizer_transformer_peak_kw.set(kpis["transformer_peak_kw"])
    ev_optimizer_sessions_gauge.set(n)
    
    return OptimizeResponse(
        date=req.date,
        schedules=schedules,
        kpis=kpis,
        solver_status=solver_status,
        solve_time_s=round(solve_time_total, 4),
    )
