"""
Grid Compatibility Credibility Validator
=========================================
Three independent validation tiers:

  Tier 1 — Physics sanity checks
    Extreme configs where engineering physics guarantees the answer.
    Any model disagreement is a red flag.

  Tier 2 — Monotonicity checks
    Increasing load must monotonically worsen compatibility class.
    Increasing transformer size must monotonically improve it.

  Tier 3 — Hold-out comparison against OpenDSS dataset
    Runs the live API on a random sample from the original simulation
    dataset and compares predictions to OpenDSS ground-truth labels.

Usage:
    python tests/validate_grid_compat.py
    python tests/validate_grid_compat.py --url http://localhost:8004
    python tests/validate_grid_compat.py --tier 1      # only physics checks
    python tests/validate_grid_compat.py --no-holdout  # skip dataset load
"""

import argparse
import json
import random
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import httpx

BASE_URL   = "http://localhost:8004"
DATASET    = Path("data/raw/simulation_dataset_final.csv")
HOLDOUT_N  = 200   # rows to sample from the dataset for Tier 3

# Compatibility class ordering (worse = higher index)
CLASS_ORDER = {"compatible": 0, "conditional": 1, "not_compatible": 2}

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"

results = []

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def predict(client: httpx.Client, cfg: dict, retries: int = 3) -> dict | None:
    for attempt in range(retries):
        try:
            r = client.post("/predict", json=cfg, timeout=30.0)
            if r.status_code == 200:
                return r.json()
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(0.5 * (attempt + 1))  # 0.5s, 1.0s back-off
            else:
                print(f"    Request failed after {retries} attempts: {e}")
    return None


def base_cfg(**overrides) -> dict:
    """Return a sensible default config with selective overrides."""
    cfg = {
        "transformer_kva": 250,
        "base_load_kw": 50.0,
        "feeder_length_km": 0.3,
        "cable_type": "B_medium",
        "r1": 0.2, "x1": 0.08, "r0": 0.4, "x0": 0.16,
        "phase_balance_class": "balanced",
        "num_chargers_installed": 20,
        "num_chargers_active": 5,
        "charger_power_kw": 7.4,
    }
    cfg.update(overrides)
    return cfg


def check(name: str, passed: bool, detail: str = "") -> None:
    status = PASS if passed else FAIL
    results.append({"tier": results[-1]["tier"] if results else "?",
                    "name": name, "status": status, "detail": detail})
    icon = "OK" if passed else "!!"
    print(f"  [{icon}] {name}")
    if detail:
        print(f"       {detail}")


# ---------------------------------------------------------------------------
# Tier 1 — Physics sanity checks
# ---------------------------------------------------------------------------

