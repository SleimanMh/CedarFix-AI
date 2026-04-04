"""
Grid Compatibility — Direct Model Accuracy Test
================================================
Loads the trained joblib models directly (no HTTP) and runs inference
on all rows from the OpenDSS dataset. Produces a full confusion matrix,
per-class metrics, and saves every row's prediction to CSV.

This is the fastest and most reliable accuracy verification — bypasses
network latency entirely, processes 40,000 rows in ~5 seconds.

Usage:
    python tests/grid_compat_accuracy.py
    python tests/grid_compat_accuracy.py --out data/grid_compat_sweep_results.csv
    python tests/grid_compat_accuracy.py --samples 5000
"""

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
MODELS_DIR = ROOT / "iep-grid-compatibility" / "models"
DATASET    = ROOT / "data" / "raw" / "simulation_dataset_final.csv"
DEFAULT_OUT = ROOT / "data" / "grid_compat_sweep_results.csv"

# Must match iep-grid-compatibility/main.py exactly
NUMERIC_FEATURES = [
    "transformer_kva", "base_load_kw", "feeder_length_km",
    "r1", "x1", "r0", "x0",
    "num_chargers_installed", "num_chargers_active", "charger_power_kw",
    "nominal_load_ratio", "nominal_headroom_kw",
]
CATEGORICAL_FEATURES = ["cable_type", "phase_balance_class"]
ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

CLASS_ORDER = ["compatible", "conditional", "not_compatible"]


def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    """Replicate the _engineer() logic from iep-grid-compatibility/main.py."""
    df = df.copy()
    total_charger_kw = df["num_chargers_active"] * df["charger_power_kw"]
    df["nominal_load_ratio"]  = (df["base_load_kw"] + total_charger_kw) / df["transformer_kva"]
    df["nominal_headroom_kw"] = df["transformer_kva"] - df["base_load_kw"] - total_charger_kw
    return df


def load_dataset(path: Path, n_samples: int | None) -> pd.DataFrame:
    print(f"Loading dataset: {path}")
    df = pd.read_csv(path)
    print(f"  Total rows: {len(df):,}")

    required = ["compatibility_class"] + NUMERIC_FEATURES[:10] + CATEGORICAL_FEATURES
    missing = [c for c in required if c not in df.columns]
    if missing:
        print(f"  ERROR: Missing columns: {missing}")
        sys.exit(1)

    df = df[df["compatibility_class"].isin(CLASS_ORDER)].copy()
    print(f"  Usable rows: {len(df):,}")

    dist = df["compatibility_class"].value_counts()
    for cls in CLASS_ORDER:
        print(f"    {cls:<18}: {dist.get(cls, 0):>6,} ({dist.get(cls,0)/len(df)*100:.1f}%)")

    if n_samples and n_samples < len(df):
        # Stratified: keep all minority classes, sample from not_compatible
        minority = df[df["compatibility_class"] != "not_compatible"]
        majority = df[df["compatibility_class"] == "not_compatible"].sample(
            n=min(n_samples, len(df[df["compatibility_class"] == "not_compatible"])),
            random_state=42
        )
        df = pd.concat([minority, majority]).sample(frac=1, random_state=42).reset_index(drop=True)
        print(f"\n  Stratified sample: {len(df):,} rows")

    return df


def run_inference(clf, reg, df: pd.DataFrame) -> pd.DataFrame:
    """Run both stages on the full DataFrame at once (vectorised)."""
    df = engineer_features(df)

    # Stage 1: classify
    print("\nRunning Stage 1 inference (classifier)...")
    t0 = datetime.now()
    pred_classes = clf.predict(df[ALL_FEATURES])
    proba        = clf.predict_proba(df[ALL_FEATURES])
    elapsed      = (datetime.now() - t0).total_seconds()
    print(f"  Done: {len(df):,} rows in {elapsed:.2f}s ({len(df)/elapsed:,.0f} rows/s)")

    classes = list(clf.classes_)
    df["predicted"] = pred_classes
    for cls in classes:
        idx = classes.index(cls)
        df[f"prob_{cls}"] = proba[:, idx]
    df["confidence"] = proba[np.arange(len(df)), [classes.index(p) for p in pred_classes]]

    # Stage 2: regress only for compatible/conditional
    print("Running Stage 2 inference (regressor for compatible/conditional)...")
    mask = df["predicted"].isin({"compatible", "conditional"})
    df["recommended_max_active_chargers"] = 0
    if mask.any():
        raw = reg.predict(df.loc[mask, ALL_FEATURES])
        df.loc[mask, "recommended_max_active_chargers"] = np.clip(
            raw.round().astype(int), 0,
            df.loc[mask, "num_chargers_installed"].astype(int)
        )
    print(f"  Stage 2 applied to {mask.sum():,} rows")

    return df


