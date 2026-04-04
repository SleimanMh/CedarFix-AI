"""
Compatibility Classifier — Stage 1
====================================
Predicts compatibility_class from grid configuration inputs only.
No OpenDSS simulation outputs are used as features (no data leakage).

Target:  compatibility_class  {not_compatible, conditional, compatible}
Features: transformer config + cable specs + charger config + engineered ratio

Usage:
    python iep-grid-compatibility/train_classifier.py
    python iep-grid-compatibility/train_classifier.py --data data/raw/simulation_dataset_final.csv
"""

import argparse
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

try:
    from xgboost import XGBClassifier
    XGBOOST_AVAILABLE = True
except ImportError:
    XGBOOST_AVAILABLE = False

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
DEFAULT_DATA = ROOT / "data" / "raw" / "simulation_dataset_final.csv"
MODELS_DIR = Path(__file__).parent / "models"
MODELS_DIR.mkdir(exist_ok=True)

# ── Feature definition ────────────────────────────────────────────────────────
# ONLY columns knowable before running any simulation.
# r1/x1/r0/x0 are included — they are cable impedance constants,
# not simulation outputs. Tree models down-weight redundant features.
NUMERIC_FEATURES = [
    "transformer_kva",
    "base_load_kw",
    "feeder_length_km",
    "r1", "x1", "r0", "x0",
    "num_chargers_installed",
    "num_chargers_active",
    "charger_power_kw",
    "nominal_load_ratio",      # engineered — see engineer_features()
    "nominal_headroom_kw",     # engineered — see engineer_features()
]
CATEGORICAL_FEATURES = [
    "cable_type",              # A_strong / B_medium / C_weak
    "phase_balance_class",     # balanced / mildly_unbalanced / heavily_unbalanced
]
TARGET = "compatibility_class"
# Class ordering for confusion matrix readability
CLASS_ORDER = ["compatible", "conditional", "not_compatible"]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add config-computable features that require no simulation.

    nominal_load_ratio:
        (base_load + total charger demand) / transformer capacity
        Values > 1.0 almost always mean overload.

    nominal_headroom_kw:
        How much transformer capacity is left after base load and all chargers.
        Negative = certain overload.
    """
    df = df.copy()
    total_charger_kw = df["num_chargers_active"] * df["charger_power_kw"]
    df["nominal_load_ratio"] = (df["base_load_kw"] + total_charger_kw) / df["transformer_kva"]
    df["nominal_headroom_kw"] = df["transformer_kva"] - df["base_load_kw"] - total_charger_kw
    return df


def build_pipeline(use_xgboost: bool = False) -> Pipeline:
    """Builds a sklearn Pipeline with preprocessing + classifier."""
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            ("cat", OneHotEncoder(handle_unknown="ignore", sparse_output=False),
             CATEGORICAL_FEATURES),
        ],
        remainder="drop",
    )

    if use_xgboost and XGBOOST_AVAILABLE:
        print("Using XGBClassifier")
        # XGBoost handles class imbalance via scale_pos_weight but for
        # multi-class the simplest equivalent is sample_weight at fit time.
        # We use RF-style class_weight workaround: pass scale via fit params.
        classifier = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.1,
            subsample=0.8,
            colsample_bytree=0.8,
            eval_metric="mlogloss",
            random_state=42,
            verbosity=0,
        )
    else:
        print("Using RandomForestClassifier")
        classifier = RandomForestClassifier(
            n_estimators=300,
            max_depth=None,
            class_weight="balanced",   # handles 90/6/4 imbalance
            random_state=42,
            n_jobs=-1,
        )

    return Pipeline([
        ("preprocessor", preprocessor),
        ("classifier", classifier),
    ])


def print_confusion_matrix(cm: np.ndarray, labels: list) -> None:
    """Pretty-print a labelled confusion matrix."""
    col_width = max(len(l) for l in labels) + 2
    header = "Actual \\ Predicted".ljust(col_width)
    header += "  ".join(l.center(col_width) for l in labels)
    print(header)
    for i, row_label in enumerate(labels):
        row = row_label.ljust(col_width)
        row += "  ".join(str(v).center(col_width) for v in cm[i])
        print(row)


def main(data_path: Path, use_xgboost: bool) -> None:
    # ── Load ──────────────────────────────────────────────────────────────────
    print(f"Loading {data_path} ...")
    df = pd.read_csv(data_path)
    print(f"  Rows: {len(df):,}  Columns: {len(df.columns)}")

    # ── Engineer features ─────────────────────────────────────────────────────
    df = engineer_features(df)

    # ── Class distribution ────────────────────────────────────────────────────
    print("\nClass distribution:")
    vc = df[TARGET].value_counts()
    for cls, count in vc.items():
        print(f"  {cls:<20} {count:>6,}  ({100*count/len(df):.1f}%)")

    # ── Split ─────────────────────────────────────────────────────────────────
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )
    print(f"\nTrain: {len(X_train):,}  Test: {len(X_test):,}")

    # ── Train ─────────────────────────────────────────────────────────────────
    print("\nTraining ...")
    pipeline = build_pipeline(use_xgboost=use_xgboost)

    if use_xgboost and XGBOOST_AVAILABLE:
        # Compute per-sample weights to handle class imbalance for XGBoost
        class_counts = y_train.value_counts().to_dict()
        total = len(y_train)
        weight_map = {cls: total / (len(class_counts) * cnt)
                      for cls, cnt in class_counts.items()}
        sample_weights = y_train.map(weight_map).values
        pipeline.fit(X_train, y_train,
                     classifier__sample_weight=sample_weights)
    else:
        pipeline.fit(X_train, y_train)

    # ── Evaluate ──────────────────────────────────────────────────────────────
    y_pred = pipeline.predict(X_test)

    print("\n=== Classification Report ===")
    print(classification_report(y_test, y_pred, target_names=CLASS_ORDER,
                                 labels=CLASS_ORDER, digits=3))

    macro_f1 = f1_score(y_test, y_pred, average="macro",
                        labels=CLASS_ORDER)
    print(f"Macro F1: {macro_f1:.4f}")

    print("\n=== Confusion Matrix (rows=actual, cols=predicted) ===")
    cm = confusion_matrix(y_test, y_pred, labels=CLASS_ORDER)
    print_confusion_matrix(cm, CLASS_ORDER)

    # ── Feature importances ───────────────────────────────────────────────────
    clf = pipeline.named_steps["classifier"]
    if hasattr(clf, "feature_importances_"):
        pre = pipeline.named_steps["preprocessor"]
        cat_cols = (pre.named_transformers_["cat"]
                    .get_feature_names_out(CATEGORICAL_FEATURES).tolist())
        all_feature_names = NUMERIC_FEATURES + cat_cols
        importances = pd.Series(clf.feature_importances_, index=all_feature_names)
        print("\n=== Top 10 Feature Importances ===")
        print(importances.sort_values(ascending=False).head(10).round(4).to_string())

    # ── Save ──────────────────────────────────────────────────────────────────
    model_path = MODELS_DIR / "compatibility_classifier.joblib"
    joblib.dump(pipeline, model_path)
    print(f"\nModel saved: {model_path}")

    metrics = {
        "macro_f1": round(float(macro_f1), 4),
        "train_rows": int(len(X_train)),
        "test_rows": int(len(X_test)),
        "classes": CLASS_ORDER,
        "features_numeric": NUMERIC_FEATURES,
        "features_categorical": CATEGORICAL_FEATURES,
        "model": "XGBClassifier" if (use_xgboost and XGBOOST_AVAILABLE)
                 else "RandomForestClassifier",
    }
    metrics_path = MODELS_DIR / "classifier_metrics.json"
    with open(metrics_path, "w") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"Metrics saved: {metrics_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train compatibility classifier")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA,
                        help="Path to simulation_dataset_final.csv")
    parser.add_argument("--xgboost", action="store_true",
                        help="Use XGBoost instead of RandomForest")
    args = parser.parse_args()

    if not args.data.exists():
        print(f"ERROR: Data file not found: {args.data}", file=sys.stderr)
        sys.exit(1)

    main(args.data, use_xgboost=args.xgboost)
