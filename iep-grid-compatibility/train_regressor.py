"""
Max-Chargers Regressor — Stage 2
==================================
Predicts recommended_max_active_chargers for scenarios where a meaningful
recommendation exists (compatibility_class != not_compatible).

Design rationale:
  77.6% of all rows have recommended_max_active_chargers == 0 because the
  grid is simply incompatible. Including those rows would make regression
  trivially predict ~0 for everything. Instead we:
    1. Filter to compatible + conditional rows only (~3,700 rows).
    2. Regress on recommended_max_active_chargers within that subset.

  In production: run Stage 1 first. If class == not_compatible, skip Stage 2
  and return 0. Otherwise call Stage 2 for the exact recommendation.

Target:  recommended_max_active_chargers  (integer 0–20, treated as float)
Features: same config-only features as Stage 1

Usage:
    python iep-grid-compatibility/train_regressor.py
    python iep-grid-compatibility/train_regressor.py --data data/raw/simulation_dataset_final.csv
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from xgboost import XGBRegressor
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DEFAULT_DATA = ROOT / "data" / "raw" / "simulation_dataset_final.csv"
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

# ── Feature definition (identical to classifier — same config inputs) ─────────
NUMERIC_FEATURES = [
    "transformer_kva",
    "base_load_kw",
    "feeder_length_km",
    "r1", "x1", "r0", "x0",
    "num_chargers_installed",
    "num_chargers_active",
    "charger_power_kw",
    "nominal_load_ratio",
    "nominal_headroom_kw",
]
CATEGORICAL_FEATURES = [
    "cable_type",
    "phase_balance_class",
]
TARGET = "recommended_max_active_chargers"
COMPATIBILITY_COL = "compatibility_class"
# Only rows where a real recommendation exists
MEANINGFUL_CLASSES = {"compatible", "conditional"}


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Same engineered features as train_classifier.py."""
    df = df.copy()
    total_charger_kw = df["num_chargers_active"] * df["charger_power_kw"]
    df["nominal_load_ratio"] = (df["base_load_kw"] + total_charger_kw) / df["transformer_kva"]
    df["nominal_headroom_kw"] = df["transformer_kva"] - df["base_load_kw"] - total_charger_kw
    return df


def build_pipeline(use_xgboost: bool = False) -> Pipeline:
    """Builds a sklearn Pipeline with preprocessing + regressor."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
             CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )

    if use_xgboost and XGBOOST_AVAILABLE:
        print("Using XGBRegressor")
        regressor = XGBRegressor(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbosity=0,
        )
    else:
        print("Using RandomForestRegressor")
        regressor = RandomForestRegressor(
            n_estimators=300,
            max_depth=None,
            random_state=42,
            n_jobs=-1,
        )

    return Pipeline([
        ("preprocessor", preprocessor),
        ("regressor", regressor),
    ])


def main(data_path: Path, use_xgboost: bool) -> None:
    # ── Load ──────────────────────────────────────────────────────────────────
    print(f"Loading {data_path} ...")
    df = pd.read_csv(data_path)
    print(f"  Full dataset: {len(df):,} rows")

    # ── Engineer features ─────────────────────────────────────────────────────
    df = engineer_features(df)

    # ── Filter to meaningful rows ─────────────────────────────────────────────
    df_stage2 = df[df[COMPATIBILITY_COL].isin(MEANINGFUL_CLASSES)].copy()
    print(f"  After filtering to {MEANINGFUL_CLASSES}: {len(df_stage2):,} rows")

    print("\nTarget distribution (filtered rows):")
    vc = df_stage2[TARGET].value_counts().sort_index()
    for val, count in vc.items():
        print(f"  max_chargers={val:<3}  {count:>5,}  ({100*count/len(df_stage2):.1f}%)")

    # ── Split ─────────────────────────────────────────────────────────────────
    X = df_stage2[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df_stage2[TARGET].astype(float)

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    print(f"\nTrain: {len(X_train):,}  Test: {len(X_test):,}")

    # ── Train ─────────────────────────────────────────────────────────────────
    print("\nTraining ...")
    pipeline = build_pipeline(use_xgboost=use_xgboost)
    pipeline.fit(X_train, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    y_pred_raw = pipeline.predict(X_test)
    # Round and clip to valid range [0, max observed]
    max_chargers = int(df_stage2[TARGET].max())
    y_pred = np.clip(np.round(y_pred_raw), 0, max_chargers)

    mae  = mean_absolute_error(y_test, y_pred)
    rmse = np.sqrt(mean_squared_error(y_test, y_pred))
    r2   = r2_score(y_test, y_pred)

    print("\n=== Regression Metrics ===")
    print(f"  MAE:  {mae:.4f}  chargers")
    print(f"  RMSE: {rmse:.4f}  chargers")
    print(f"  R²:   {r2:.4f}")

    # Error distribution
    errors = np.abs(y_test.values - y_pred)
    print("\n=== Absolute Error Distribution ===")
    for threshold in [0, 1, 2, 3]:
        pct = 100 * (errors <= threshold).mean()
        print(f"  Within {threshold} charger(s): {pct:.1f}%")

    # Predicted vs actual sample
    print("\n=== Sample predictions (first 10 test rows) ===")
    comparison = pd.DataFrame({
        "actual":    y_test.values[:10].astype(int),
        "predicted": y_pred[:10].astype(int),
        "error":     errors[:10].astype(int),
    })
    print(comparison.to_string(index=False))

    # ── Feature importances ───────────────────────────────────────────────────
    reg = pipeline.named_steps["regressor"]
    if hasattr(reg, "feature_importances_"):
        pre = pipeline.named_steps["preprocessor"]
        cat_cols = (pre.named_transformers_["cat"]
                    .get_feature_names_out(CATEGORICAL_FEATURES).tolist())
        all_feature_names = NUMERIC_FEATURES + cat_cols
        importances = pd.Series(reg.feature_importances_, index=all_feature_names)
        print("\n=== Top 10 Feature Importances ===")
        print(importances.sort_values(ascending=False).head(10).round(4).to_string())

    # ── Save ──────────────────────────────────────────────────────────────────
    model_path = MODELS_DIR / "max_chargers_regressor.joblib"
    joblib.dump(pipeline, model_path)
    print(f"\nModel saved: {model_path}")

    metrics = {
        "mae":  round(float(mae), 4),
        "rmse": round(float(rmse), 4),
        "r2":   round(float(r2), 4),
        "train_rows": int(len(X_train)),
        "test_rows":  int(len(X_test)),
        "max_chargers_range": [0, max_chargers],
        "filter": f"compatibility_class in {sorted(MEANINGFUL_CLASSES)}",
        "features_numeric": NUMERIC_FEATURES,
        "features_categorical": CATEGORICAL_FEATURES,
        "model": "XGBRegressor" if (use_xgboost and XGBOOST_AVAILABLE)
                 else "RandomForestRegressor",
    }
    metrics_path = MODELS_DIR / "regressor_metrics.json"
    with open(metrics_path, "w") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Metrics saved: {metrics_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train max-chargers regressor (Stage 2)")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="Path to simulation_dataset_final.csv")
    parser.add_argument("--xgboost", action="store_true",
                        help="Use XGBoost instead of RandomForest")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"ERROR: Data file not found: {args.data}", file=sys.stderr)
        sys.exit(1)

    main(args.data, use_xgboost=args.xgboost)
