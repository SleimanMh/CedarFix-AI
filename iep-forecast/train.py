"""
Training script for the IEP demand forecast models.

Trains three GradientBoostingRegressor models:
  - forecast_model   : mean prediction
  - forecast_lower   : quantile 0.10 (lower confidence interval)
  - forecast_upper   : quantile 0.90 (upper confidence interval)

Run from repo root:
    python3 iep-forecast/train.py
"""

import json
import os
from pathlib import Path

import joblib
import mlflow
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "data" / "processed" / "demand_train.parquet"
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(parents=True, exist_ok=True)

FEATURE_LIST_PATH = MODELS_DIR / "feature_list.json"
MODEL_MEAN_PATH = MODELS_DIR / "forecast_model.joblib"
MODEL_LOWER_PATH = MODELS_DIR / "forecast_lower.joblib"
MODEL_UPPER_PATH = MODELS_DIR / "forecast_upper.joblib"

FORECAST_FEATURES = [
    "hour_sin",
    "hour_cos",
    "dow_sin",
    "dow_cos",
    "month_sin",
    "month_cos",
    "is_weekend",
    "is_summer",
    "slot_of_day",
    "lag_4",
    "lag_16",
    "lag_96",
    "lag_672",
    "rolling_mean_1h",
    "rolling_std_1h",
]
TARGET = "total_kw"

# ---------------------------------------------------------------------------
# GBR hyperparameters
# ---------------------------------------------------------------------------
GBR_PARAMS = {
    "n_estimators": 200,
    "max_depth": 5,
    "learning_rate": 0.05,
}

MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "./mlruns")


def load_data() -> tuple[pd.DataFrame, pd.Series]:
    """Load parquet, drop NaN rows introduced by lag/rolling features."""
    df = pd.read_parquet(DATA_PATH)
    df = df[FORECAST_FEATURES + [TARGET]].dropna()
    X = df[FORECAST_FEATURES]
    y = df[TARGET]
    return X, y


def train_models(X: pd.DataFrame, y: pd.Series):
    """Train mean and quantile GBR models, log to MLflow, save to disk."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment("iep-forecast")

    with mlflow.start_run(run_name="gbr_training"):
        # --- Mean model ---
        model_mean = GradientBoostingRegressor(**GBR_PARAMS, random_state=42)
        model_mean.fit(X, y)

        # --- Quantile models ---
        model_lower = GradientBoostingRegressor(
            loss="quantile", alpha=0.1, **GBR_PARAMS, random_state=42
        )
        model_lower.fit(X, y)

        model_upper = GradientBoostingRegressor(
            loss="quantile", alpha=0.9, **GBR_PARAMS, random_state=42
        )
        model_upper.fit(X, y)

        # --- Metrics on training set (mean model) ---
        y_pred_train = model_mean.predict(X)
        train_mae = mean_absolute_error(y, y_pred_train)
        train_rmse = np.sqrt(mean_squared_error(y, y_pred_train))

        # --- MLflow logging ---
        mlflow.log_params(GBR_PARAMS)
        mlflow.log_metric("train_mae", train_mae)
        mlflow.log_metric("train_rmse", train_rmse)

        print(f"[train] rows={len(X):,}  train_mae={train_mae:.4f}  train_rmse={train_rmse:.4f}")

        # --- Persist models ---
        joblib.dump(model_mean, MODEL_MEAN_PATH)
        joblib.dump(model_lower, MODEL_LOWER_PATH)
        joblib.dump(model_upper, MODEL_UPPER_PATH)

        with open(FEATURE_LIST_PATH, "w") as fh:
            json.dump(FORECAST_FEATURES, fh, indent=2)

        metrics_path = MODELS_DIR / "metrics.json"
        with open(metrics_path, "w") as fh:
            json.dump({"mae": round(float(train_mae), 4), "rmse": round(float(train_rmse), 4)}, fh, indent=2)

        print(f"[train] Models saved to {MODELS_DIR}")


if __name__ == "__main__":
    X, y = load_data()
    train_models(X, y)
