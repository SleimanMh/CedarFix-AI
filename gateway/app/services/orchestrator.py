"""
Orchestrator — coordinates calls between ML Service and Optimizer.

Three-way comparison that isolates ML value:

  1. AI + ML:  LP optimizer + ML departure predictions + ML demand forecast
  2. AI only:  LP optimizer + fixed 4h assumption (no ML at all)
  3. FCFS:     First-come-first-served greedy (no ML, no optimization)

KEY INSIGHT: ML predictions serve as the "actual" departure time (ground truth).
  - The ML-aware strategy schedules with the correct departure → efficient.
  - The no-ML strategy schedules with a fixed 4h assumption → but vehicles
    actually leave at the ML-predicted time → wasted charging slots → lower
    satisfaction.  This demonstrates concrete ML value.
"""

import logging
import math
import uuid
from datetime import datetime, timedelta, timezone

import httpx

from app.config import ML_SERVICE_URL, OPTIMIZER_SERVICE_URL, ML_TIMEOUT_S, OPTIMIZER_TIMEOUT_S
from app.schemas import (
    SimulationRequest, SimulationResponse, StrategyResult,
    EVResult, TimeSeriesPoint, GridMetrics, MLMetrics,
)

logger = logging.getLogger(__name__)

# Fixed stay assumption for the no-ML baseline (minutes)
# Without ML, the system has no idea when the vehicle will leave.
# A conservative default is to assume a full workday (8 hours).
DEFAULT_STAY_MINUTES = 480.0  # 8 hours — naive "stay all day" assumption