def tier1_physics(client: httpx.Client) -> None:
    print("\n=== Tier 1: Physics Sanity Checks ===")
    tier = "T1-Physics"

    # --- T1-1: Severely overloaded transformer must be not_compatible
    cfg = base_cfg(
        transformer_kva=50,
        base_load_kw=45.0,       # 90% base load alone
        num_chargers_active=10,
        charger_power_kw=22.0,   # total EV demand = 220 kW on a 50 kVA transformer
        cable_type="C_weak",
        phase_balance_class="heavily_unbalanced",
    )
    r = predict(client, cfg)
    if r:
        actual = r["compatibility_class"]
        passed = actual == "not_compatible"
        results.append({"tier": tier})
        check(
            "Severely overloaded (load_ratio>>1) → not_compatible",
            passed,
            f"nominal_load_ratio={r['nominal_load_ratio']:.2f}, "
            f"got '{actual}', expected 'not_compatible'",
        )
    else:
        results.append({"tier": tier})
        check("Severely overloaded → not_compatible", False, "No response")

    # --- T1-2: Lightly loaded large transformer must NOT be not_compatible
    cfg = base_cfg(
        transformer_kva=1000,
        base_load_kw=20.0,
        num_chargers_active=2,
        charger_power_kw=3.7,
        cable_type="A_strong",
        phase_balance_class="balanced",
    )
    r = predict(client, cfg)
    if r:
        actual = r["compatibility_class"]
        passed = actual in ("compatible", "conditional")
        results.append({"tier": tier})
        check(
            "Light load on large transformer → compatible/conditional",
            passed,
            f"nominal_load_ratio={r['nominal_load_ratio']:.3f}, got '{actual}'",
        )
    else:
        results.append({"tier": tier})
        check("Light load on large transformer", False, "No response")

    # --- T1-3: nominal_load_ratio math must be correct
    kva, base, n, p = 500, 100.0, 10, 7.4
    cfg = base_cfg(transformer_kva=kva, base_load_kw=base,
                   num_chargers_active=n, charger_power_kw=p)
    r = predict(client, cfg)
    if r:
        expected = (base + n * p) / kva
        actual_ratio = r["nominal_load_ratio"]
        passed = abs(actual_ratio - expected) < 0.001
        results.append({"tier": tier})
        check(
            "nominal_load_ratio math: (base + n*p) / kVA",
            passed,
            f"expected={expected:.4f}, got={actual_ratio:.4f}",
        )
    else:
        results.append({"tier": tier})
        check("nominal_load_ratio math", False, "No response")

    # --- T1-4: recommended_max_active_chargers never exceeds installed
    cfg = base_cfg(num_chargers_installed=8, num_chargers_active=8)
    r = predict(client, cfg)
    if r:
        rec = r["recommended_max_active_chargers"]
        passed = rec <= 8
        results.append({"tier": tier})
        check(
            "Recommended chargers never exceeds installed (8)",
            passed,
            f"recommended={rec}, installed=8",
        )
    else:
        results.append({"tier": tier})
        check("Recommended chargers <= installed", False, "No response")

    # --- T1-5: confidence is a valid probability
    cfg = base_cfg()
    r = predict(client, cfg)
    if r:
        conf = r["confidence"]
        probs = r["class_probabilities"]
        prob_sum = sum(probs.values())
        passed = 0.0 <= conf <= 1.0 and abs(prob_sum - 1.0) < 0.01
        results.append({"tier": tier})
        check(
            "Confidence in [0,1] and probabilities sum to 1.0",
            passed,
            f"confidence={conf:.4f}, prob_sum={prob_sum:.4f}",
        )
    else:
        results.append({"tier": tier})
        check("Confidence and probability validity", False, "No response")

    # --- T1-6: headroom = kVA - base - n*p (nominal)
    kva, base, n, p = 200, 60.0, 5, 7.4
    cfg = base_cfg(transformer_kva=kva, base_load_kw=base,
                   num_chargers_active=n, charger_power_kw=p)
    r = predict(client, cfg)
    if r:
        expected_headroom = kva - base - n * p
        actual_headroom = r["nominal_headroom_kw"]
        passed = abs(actual_headroom - expected_headroom) < 0.5
        results.append({"tier": tier})
        check(
            "nominal_headroom_kw = kVA - base_load - n*charger_power",
            passed,
            f"expected={expected_headroom:.1f}, got={actual_headroom:.1f}",
        )
    else:
        results.append({"tier": tier})
        check("nominal_headroom_kw math", False, "No response")


# ---------------------------------------------------------------------------
# Tier 2 — Monotonicity checks
# ---------------------------------------------------------------------------

