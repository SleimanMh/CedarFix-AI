"""
IEP Demand Forecast FastAPI service.

Endpoints:
  POST /forecast          – run demand forecast for one or more feature slots
  POST /forecast/horizon  – forecast using current time + horizon + recent history
  GET  /health            – liveness / readiness probe

Run from iep-forecast directory (or repo root with the cd wrapper):
    cd iep-forecast && uvicorn main:app --host 0.0.0.0 --port 8001
"""

import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import mlflow
import numpy as np
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator
from metrics import (
    setup_metrics,
    ev_forecast_predicted_kw,
    ev_forecast_confidence_width,
    ev_forecast_n_slots,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
MODELS_DIR = Path(__file__).parent / "models"
FEATURE_LIST_PATH = MODELS_DIR / "feature_list.json"
MODEL_MEAN_PATH = MODELS_DIR / "forecast_model.joblib"
MODEL_LOWER_PATH = MODELS_DIR / "forecast_lower.joblib"
MODEL_UPPER_PATH = MODELS_DIR / "forecast_upper.joblib"

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "./mlruns")

# ---------------------------------------------------------------------------
# Module-level state (populated at startup)
# ---------------------------------------------------------------------------
model_mean = None
model_lower = None
model_upper = None
feature_list: list[str] = []
models_loaded: bool = False

# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Load models on startup."""
    _load_models()
    yield


app = FastAPI(title="IEP Demand Forecast Service", version="1.0", lifespan=lifespan)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow all origins for development
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)
setup_metrics(app, "iep-forecast")


def _load_models() -> None:
    """Load all three GBR models and the feature list from disk."""
    global model_mean, model_lower, model_upper, feature_list, models_loaded

    try:
        import joblib  # imported here to keep top-level imports lightweight

        if not (MODEL_MEAN_PATH.exists() and MODEL_LOWER_PATH.exists() and MODEL_UPPER_PATH.exists()):
            raise FileNotFoundError("One or more model files are missing.")

        model_mean = joblib.load(MODEL_MEAN_PATH)
        model_lower = joblib.load(MODEL_LOWER_PATH)
        model_upper = joblib.load(MODEL_UPPER_PATH)

        with open(FEATURE_LIST_PATH) as fh:
            feature_list = json.load(fh)

        models_loaded = True
        print(f"[startup] Models loaded from {MODELS_DIR}")
    except Exception as exc:
        models_loaded = False
        print(f"[startup] WARNING – models not loaded: {exc}")


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class ForecastRequest(BaseModel):
    slots: list[dict[str, Any]]

    @model_validator(mode="after")
    def validate_slots(self) -> "ForecastRequest":
        required = set(feature_list) if feature_list else set()
        if not required:
            # Feature list not yet available (models not loaded); will be
            # caught at request time instead.
            return self
        for i, slot in enumerate(self.slots):
            missing = required - set(slot.keys())
            if missing:
                raise ValueError(
                    f"Slot {i} is missing required features: {sorted(missing)}"
                )
        return self


class SlotPrediction(BaseModel):
    slot_index: int
    predicted_kw: float
    lower_ci: float
    upper_ci: float


class ForecastResponse(BaseModel):
    predictions: list[SlotPrediction]
    model_version: str
    n_slots: int


class HorizonForecastRequest(BaseModel):
    current_time: datetime
    horizon_slots: int = Field(default=8, ge=1, le=192)
    recent_kw: list[float] = Field(
        default_factory=list,
        description="Recent EV load history in kW (most recent first).",
    )
    autoregressive: bool = Field(
        default=True,
        description="When true, feed each predicted slot back as future lag history.",
    )


class HorizonSlotPrediction(BaseModel):
    slot_index: int
    slot_start: datetime
    predicted_kw: float
    lower_ci: float
    upper_ci: float


class HorizonForecastResponse(BaseModel):
    predictions: list[HorizonSlotPrediction]
    model_version: str
    n_slots: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _to_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _cyclical(value: float, period: float) -> tuple[float, float]:
    angle = 2 * np.pi * value / period
    return float(np.sin(angle)), float(np.cos(angle))