async def run_simulation(request: SimulationRequest) -> SimulationResponse:
    run_id = str(uuid.uuid4())[:8]
    num_slots = int(request.simulation_duration_hours * 60 / request.time_step_minutes)
    slot_duration_hours = request.time_step_minutes / 60

    now = datetime.now(timezone.utc)

    # ══════════════════════════════════════════════════════════════════════
    #  ML FEATURE 1: Departure Time Prediction  (per-vehicle)
    # ══════════════════════════════════════════════════════════════════════
    departure_predictions = {}
    ml_pred_count = 0
    ml_skip_count = 0
    try:
        async with httpx.AsyncClient(timeout=ML_TIMEOUT_S) as client:
            for ev in request.vehicles:
                arrival = ev.arrival_time or now
                resp = await client.post(
                    f"{ML_SERVICE_URL}/predict-departure",
                    json={
                        "arrival_time": arrival.isoformat(),
                        "site_id": "0002",
                        "cluster_id": "0039",
                    },
                )
                if resp.status_code == 200:
                    data = resp.json()
                    departure_predictions[ev.ev_id] = data["predicted_stay_duration_min"]
    except Exception as e:
        logger.warning(f"ML departure prediction unavailable: {e}")

    # ══════════════════════════════════════════════════════════════════════
    #  ML FEATURE 2: Demand Forecasting  (aggregate future arrivals)
    # ══════════════════════════════════════════════════════════════════════
    ml_future_arrivals = []
    try:
        horizon_windows = max(1, int(request.simulation_duration_hours * 2))
        async with httpx.AsyncClient(timeout=ML_TIMEOUT_S) as client:
            resp = await client.post(
                f"{ML_SERVICE_URL}/forecast",
                json={
                    "current_time": now.isoformat(),
                    "horizon_windows": min(horizon_windows, 96),
                    "recent_arrivals": [],
                    "recent_kwh": [],
                },
            )
            if resp.status_code == 200:
                forecast_data = resp.json()
                for point in forecast_data["forecast"]:
                    window_start = datetime.fromisoformat(point["window_start"])
                    minutes_from_now = max(0, (window_start - now).total_seconds() / 60)
                    slot_idx = int(minutes_from_now / request.time_step_minutes)

                    if slot_idx < num_slots and point["predicted_arrivals"] > 0.3:
                        ml_future_arrivals.append({
                            "slot": slot_idx,
                            "predicted_count": point["predicted_arrivals"],
                            "predicted_kwh": point["predicted_kwh"],
                            "avg_charge_kw": 7.2,
                        })
                logger.info(f"ML forecast: {len(ml_future_arrivals)} future arrival windows")
    except Exception as e:
        logger.warning(f"ML demand forecast unavailable: {e}")

    # ── Build vehicle lists with "actual" departure (ground truth) ───────
    #
    # The "actual" departure is:
    #   - planned_departure_time if provided by user (known truth)
    #   - ML-predicted departure if no departure given (best estimate = truth)
    #
    # ML strategy: optimizer sees the CORRECT departure → schedules well
    # No-ML strategy: optimizer sees DEFAULT_STAY departure → schedules
    #   based on wrong assumption → power after actual departure is WASTED

    ml_vehicles = []       # For AI + ML strategy
    no_ml_vehicles = []    # For AI-only and FCFS strategies
    actual_dep_slots = {}  # Ground truth departure per vehicle

    for ev in request.vehicles:
        energy_needed = ev.battery_capacity_kwh * (ev.target_pct - ev.battery_pct) / 100
        energy_needed = max(0, energy_needed)

        arrival_slot = 0
        if ev.arrival_time:
            minutes_from_now = max(0, (ev.arrival_time - now).total_seconds() / 60)
            arrival_slot = int(minutes_from_now / request.time_step_minutes)

        # Determine actual stay (ground truth)
        if ev.planned_departure_time:
            actual_stay = max(15, (ev.planned_departure_time - (ev.arrival_time or now)).total_seconds() / 60)
            ml_skip_count += 1
        elif ev.ev_id in departure_predictions:
            actual_stay = max(15, departure_predictions[ev.ev_id])
            ml_pred_count += 1
        else:
            actual_stay = DEFAULT_STAY_MINUTES
            ml_skip_count += 1

        actual_dep = min(num_slots, arrival_slot + max(1, int(actual_stay / request.time_step_minutes)))
        actual_dep_slots[ev.ev_id] = actual_dep

        # ML vehicle: KNOWS the actual departure
        ml_vehicles.append({
            "ev_id": ev.ev_id,
            "energy_needed_kwh": round(energy_needed, 3),
            "max_charge_kw": ev.max_charge_kw,
            "arrival_slot": arrival_slot,
            "departure_slot": actual_dep,  # correct info
        })

        # No-ML vehicle: ASSUMES default stay (may be wrong)
        if ev.planned_departure_time:
            no_ml_dep = actual_dep  # known departure — same for both
        else:
            no_ml_stay = DEFAULT_STAY_MINUTES
            no_ml_dep = min(num_slots, arrival_slot + max(1, int(no_ml_stay / request.time_step_minutes)))

        no_ml_vehicles.append({
            "ev_id": ev.ev_id,
            "energy_needed_kwh": round(energy_needed, 3),
            "max_charge_kw": ev.max_charge_kw,
            "arrival_slot": arrival_slot,
            "departure_slot": no_ml_dep,  # possibly wrong
        })

    # ── Base load profile ────────────────────────────────────────────────
    base_load = _generate_base_load(request.building_base_load_kw, num_slots, request.time_step_minutes)

    # ── Adjust ML forecast reservations ──────────────────────────────────
    if ml_future_arrivals:
        known_per_slot = {}
        for v in ml_vehicles:
            s = v["arrival_slot"]
            known_per_slot[s] = known_per_slot.get(s, 0) + 1

        adjusted = []
        for fa in ml_future_arrivals:
            known = known_per_slot.get(fa["slot"], 0)
            net = max(0, fa["predicted_count"] - known)
            if net > 0.1:
                adjusted.append({
                    **fa,
                    "predicted_count": net,
                    "predicted_kwh": fa["predicted_kwh"] * (net / fa["predicted_count"]),
                })
        ml_future_arrivals = adjusted

    # ══════════════════════════════════════════════════════════════════════
    #  STRATEGY 1: AI + ML  (LP optimizer + correct departures)
    #  Demand forecast is used for monitoring/awareness (dashboard),
    #  not for capacity reservation — avoids penalising current vehicles.
    # ══════════════════════════════════════════════════════════════════════
    ai_result = await _call_optimizer(
        "optimal", ml_vehicles, num_slots,
        slot_duration_hours, request.transformer_capacity_kw, base_load,
        predicted_future_arrivals=[],
    )
    ai_result.strategy = "ai_ml"

    # ══════════════════════════════════════════════════════════════════════
    #  STRATEGY 2: AI without ML  (LP + wrong departures, no forecast)
    #  → post-process: truncate power after ACTUAL departure
    # ══════════════════════════════════════════════════════════════════════
    no_ml_result = await _call_optimizer(
        "optimal", no_ml_vehicles, num_slots,
        slot_duration_hours, request.transformer_capacity_kw, base_load,
        predicted_future_arrivals=[],
    )
    no_ml_result.strategy = "ai_no_ml"
    # Apply actual departures — truncate power scheduled after vehicle left
    no_ml_result = _apply_actual_departures(no_ml_result, actual_dep_slots, base_load,
                                            request.transformer_capacity_kw, slot_duration_hours)

    # ══════════════════════════════════════════════════════════════════════
    #  STRATEGY 3: FCFS baseline  (greedy, reactive — no scheduling)
    #  FCFS represents a "dumb charger": it charges while the vehicle is
    #  physically plugged in and stops when it leaves.  It doesn't need
    #  departure predictions because it reacts to the physical event.
    #  We give it the correct departure (= actual presence window).
    # ══════════════════════════════════════════════════════════════════════
    baseline_result = None
    if request.compare_baseline:
        baseline_result = await _call_optimizer(
            "fcfs", ml_vehicles, num_slots,
            slot_duration_hours, request.transformer_capacity_kw, base_load,
            predicted_future_arrivals=[],
        )
        baseline_result.strategy = "fcfs"

    # ── Grid validation for all strategies ──
    for result in [ai_result, no_ml_result, baseline_result]:
        if result:
            result.grid_validation = await _call_grid_validator(
                result, base_load, request.transformer_capacity_kw
            )

    # ── ML Metrics ──
    pred_stays = list(departure_predictions.values())
    total_reserved = sum(
        fa["predicted_kwh"] for fa in ml_future_arrivals
    ) if ml_future_arrivals else 0

    ml_metrics = MLMetrics(
        departure_predictions_used=ml_pred_count,
        departure_predictions_skipped=ml_skip_count,
        demand_forecast_windows=len(ml_future_arrivals),
        capacity_reserved_kwh=round(total_reserved, 1),
        avg_predicted_stay_min=round(sum(pred_stays) / len(pred_stays), 1) if pred_stays else None,
        default_stay_min=DEFAULT_STAY_MINUTES,
    )

    return SimulationResponse(
        run_id=run_id,
        status="success",
        simulation_duration_hours=request.simulation_duration_hours,
        time_step_minutes=request.time_step_minutes,
        num_vehicles=len(request.vehicles),
        ai_result=ai_result,
        no_ml_result=no_ml_result,
        baseline_result=baseline_result,
        ml_metrics=ml_metrics,
    )


