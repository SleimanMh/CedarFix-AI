"""Request/response schemas for the Optimizer + Grid Validation service."""

from pydantic import BaseModel, Field


class EVVehicle(BaseModel):
    ev_id: str
    energy_needed_kwh: float = Field(gt=0, description="Remaining energy to deliver (kWh)")
    max_charge_kw: float = Field(gt=0, le=350, description="Max charger power (kW)")
    arrival_slot: int = Field(ge=0, description="Time slot when vehicle arrived")
    departure_slot: int = Field(gt=0, description="Time slot when vehicle departs")


class FutureArrival(BaseModel):
    """ML-predicted future EV arrival for a time window."""
    slot: int = Field(ge=0, description="Time slot of predicted arrival")
    predicted_count: float = Field(ge=0, description="Predicted number of EVs arriving")
    predicted_kwh: float = Field(ge=0, description="Predicted total energy demand (kWh)")
    avg_charge_kw: float = Field(default=7.2, description="Assumed charger rate for future EVs")


class OptimizationRequest(BaseModel):
    vehicles: list[EVVehicle] = Field(..., min_length=1, max_length=200)
    num_slots: int = Field(gt=0, le=192, description="Number of 15-min time slots in horizon")
    slot_duration_hours: float = Field(default=0.25, description="Duration of each slot in hours")
    transformer_capacity_kw: float = Field(gt=0, description="Transformer power limit (kW)")
    base_load_per_slot_kw: list[float] = Field(..., description="Building base load per slot (kW)")
    predicted_future_arrivals: list[FutureArrival] = Field(default=[], description="ML-predicted future EV arrivals — optimizer reserves capacity for them")
    strategy: str = Field(default="optimal", pattern="^(optimal|fcfs|greedy)$")


class EVSchedule(BaseModel):
    ev_id: str
    power_per_slot_kw: list[float]
    energy_delivered_kwh: float
    energy_needed_kwh: float
    satisfaction_pct: float


class OptimizationResponse(BaseModel):
    strategy: str
    schedules: list[EVSchedule]
    total_energy_delivered_kwh: float
    total_energy_needed_kwh: float
    overall_satisfaction_pct: float
    peak_load_kw: float
    overload_slots: int
    transformer_utilization_per_slot: list[float]


class GridValidationRequest(BaseModel):
    total_load_per_slot_kw: list[float]
    transformer_capacity_kw: float
    num_charger_nodes: int = Field(default=20)
    transformer_kva: float = Field(default=500.0)


class GridValidationResponse(BaseModel):
    feasible: bool
    max_transformer_loading_pct: float
    min_bus_voltage_pu: float
    max_line_current_a: float
    overload_minutes: float
    warnings: list[str]