def compute_metrics(df: pd.DataFrame) -> dict:
    confusion = {gt: {pred: 0 for pred in CLASS_ORDER} for gt in CLASS_ORDER}
    for gt, pred in zip(df["compatibility_class"], df["predicted"]):
        if gt in confusion and pred in confusion:
            confusion[gt][pred] += 1

    correct = sum(confusion[c][c] for c in CLASS_ORDER)
    total   = len(df)
    accuracy = correct / total

    per_class = {}
    macro_f1_parts = []
    for cls in CLASS_ORDER:
        tp   = confusion[cls][cls]
        fn   = sum(confusion[cls][p] for p in CLASS_ORDER if p != cls)
        fp   = sum(confusion[g][cls] for g in CLASS_ORDER if g != cls)
        supp = tp + fn
        rec  = tp / supp if supp else 0.0
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
        macro_f1_parts.append(f1)
        per_class[cls] = {"tp": tp, "fp": fp, "fn": fn, "support": supp,
                          "recall": rec, "precision": prec, "f1": f1}

    return {
        "accuracy": accuracy,
        "correct": correct,
        "total": total,
        "macro_f1": sum(macro_f1_parts) / len(macro_f1_parts),
        "confusion": confusion,
        "per_class": per_class,
    }


def print_report(metrics: dict) -> None:
    confusion  = metrics["confusion"]
    per_class  = metrics["per_class"]

    print("\n" + "=" * 64)
    print("ACCURACY REPORT")
    print("=" * 64)

    # Confusion matrix
    print(f"\n  Confusion matrix  (rows = ground truth, cols = predicted)")
    col_w = 18
    header = f"  {'':20}" + "".join(f"{c[:col_w]:>{col_w}}" for c in CLASS_ORDER)
    print(header)
    for gt in CLASS_ORDER:
        row = "".join(f"{confusion[gt][pred]:>{col_w}}" for pred in CLASS_ORDER)
        print(f"  {gt:<20}{row}")

    # Per-class metrics
    print(f"\n  {'Class':<20} {'Support':>8} {'Recall':>8} {'Precision':>10} {'F1':>8}")
    print(f"  {'-'*20} {'-'*8} {'-'*8} {'-'*10} {'-'*8}")
    for cls in CLASS_ORDER:
        m = per_class[cls]
        print(f"  {cls:<20} {m['support']:>8,} {m['recall']:>8.1%} "
              f"{m['precision']:>10.1%} {m['f1']:>8.3f}")

    print(f"\n  Overall accuracy : {metrics['correct']:,} / {metrics['total']:,} "
          f"= {metrics['accuracy']:.2%}")
    print(f"  Macro F1         : {metrics['macro_f1']:.4f}")

    # Pass / fail
    passed = metrics["accuracy"] >= 0.90 and metrics["macro_f1"] >= 0.85
    print(f"\n  Thresholds: accuracy >= 90%  macro_f1 >= 0.85")
    print(f"  Result    : {'PASS' if passed else 'FAIL'}")
    print("=" * 64)


def save_csv(df: pd.DataFrame, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    keep = (
        ["transformer_kva", "base_load_kw", "feeder_length_km",
         "cable_type", "r1", "x1", "r0", "x0",
         "phase_balance_class", "num_chargers_installed",
         "num_chargers_active", "charger_power_kw",
         "nominal_load_ratio", "nominal_headroom_kw",
         "compatibility_class", "predicted",
         "confidence", "recommended_max_active_chargers"]
        + [f"prob_{c}" for c in CLASS_ORDER if f"prob_{c}" in df.columns]
    )
    keep = [c for c in keep if c in df.columns]
    df[keep].rename(columns={"compatibility_class": "ground_truth"}).to_csv(
        out_path, index=False
    )
    print(f"\n  Saved {len(df):,} rows to: {out_path.resolve()}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="Output CSV path")
    parser.add_argument("--samples", type=int, default=None,
                        help="Max not_compatible rows to include (default: all)")
    args = parser.parse_args()

    # Load models
    print(f"Loading models from {MODELS_DIR}")
    if not (MODELS_DIR / "compatibility_classifier.joblib").exists():
        print("ERROR: Models not found. Run iep-grid-compatibility/train_classifier.py first.")
        sys.exit(1)
    clf = joblib.load(MODELS_DIR / "compatibility_classifier.joblib")
    reg = joblib.load(MODELS_DIR / "max_chargers_regressor.joblib")
    print("  Models loaded.")

    # Load + optionally sample dataset
    df = load_dataset(DATASET, args.samples)

    # Run inference
    df = run_inference(clf, reg, df)
    df["match"] = df["predicted"] == df["compatibility_class"]

    # Metrics + report
    metrics = compute_metrics(df)
    print_report(metrics)

    # Save
    save_csv(df, Path(args.out))
