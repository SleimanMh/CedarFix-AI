"""
Holdout evaluation script for the IEP demand forecast models.

Evaluates the saved forecast models on the true holdout dataset produced by
data/preprocess.py:
    data/processed/demand_holdout.parquet

This is intentionally separate from train.py so training behavior stays
unchanged. The goal is an honest post-training evaluation on unseen data,
not another training-set score.

Run from repo root:
    python iep-forecast/evaluate_holdout.py
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error


REPO_ROOT = Path(__file__).parent.parent
DATA_PATH = REPO_ROOT / "data" / "processed" / "demand_holdout.parquet"
MODELS_DIR = Path(__file__).parent / "models"

FEATURE_LIST_PATH = MODELS_DIR / "feature_list.json"
MODEL_MEAN_PATH = MODELS_DIR / "forecast_model.joblib"
MODEL_LOWER_PATH = MODELS_DIR / "forecast_lower.joblib"
MODEL_UPPER_PATH = MODELS_DIR / "forecast_upper.joblib"
ARTIFACT_PATH = MODELS_DIR / "holdout_metrics.json"

TARGET = "total_kw"


def load_holdout_frame() -> tuple[pd.DataFrame, list[str]]:
    """Load holdout parquet and align it to the persisted feature list."""
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Holdout dataset not found: {DATA_PATH}")
    if not FEATURE_LIST_PATH.exists():
        raise FileNotFoundError(f"Feature list not found: {FEATURE_LIST_PATH}")

    with open(FEATURE_LIST_PATH) as fh:
        feature_list: list[str] = json.load(fh)

    df = pd.read_parquet(DATA_PATH)
    required_columns = feature_list + [TARGET]
    missing = [column for column in required_columns if column not in df.columns]
    if missing:
        raise ValueError(f"Holdout dataset missing required columns: {missing}")

    return df, feature_list


def load_models() -> tuple[object, object, object]:
    """Load the persisted mean/lower/upper models."""
    for model_path in (MODEL_MEAN_PATH, MODEL_LOWER_PATH, MODEL_UPPER_PATH):
        if not model_path.exists():
            raise FileNotFoundError(f"Model file not found: {model_path}")

    return (
        joblib.load(MODEL_MEAN_PATH),
        joblib.load(MODEL_LOWER_PATH),
        joblib.load(MODEL_UPPER_PATH),
    )


def evaluate_holdout() -> dict:
    """Run the saved models on the holdout set and return honest metrics."""
    df_raw, feature_list = load_holdout_frame()
    raw_rows = int(len(df_raw))

    # Keep evaluation aligned with training: lag/rolling features introduce NaNs
    # at the boundaries, so score only rows with a complete feature vector.
    df = df_raw[feature_list + [TARGET]].dropna().copy()
    evaluated_rows = int(len(df))
    if evaluated_rows == 0:
        raise ValueError("No non-null holdout rows available for evaluation")

    X = df[feature_list]
    y = df[TARGET].to_numpy(dtype=float)

    model_mean, model_lower, model_upper = load_models()
    preds_mean = np.asarray(model_mean.predict(X), dtype=float)
    preds_lower = np.asarray(model_lower.predict(X), dtype=float)
    preds_upper = np.asarray(model_upper.predict(X), dtype=float)

    # Guard against lower/upper quantile crossing due to model error.
    lower = np.minimum(preds_lower, preds_upper)
    upper = np.maximum(preds_lower, preds_upper)

    mae = float(mean_absolute_error(y, preds_mean))
    rmse = float(np.sqrt(mean_squared_error(y, preds_mean)))

    within_interval = (y >= lower) & (y <= upper)
    below_interval = y < lower
    above_interval = y > upper
    interval_width = upper - lower

    slot_start_min = None
    slot_start_max = None
    if "slot_start" in df_raw.columns:
        holdout_slot_times = df_raw["slot_start"].dropna()
        if len(holdout_slot_times) > 0:
            slot_start_min = str(pd.Timestamp(holdout_slot_times.min()))
            slot_start_max = str(pd.Timestamp(holdout_slot_times.max()))

    metrics = {
        "dataset": str(DATA_PATH.relative_to(REPO_ROOT)).replace("\\", "/"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "raw_holdout_rows": raw_rows,
        "evaluated_rows": evaluated_rows,
        "feature_count": len(feature_list),
        "target": TARGET,
        "slot_start_min": slot_start_min,
        "slot_start_max": slot_start_max,
        "mae_kw": round(mae, 4),
        "rmse_kw": round(rmse, 4),
        "interval_coverage_pct": round(float(np.mean(within_interval) * 100.0), 2),
        "avg_interval_width_kw": round(float(np.mean(interval_width)), 4),
        "below_lower_count": int(np.sum(below_interval)),
        "above_upper_count": int(np.sum(above_interval)),
    }

    with open(ARTIFACT_PATH, "w") as fh:
        json.dump(metrics, fh, indent=2)

    return metrics


def main() -> None:
    metrics = evaluate_holdout()
    print(
        "[holdout] "
        f"rows={metrics['evaluated_rows']:,} "
        f"mae={metrics['mae_kw']:.4f} "
        f"rmse={metrics['rmse_kw']:.4f} "
        f"coverage={metrics['interval_coverage_pct']:.2f}% "
        f"width={metrics['avg_interval_width_kw']:.4f}"
    )
    print(f"[holdout] Metrics artifact saved to {ARTIFACT_PATH}")


if __name__ == "__main__":
    main()