def tier2_monotonicity(client: httpx.Client) -> None:
    print("\n=== Tier 2: Monotonicity Checks ===")
    tier = "T2-Monotonicity"

    # --- T2-1: Increasing active chargers should worsen or hold class
    print("  Active chargers 1 → 20 (fixed 100kVA, 40kW base, 7.4kW charger):")
    charger_counts = [1, 3, 5, 8, 12, 16, 20]
    classes = []
    for n in charger_counts:
        cfg = base_cfg(transformer_kva=100, base_load_kw=40.0,
                       num_chargers_active=n, charger_power_kw=7.4,
                       num_chargers_installed=20)
        r = predict(client, cfg)
        if r:
            cls = r["compatibility_class"]
            ratio = r["nominal_load_ratio"]
            classes.append(CLASS_ORDER[cls])
            print(f"    n={n:2d} → {cls:<16} (load_ratio={ratio:.2f})")
        else:
            classes.append(-1)
            print(f"    n={n:2d} → ERROR")

    valid = all(c >= 0 for c in classes)
    monotone = all(classes[i] <= classes[i+1] for i in range(len(classes)-1))
    results.append({"tier": tier})
    check(
        "Class degrades (or holds) as active chargers increase",
        valid and monotone,
        "non-monotone sequence detected" if not monotone else "strictly non-improving",
    )

    # --- T2-2: Increasing transformer kVA should improve or hold class
    print("  Transformer kVA 50 → 1000 (fixed 40kW base, 10 chargers @ 7.4kW):")
    kva_values = [50, 100, 200, 400, 750, 1000]
    classes = []
    for kva in kva_values:
        cfg = base_cfg(transformer_kva=kva, base_load_kw=40.0,
                       num_chargers_active=10, charger_power_kw=7.4)
        r = predict(client, cfg)
        if r:
            cls = r["compatibility_class"]
            ratio = r["nominal_load_ratio"]
            classes.append(CLASS_ORDER[cls])
            print(f"    kVA={kva:4d} → {cls:<16} (load_ratio={ratio:.2f})")
        else:
            classes.append(999)
            print(f"    kVA={kva:4d} → ERROR")

    valid = all(c < 999 for c in classes)
    monotone = all(classes[i] >= classes[i+1] for i in range(len(classes)-1))
    results.append({"tier": tier})
    check(
        "Class improves (or holds) as transformer kVA increases",
        valid and monotone,
        "non-monotone sequence detected" if not monotone else "strictly non-worsening",
    )

    # --- T2-3: Stronger cable should never worsen compatibility vs weaker cable
    print("  Cable type A_strong vs C_weak (same everything else):")
    cable_map = {
        "A_strong": {"r1": 0.1,  "x1": 0.04, "r0": 0.2,  "x0": 0.08},
        "B_medium": {"r1": 0.2,  "x1": 0.08, "r0": 0.4,  "x0": 0.16},
        "C_weak":   {"r1": 0.35, "x1": 0.12, "r0": 0.7,  "x0": 0.24},
    }
    cable_classes = {}
    for cable_name, cable_params in cable_map.items():
        cfg = base_cfg(feeder_length_km=1.0, num_chargers_active=10,
                       cable_type=cable_name, **cable_params)
        r = predict(client, cfg)
        if r:
            cls = r["compatibility_class"]
            cable_classes[cable_name] = CLASS_ORDER[cls]
            print(f"    {cable_name:<10} → {cls}")
        else:
            cable_classes[cable_name] = -1
            print(f"    {cable_name:<10} → ERROR")

    valid = all(v >= 0 for v in cable_classes.values())
    # A_strong should be <= B_medium <= C_weak in class order
    ordered = (cable_classes.get("A_strong", 0) <=
               cable_classes.get("B_medium", 0) <=
               cable_classes.get("C_weak", 999))
    results.append({"tier": tier})
    check(
        "Stronger cable never worsens compatibility vs weaker cable",
        valid and ordered,
        f"A={cable_classes.get('A_strong')}, B={cable_classes.get('B_medium')}, "
        f"C={cable_classes.get('C_weak')} (0=compatible,1=conditional,2=not_compatible)",
    )


# ---------------------------------------------------------------------------
# Tier 3 — Hold-out comparison against OpenDSS dataset
# ---------------------------------------------------------------------------

