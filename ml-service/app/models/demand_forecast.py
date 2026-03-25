"""Demand forecasting inference — loads trained XGBoost models and predicts."""

import pickle
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from app.config import ARTIFACTS_DIR


_models = None


def load_demand_models():
    global _models
    model_path = ARTIFACTS_DIR / "demand_model.pkl"
    if not model_path.exists():
        raise FileNotFoundError(f"Demand model not found at {model_path}")
    with open(model_path, "rb") as f:
        _models = pickle.load(f)
    return _models


def _cyclical(value: float, period: float) -> tuple[float, float]:
    angle = 2 * np.pi * value / period
    return float(np.sin(angle)), float(np.cos(angle))


def predict_demand(
    current_time: datetime,
    horizon_windows: int,
    recent_arrivals: list[int],
    recent_kwh: list[float],
) -> list[dict]:
    """
    Predict arrival count and energy demand for the next N 30-min windows.
    """
    if _models is None:
        raise RuntimeError("Demand models not loaded")

    results = []
    # Pad recent history if insufficient
    arrivals = list(recent_arrivals) + [0] * 48
    kwh_hist = list(recent_kwh) + [0.0] * 48

    for step in range(horizon_windows):
        window_start = current_time + timedelta(minutes=30 * step)
        hour = window_start.hour + window_start.minute / 60
        dow = window_start.weekday()
        month = window_start.month

        hour_sin, hour_cos = _cyclical(hour, 24)
        dow_sin, dow_cos = _cyclical(dow, 7)
        month_sin, month_cos = _cyclical(month, 12)
        is_weekend = 1 if dow >= 5 else 0

        # Lag features from provided history (index 0 = most recent)
        lag_1 = arrivals[step] if step < len(recent_arrivals) else 0
        lag_2 = arrivals[step + 1] if (step + 1) < len(recent_arrivals) else 0
        lag_48 = arrivals[step + 47] if (step + 47) < len(recent_arrivals) else 0
        lag_kwh_1 = kwh_hist[step] if step < len(recent_kwh) else 0.0
        lag_kwh_48 = kwh_hist[step + 47] if (step + 47) < len(recent_kwh) else 0.0

        # Rolling means from available history
        window_arrivals = arrivals[step:step + 6]
        rolling_6 = np.mean(window_arrivals) if window_arrivals else 0
        window_arrivals_48 = arrivals[step:step + 48]
        rolling_48 = np.mean(window_arrivals_48) if window_arrivals_48 else 0
        window_kwh_6 = kwh_hist[step:step + 6]
        rolling_kwh_6 = np.mean(window_kwh_6) if window_kwh_6 else 0

        features = np.array([[
            hour_sin, hour_cos, dow_sin, dow_cos, is_weekend,
            month_sin, month_cos,
            lag_1, lag_2, lag_48,
            lag_kwh_1, lag_kwh_48,
            rolling_6, rolling_48, rolling_kwh_6,
        ]])

        pred_arrivals = float(_models["arrival_count"].predict(features)[0])
        pred_kwh = float(_models["total_kwh"].predict(features)[0])

        results.append({
            "window_start": window_start,
            "predicted_arrivals": max(0, pred_arrivals),
            "predicted_kwh": max(0, pred_kwh),
        })

    return results
