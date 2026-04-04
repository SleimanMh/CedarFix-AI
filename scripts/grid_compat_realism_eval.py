"""
Grid Compatibility Realism Evaluation
====================================
Stricter evaluation than a simple random split:

1) Random stratified holdout (baseline)
2) Leave-one-transformer-size-out (OOD)
3) Leave-one-cable-type-out (OOD)
4) Leave-one-phase-balance-out (OOD)
5) Baseline hard-zone metrics by nominal load ratio bins

Run:
    python tests/grid_compat_realism_eval.py
    python tests/grid_compat_realism_eval.py --estimators 200
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_recall_fscore_support
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DATA = ROOT / "data" / "raw" / "simulation_dataset_final.csv"
DEFAULT_OUT = ROOT / "data" / "grid_compat_realism_report.json"

CLASS_ORDER = ["compatible", "conditional", "not_compatible"]
TARGET = "compatibility_class"

NUMERIC_FEATURES = [
    "transformer_kva",
    "base_load_kw",
    "feeder_length_km",
    "r1",
    "x1",
    "r0",
    "x0",
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

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    total_charger_kw = out["num_chargers_active"] * out["charger_power_kw"]
    out["nominal_load_ratio"] = (out["base_load_kw"] + total_charger_kw) / out["transformer_kva"]
    out["nominal_headroom_kw"] = out["transformer_kva"] - out["base_load_kw"] - total_charger_kw
    return out


def build_pipeline(n_estimators: int, seed: int) -> Pipeline:
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", StandardScaler(), NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", sparse_output=False),
                CATEGORICAL_FEATURES,
            ),
        ],
        remainder="drop",
    )
    clf = RandomForestClassifier(
        n_estimators=n_estimators,
        random_state=seed,
        class_weight="balanced",
        n_jobs=1,  # keep compatible with restricted runtime envs
    )
    return Pipeline([("preprocessor", preprocessor), ("classifier", clf)])


def compute_metrics(
    y_true: pd.Series, y_pred: np.ndarray, present_only: bool = False
) -> dict[str, Any]:
    labels = (
        sorted(set(pd.Series(y_true).astype(str).tolist()) | set(pd.Series(y_pred).astype(str).tolist()))
        if present_only
        else CLASS_ORDER
    )
    accuracy = float(accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0))

    p, r, f1, support = precision_recall_fscore_support(
        y_true,
        y_pred,
        labels=CLASS_ORDER,
        zero_division=0,
    )
    per_class = {
        cls: {
            "precision": float(p[i]),
            "recall": float(r[i]),
            "f1": float(f1[i]),
            "support": int(support[i]),
        }
        for i, cls in enumerate(CLASS_ORDER)
    }

    cm = confusion_matrix(y_true, y_pred, labels=CLASS_ORDER).tolist()

    return {
        "accuracy": accuracy,
        "macro_f1": macro_f1,
        "per_class": per_class,
        "confusion_matrix": cm,
    }


def evaluate_random_baseline(
    df: pd.DataFrame, n_estimators: int, seed: int
) -> tuple[dict[str, Any], Pipeline, pd.DataFrame]:
    X = df[ALL_FEATURES]
    y = df[TARGET]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=seed, stratify=y
    )
    model = build_pipeline(n_estimators=n_estimators, seed=seed)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    metrics = compute_metrics(y_test, y_pred)
    metrics["train_rows"] = int(len(X_train))
    metrics["test_rows"] = int(len(X_test))

    test_eval = X_test.copy()
    test_eval[TARGET] = y_test.values
    test_eval["predicted"] = y_pred
    return metrics, model, test_eval


def evaluate_group_ood(
    df: pd.DataFrame, group_col: str, n_estimators: int, seed: int
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for holdout_value in sorted(df[group_col].unique().tolist()):
        train_df = df[df[group_col] != holdout_value]
        test_df = df[df[group_col] == holdout_value]
        if train_df.empty or test_df.empty:
            continue

        model = build_pipeline(n_estimators=n_estimators, seed=seed)
        model.fit(train_df[ALL_FEATURES], train_df[TARGET])
        y_pred = model.predict(test_df[ALL_FEATURES])
        m = compute_metrics(test_df[TARGET], y_pred)
        rows.append(
            {
                "group_col": group_col,
                "holdout_value": holdout_value,
                "test_rows": int(len(test_df)),
                "accuracy": m["accuracy"],
                "macro_f1": m["macro_f1"],
            }
        )
    return rows


def evaluate_load_ratio_bins(test_eval: pd.DataFrame) -> list[dict[str, Any]]:
    # Hard zones around overload boundary.
    bins = [
        ("<=0.8", -np.inf, 0.8),
        ("0.8-1.0", 0.8, 1.0),
        ("1.0-1.5", 1.0, 1.5),
        (">1.5", 1.5, np.inf),
    ]

    rows: list[dict[str, Any]] = []
    for label, lo, hi in bins:
        sub = test_eval[(test_eval["nominal_load_ratio"] > lo) & (test_eval["nominal_load_ratio"] <= hi)]
        if sub.empty:
            continue
        # In narrow bins, some classes may be absent; use present-only macro F1.
        m = compute_metrics(sub[TARGET], sub["predicted"].values, present_only=True)
        rows.append(
            {
                "load_ratio_bin": label,
                "rows": int(len(sub)),
                "accuracy": m["accuracy"],
                "macro_f1": m["macro_f1"],
            }
        )
    return rows


def summarize(rows: list[dict[str, Any]]) -> dict[str, float]:
    if not rows:
        return {"mean_accuracy": 0.0, "mean_macro_f1": 0.0, "worst_macro_f1": 0.0}
    accs = [r["accuracy"] for r in rows]
    f1s = [r["macro_f1"] for r in rows]
    return {
        "mean_accuracy": float(np.mean(accs)),
        "mean_macro_f1": float(np.mean(f1s)),
        "worst_macro_f1": float(np.min(f1s)),
    }


def print_table(title: str, rows: list[dict[str, Any]], key: str) -> None:
    print(f"\n=== {title} ===")
    if not rows:
        print("No rows")
        return
    for row in rows:
        print(
            f"  {key}={row[key]!s:<24} "
            f"rows={row.get('test_rows', row.get('rows', 0)):>6}  "
            f"acc={row['accuracy']:.4f}  macro_f1={row['macro_f1']:.4f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run stricter realism evaluation for grid compatibility")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA, help="Path to simulation dataset")
    parser.add_argument("--estimators", type=int, default=120, help="RandomForest n_estimators")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="JSON report output path")
    args = parser.parse_args()

    if not args.data.exists():
        raise FileNotFoundError(f"Dataset not found: {args.data}")

    print(f"Loading {args.data} ...")
    df = pd.read_csv(args.data)
    df = df[df[TARGET].isin(CLASS_ORDER)].copy()
    df = engineer_features(df)

    print(f"Rows: {len(df):,}")
    print("Class distribution:")
    vc = df[TARGET].value_counts()
    for cls in CLASS_ORDER:
        count = int(vc.get(cls, 0))
        print(f"  {cls:<16} {count:>7,} ({100*count/len(df):.1f}%)")

    print("\nTraining baseline split model ...")
    baseline, _, baseline_test_eval = evaluate_random_baseline(
        df=df, n_estimators=args.estimators, seed=args.seed
    )
    print(f"  baseline accuracy={baseline['accuracy']:.4f}  macro_f1={baseline['macro_f1']:.4f}")

    print("\nEvaluating OOD group holdouts ...")
    transformer_ood = evaluate_group_ood(df, "transformer_kva", args.estimators, args.seed)
    cable_ood = evaluate_group_ood(df, "cable_type", args.estimators, args.seed)
    phase_ood = evaluate_group_ood(df, "phase_balance_class", args.estimators, args.seed)
    load_ratio_bins = evaluate_load_ratio_bins(baseline_test_eval)

    print_table("OOD: Leave-one-transformer_kva-out", transformer_ood, "holdout_value")
    print_table("OOD: Leave-one-cable_type-out", cable_ood, "holdout_value")
    print_table("OOD: Leave-one-phase_balance_class-out", phase_ood, "holdout_value")
    print_table("Hard zones: nominal_load_ratio bins", load_ratio_bins, "load_ratio_bin")

    report = {
        "dataset_path": str(args.data),
        "rows": int(len(df)),
        "estimators": int(args.estimators),
        "seed": int(args.seed),
        "baseline_random_split": baseline,
        "ood_transformer_kva": {
            "rows": transformer_ood,
            "summary": summarize(transformer_ood),
        },
        "ood_cable_type": {
            "rows": cable_ood,
            "summary": summarize(cable_ood),
        },
        "ood_phase_balance_class": {
            "rows": phase_ood,
            "summary": summarize(phase_ood),
        },
        "hard_zone_load_ratio_bins": {
            "rows": load_ratio_bins,
            "summary": summarize(load_ratio_bins),
        },
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"\nSaved report: {args.out.resolve()}")


if __name__ == "__main__":
    main()