def tier3_holdout(client: httpx.Client, n_samples: int, save_path: str | None = None) -> None:
    print(f"\n=== Tier 3: Hold-out Comparison vs OpenDSS Ground Truth (n={n_samples}) ===")
    tier = "T3-Holdout"

    if not DATASET.exists():
        print(f"  Dataset not found at {DATASET} — skipping Tier 3")
        results.append({"tier": tier})
        check("Dataset available", False, f"File not found: {DATASET}")
        return

    import csv as _csv

    # Load dataset
    try:
        with DATASET.open(encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))
    except Exception as e:
        print(f"  Failed to load dataset: {e}")
        results.append({"tier": tier})
        check("Dataset loadable", False, str(e))
        return

    required_in = ["transformer_kva", "base_load_kw", "feeder_length_km",
                   "cable_type", "r1", "x1", "r0", "x0",
                   "phase_balance_class", "num_chargers_installed",
                   "num_chargers_active", "charger_power_kw"]

    # Stratified sampling: keep ALL minority class rows, sample from majority
    by_class = {c: [] for c in CLASS_ORDER}
    for row in rows:
        cls = row.get("compatibility_class", "")
        if cls in CLASS_ORDER and all(k in row for k in required_in):
            by_class[cls].append(row)

    print(f"  Dataset: {len(rows):,} rows")
    for cls, cls_rows in by_class.items():
        print(f"    {cls:<16}: {len(cls_rows):,}")

    # Cap not_compatible to n_samples to keep runtime reasonable
    # Keep all compatible + conditional (minority classes — most important to test)
    not_compat_sample = random.sample(
        by_class["not_compatible"],
        min(n_samples, len(by_class["not_compatible"]))
    )
    sample = by_class["compatible"] + by_class["conditional"] + not_compat_sample
    random.shuffle(sample)
    total_planned = len(sample)
    print(f"\n  Stratified sample: {total_planned:,} rows "
          f"(all compatible={len(by_class['compatible'])}, "
          f"all conditional={len(by_class['conditional'])}, "
          f"not_compatible={len(not_compat_sample)})")

    # Run predictions concurrently
    classes = list(CLASS_ORDER.keys())
    confusion = {gt: {pred: 0 for pred in classes} for gt in classes}
    csv_rows = []
    correct = 0
    evaluated = 0
    start_time = datetime.now()

    def _call(row):
        try:
            cfg = {k: (float(row[k]) if k not in ("cable_type", "phase_balance_class") else row[k])
                   for k in required_in}
            cfg["num_chargers_installed"] = int(float(cfg["num_chargers_installed"]))
            cfg["num_chargers_active"]    = int(float(cfg["num_chargers_active"]))
        except Exception:
            return None
        ground_truth = row["compatibility_class"]
        resp = predict(client, cfg)
        if not resp:
            return None
        return cfg, ground_truth, resp

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(_call, row): row for row in sample}
        done = 0
        for future in as_completed(futures):
            done += 1
            result = future.result()
            if result is None:
                continue
            cfg, ground_truth, resp = result

            predicted        = resp["compatibility_class"]
            confidence       = resp.get("confidence", "")
            load_ratio       = resp.get("nominal_load_ratio", "")
            headroom         = resp.get("nominal_headroom_kw", "")
            match            = predicted == ground_truth

            confusion[ground_truth][predicted] += 1
            if match:
                correct += 1
            evaluated += 1

            csv_rows.append({
                **cfg,
                "ground_truth":        ground_truth,
                "predicted":           predicted,
                "match":               match,
                "confidence":          confidence,
                "nominal_load_ratio":  load_ratio,
                "nominal_headroom_kw": headroom,
            })

            if done % 500 == 0 or done == total_planned:
                elapsed = (datetime.now() - start_time).total_seconds()
                rate = done / elapsed if elapsed > 0 else 1
                acc_str = f"{correct/evaluated:.1%}" if evaluated else "n/a"
                print(f"  {done:>5}/{total_planned}  acc={acc_str}  ({rate:.0f} req/s)")

    if evaluated == 0:
        results.append({"tier": tier})
        check("Hold-out accuracy", False, "No rows evaluated")
        return

    accuracy = correct / evaluated

    # Confusion matrix
    print(f"\n  Confusion matrix (rows=ground truth, cols=predicted):")
    header = f"  {'':18}" + "".join(f"{c[:12]:>14}" for c in classes)
    print(header)
    for gt in classes:
        row_vals = "".join(f"{confusion[gt][pred]:>14}" for pred in classes)
        print(f"  {gt:<18}{row_vals}")

    # Per-class precision / recall
    print(f"\n  Per-class metrics:")
    print(f"  {'Class':<18} {'Recall':>8} {'Precision':>10} {'F1':>8} {'Support':>8}")
    macro_f1_parts = []
    for cls in classes:
        tp   = confusion[cls][cls]
        fn   = sum(confusion[cls][p] for p in classes if p != cls)
        fp   = sum(confusion[g][cls] for g in classes if g != cls)
        supp = tp + fn
        rec  = tp / supp if supp else 0
        prec = tp / (tp + fp) if (tp + fp) else 0
        f1   = 2 * prec * rec / (prec + rec) if (prec + rec) else 0
        macro_f1_parts.append(f1)
        print(f"  {cls:<18} {rec:>8.1%} {prec:>10.1%} {f1:>8.3f} {supp:>8}")

    macro_f1 = sum(macro_f1_parts) / len(macro_f1_parts)
    print(f"\n  Overall accuracy : {correct}/{evaluated} = {accuracy:.1%}")
    print(f"  Macro F1         : {macro_f1:.3f}")

    # Save CSV
    if save_path:
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = list(csv_rows[0].keys()) if csv_rows else []
        with save_path.open("w", newline="", encoding="utf-8") as f:
            writer = _csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(csv_rows)
        print(f"\n  Saved {len(csv_rows):,} rows to: {save_path.resolve()}")

    results.append({"tier": tier})
    check(
        "Hold-out accuracy >= 90%",
        accuracy >= 0.90,
        f"accuracy={accuracy:.1%}, macro_f1={macro_f1:.3f} on {evaluated} rows",
    )
    results.append({"tier": tier})
    check(
        "All classes represented in sample",
        all(sum(confusion[c].values()) > 0 for c in classes),
        "class counts: " + ", ".join(
            f"{c}={sum(confusion[c].values())}" for c in classes
        ),
    )


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