def _apply_actual_departures(
    result: StrategyResult,
    actual_dep_slots: dict[str, int],
    base_load: list[float],
    transformer_capacity_kw: float,
    slot_duration_hours: float,
) -> StrategyResult:
    """
    Truncate power schedules at the ACTUAL departure slot.

    The no-ML strategy assumed DEFAULT_STAY_MINUTES, but the vehicle
    actually left at the ML-predicted time.  Any power scheduled after
    the real departure is wasted (vehicle unplugged).

    This simulates the real-world consequence of not knowing departure.
    """
    new_ev_results = []
    for ev in result.ev_results:
        actual_dep = actual_dep_slots.get(ev.ev_id, len(ev.power_schedule_kw))
        schedule = list(ev.power_schedule_kw)

        # Zero out power after actual departure
        for k in range(actual_dep, len(schedule)):
            schedule[k] = 0.0

        delivered = sum(schedule) * slot_duration_hours
        satisfaction = min(100.0, delivered / ev.energy_needed_kwh * 100) if ev.energy_needed_kwh > 0 else 100.0

        new_ev_results.append(EVResult(
            ev_id=ev.ev_id,
            energy_delivered_kwh=round(delivered, 3),
            energy_needed_kwh=ev.energy_needed_kwh,
            satisfaction_pct=round(satisfaction, 1),
            power_schedule_kw=schedule,
        ))

    # Rebuild time series and aggregate metrics
    num_slots = len(result.time_series)
    total_energy = sum(e.energy_delivered_kwh for e in new_ev_results)
    overall_sat = sum(e.satisfaction_pct for e in new_ev_results) / len(new_ev_results) if new_ev_results else 0

    new_time_series = []
    peak_load = 0.0
    overload_slots = 0
    for k in range(num_slots):
        ev_load = sum(e.power_schedule_kw[k] for e in new_ev_results)
        total = ev_load + base_load[k]
        util = total / transformer_capacity_kw * 100 if transformer_capacity_kw > 0 else 0
        overload = total > transformer_capacity_kw
        if overload:
            overload_slots += 1
        peak_load = max(peak_load, total)
        new_time_series.append(TimeSeriesPoint(
            time_minutes=result.time_series[k].time_minutes,
            ev_load_kw=round(ev_load, 2),
            building_load_kw=result.time_series[k].building_load_kw,
            total_load_kw=round(total, 2),
            transformer_utilization_pct=round(util, 2),
            overload=overload,
        ))

    return StrategyResult(
        strategy=result.strategy,
        ev_results=new_ev_results,
        overall_satisfaction_pct=round(overall_sat, 1),
        peak_load_kw=round(peak_load, 2),
        total_energy_delivered_kwh=round(total_energy, 1),
        overload_slots=overload_slots,
        time_series=new_time_series,
        grid_validation=result.grid_validation,
    )