def _feature_row_for_timestamp(ts: datetime, history_kw: list[float]) -> dict[str, float]:
    """
    Build a feature row for one forecast slot.

    The model was trained with 15-minute lags. For horizon mode we map:
      - lag_4   = 1 hour back
      - lag_16  = 4 hours back
      - lag_96  = 24 hours back
      - lag_672 = 7 days back
    """
    hour = ts.hour + ts.minute / 60
    dow = ts.weekday()
    month = ts.month

    hour_sin, hour_cos = _cyclical(hour, 24)
    dow_sin, dow_cos = _cyclical(dow, 7)
    month_sin, month_cos = _cyclical(month, 12)

    # Build with zeros first to tolerate future feature-list changes.
    row = {name: 0.0 for name in feature_list}

    def lag(slots_back: int) -> float:
        idx = slots_back - 1
        if idx < len(history_kw):
            return float(history_kw[idx])
        return 0.0

    last_hour = history_kw[:4]  # 4 * 15min = 1 hour
    rolling_mean_1h = float(np.mean(last_hour)) if last_hour else 0.0
    rolling_std_1h = float(np.std(last_hour)) if last_hour else 0.0

    values = {
        "hour_sin": hour_sin,
        "hour_cos": hour_cos,
        "dow_sin": dow_sin,
        "dow_cos": dow_cos,
        "month_sin": month_sin,
        "month_cos": month_cos,
        "is_weekend": float(int(dow >= 5)),
        "is_summer": float(int(month in (6, 7, 8, 9))),
        "slot_of_day": float((ts.hour * 60 + ts.minute) // 15),
        "lag_4": lag(4),
        "lag_16": lag(16),
        "lag_96": lag(96),
        "lag_672": lag(672),
        "rolling_mean_1h": rolling_mean_1h,
        "rolling_std_1h": rolling_std_1h,
    }

    for key, value in values.items():
        if key in row:
            row[key] = value

    return row


def _predict_rows(rows: list[dict[str, float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    X = np.array([[row[f] for f in feature_list] for row in rows], dtype=float)
    preds_mean = model_mean.predict(X)
    preds_lower = model_lower.predict(X)
    preds_upper = model_upper.predict(X)
    return preds_mean, preds_lower, preds_upper


def _log_inference(preds_mean: np.ndarray, preds_lower: np.ndarray, preds_upper: np.ndarray, n_slots: int) -> None:
    # Log inference metrics to MLflow (non-blocking best-effort)
    try:
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment("iep-forecast-inference")
        with mlflow.start_run(run_name="inference"):
            mlflow.log_metric("n_slots", n_slots)
            mlflow.log_metric("mean_predicted_kw", float(np.mean(preds_mean)))
    except Exception as exc:
        print(f"[inference] MLflow logging failed (non-fatal): {exc}")

    # Update Prometheus gauges
    ev_forecast_predicted_kw.set(float(np.mean(preds_mean)))
    ev_forecast_confidence_width.set(float(np.mean(preds_upper - preds_lower)))
    ev_forecast_n_slots.set(n_slots)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health")
def health() -> dict:
    return {"status": "ok", "models_loaded": models_loaded}


@app.post("/models/reload")
def reload_models():
    """Hot-reload model files from disk (called after governance retrain)."""
    _load_models()
    if not models_loaded:
        raise HTTPException(status_code=500, detail="Model reload failed.")
    return {"status": "reloaded", "models_loaded": models_loaded}


@app.post("/forecast", response_model=ForecastResponse)
def forecast(request: ForecastRequest) -> ForecastResponse:
    if not models_loaded:
        raise HTTPException(status_code=503, detail="Models are not loaded.")

    if not request.slots:
        return ForecastResponse(n_slots=0, predictions=[], model_version="1.0")

    try:
        preds_mean, preds_lower, preds_upper = _predict_rows(request.slots)
    except KeyError as exc:
        raise HTTPException(status_code=422, detail=f"Missing feature in slot: {exc}") from exc

    predictions = [
        SlotPrediction(
            slot_index=i,
            predicted_kw=round(float(preds_mean[i]), 4),
            lower_ci=round(float(preds_lower[i]), 4),
            upper_ci=round(float(preds_upper[i]), 4),
        )
        for i in range(len(request.slots))
    ]

    _log_inference(preds_mean, preds_lower, preds_upper, len(request.slots))

    return ForecastResponse(
        predictions=predictions,
        model_version="1.0",
        n_slots=len(request.slots),
    )


@app.post("/forecast/horizon", response_model=HorizonForecastResponse)
def forecast_horizon(request: HorizonForecastRequest) -> HorizonForecastResponse:
    """
    Convenience endpoint that mirrors a "current_time + horizon + recent history" API.
    Useful when the caller doesn't want to pre-engineer slot-level feature dictionaries.
    """
    if not models_loaded:
        raise HTTPException(status_code=503, detail="Models are not loaded.")

    current_time = _to_utc(request.current_time)
    # Keep most-recent-first ordering; coerce values to floats and cap history.
    history_kw = [float(v) for v in request.recent_kw][:672]

    predictions: list[HorizonSlotPrediction] = []
    preds_mean: list[float] = []
    preds_lower: list[float] = []
    preds_upper: list[float] = []

    for i in range(request.horizon_slots):
        slot_start = current_time + timedelta(minutes=15 * i)
        row = _feature_row_for_timestamp(slot_start, history_kw)
        pm, pl, pu = _predict_rows([row])

        mean_v = float(pm[0])
        lower_v = float(pl[0])
        upper_v = float(pu[0])

        predictions.append(
            HorizonSlotPrediction(
                slot_index=i,
                slot_start=slot_start,
                predicted_kw=round(mean_v, 4),
                lower_ci=round(lower_v, 4),
                upper_ci=round(upper_v, 4),
            )
        )
        preds_mean.append(mean_v)
        preds_lower.append(lower_v)
        preds_upper.append(upper_v)

        if request.autoregressive:
            history_kw.insert(0, mean_v)
            if len(history_kw) > 672:
                history_kw = history_kw[:672]

    _log_inference(
        np.array(preds_mean, dtype=float),
        np.array(preds_lower, dtype=float),
        np.array(preds_upper, dtype=float),
        len(predictions),
    )

    return HorizonForecastResponse(
        predictions=predictions,
        model_version="1.0",
        n_slots=len(predictions),
    )