def print_summary() -> bool:
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    passed = [r for r in results if r.get("status") == PASS]
    failed = [r for r in results if r.get("status") == FAIL]
    skipped = [r for r in results if r.get("status") == SKIP]

    for r in results:
        if "status" not in r:
            continue
        icon = "OK" if r["status"] == PASS else ("--" if r["status"] == SKIP else "!!")
        print(f"  [{icon}] [{r['tier']}] {r['name']}")

    print(f"\n  Passed : {len(passed)}")
    print(f"  Failed : {len(failed)}")
    print(f"  Skipped: {len(skipped)}")

    if failed:
        print("\nFAILED CHECKS:")
        for r in failed:
            print(f"  - [{r['tier']}] {r['name']}: {r.get('detail', '')}")

    all_passed = len(failed) == 0
    print(f"\nOverall: {'ALL CHECKS PASSED' if all_passed else 'SOME CHECKS FAILED'}")
    return all_passed


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=BASE_URL)
    parser.add_argument("--tier", type=int, choices=[1, 2, 3],
                        help="Run only a specific tier")
    parser.add_argument("--no-holdout", action="store_true",
                        help="Skip Tier 3 hold-out comparison")
    parser.add_argument("--samples", type=int, default=2000,
                        help="not_compatible rows to sample for Tier 3 (default 2000; minority classes always fully included)")
    parser.add_argument("--save-csv", default="data/grid_compat_sweep_results.csv",
                        help="Save Tier 3 per-row results to this CSV")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)

    # Reachability check
    try:
        r = httpx.get(f"{args.url}/health", timeout=5.0)
        if r.status_code != 200:
            print(f"ERROR: Health check failed ({r.status_code})")
            sys.exit(1)
        h = r.json()
        print(f"Service: {args.url}")
        print(f"Models loaded: {h.get('models_loaded')}")
    except Exception as e:
        print(f"ERROR: Cannot reach {args.url} — {e}")
        sys.exit(1)

    with httpx.Client(base_url=args.url) as client:
        if args.tier in (None, 1):
            tier1_physics(client)
        if args.tier in (None, 2):
            tier2_monotonicity(client)
        if args.tier in (None, 3) and not args.no_holdout:
            tier3_holdout(client, args.samples, save_path=args.save_csv)

    ok = print_summary()
    sys.exit(0 if ok else 1)