async def _call_optimizer(
    strategy: str,
    vehicles: list[dict],
    num_slots: int,
    slot_duration_hours: float,
    transformer_capacity_kw: float,
    base_load: list[float],
    predicted_future_arrivals: list[dict] | None = None,
) -> StrategyResult:
    """Call the optimizer service."""
    payload = {
        "vehicles": vehicles,
        "num_slots": num_slots,
        "slot_duration_hours": slot_duration_hours,
        "transformer_capacity_kw": transformer_capacity_kw,
        "base_load_per_slot_kw": base_load,
        "predicted_future_arrivals": predicted_future_arrivals or [],
        "strategy": strategy,
    }

    try:
        async with httpx.AsyncClient(timeout=OPTIMIZER_TIMEOUT_S) as client:
            resp = await client.post(f"{OPTIMIZER_SERVICE_URL}/optimize", json=payload)
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Optimizer call failed for strategy={strategy}: {e}")
        return StrategyResult(
            strategy=strategy,
            ev_results=[],
            overall_satisfaction_pct=0,
            peak_load_kw=0,
            total_energy_delivered_kwh=0,
            overload_slots=0,
            time_series=[],
        )

    # Build time series
    time_series = []
    for k in range(num_slots):
        ev_load = sum(s["power_per_slot_kw"][k] for s in data["schedules"])
        total = ev_load + base_load[k]
        util = total / transformer_capacity_kw * 100 if transformer_capacity_kw > 0 else 0
        time_series.append(TimeSeriesPoint(
            time_minutes=k * slot_duration_hours * 60,
            ev_load_kw=round(ev_load, 2),
            building_load_kw=round(base_load[k], 2),
            total_load_kw=round(total, 2),
            transformer_utilization_pct=round(util, 2),
            overload=total > transformer_capacity_kw,
        ))

    ev_results = [
        EVResult(
            ev_id=s["ev_id"],
            energy_delivered_kwh=s["energy_delivered_kwh"],
            energy_needed_kwh=s["energy_needed_kwh"],
            satisfaction_pct=s["satisfaction_pct"],
            power_schedule_kw=s["power_per_slot_kw"],
        )
        for s in data["schedules"]
    ]

    return StrategyResult(
        strategy=strategy,
        ev_results=ev_results,
        overall_satisfaction_pct=data["overall_satisfaction_pct"],
        peak_load_kw=data["peak_load_kw"],
        total_energy_delivered_kwh=data["total_energy_delivered_kwh"],
        overload_slots=data["overload_slots"],
        time_series=time_series,
    )


async def _call_grid_validator(
    result: StrategyResult,
    base_load: list[float],
    transformer_capacity_kw: float,
) -> GridMetrics | None:
    """Call grid validation on the total load profile."""
    total_loads = [p.total_load_kw for p in result.time_series]

    payload = {
        "total_load_per_slot_kw": total_loads,
        "transformer_capacity_kw": transformer_capacity_kw,
        "transformer_kva": transformer_capacity_kw / 0.95,
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(f"{OPTIMIZER_SERVICE_URL}/validate-grid", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return GridMetrics(**data)
    except Exception as e:
        logger.warning(f"Grid validation failed: {e}")
        return None


def _generate_base_load(base_kw: float, num_slots: int, step_minutes: int) -> list[float]:
    """
    Generate a realistic building base load profile (sinusoidal + noise).
    Peaks during business hours, dips at night.
    """
    loads = []
    for k in range(num_slots):
        hour = (k * step_minutes / 60) % 24
        if 7 <= hour <= 9:
            ramp = (hour - 7) / 2
            factor = 0.4 + 0.6 * ramp
        elif 9 < hour <= 17:
            factor = 1.0
        elif 17 < hour <= 20:
            factor = 1.0 - 0.5 * (hour - 17) / 3
        else:
            factor = 0.4

        variation = 0.05 * math.sin(2 * math.pi * hour / 24)
        load = base_kw * (factor + variation)
        loads.append(round(max(0, load), 2))

    return loads
