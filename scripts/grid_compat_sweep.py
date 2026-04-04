"""
Grid Compatibility Parameter Sweep
===================================
Calls /predict on iep-grid-compatibility with a wide range of configurations
and saves all results to data/grid_compat_sweep_results.csv.

Usage:
    python tests/grid_compat_sweep.py
    python tests/grid_compat_sweep.py --url http://localhost:8004 --out data/sweep.csv
"""

import argparse
import csv
import itertools
import sys
from datetime import datetime
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Parameter grid
# ---------------------------------------------------------------------------

TRANSFORMER_KVA   = [50, 100, 250, 500]
BASE_LOAD_FRAC    = [0.20, 0.40, 0.60, 0.75, 0.90]   # fraction of kVA
FEEDER_LENGTH_KM  = [0.1, 0.3, 0.5, 1.0, 2.0]
CABLE_TYPES = {
    "A_strong": {"r1": 0.1,  "x1": 0.04, "r0": 0.2,  "x0": 0.08},
    "B_medium": {"r1": 0.2,  "x1": 0.08, "r0": 0.4,  "x0": 0.16},
    "C_weak":   {"r1": 0.35, "x1": 0.12, "r0": 0.7,  "x0": 0.24},
}
PHASE_BALANCE     = ["balanced", "mildly_unbalanced", "heavily_unbalanced"]
NUM_INSTALLED     = [5, 10, 20]
CHARGER_POWER_KW  = [3.7, 7.4, 11.0, 22.0]
# active chargers as fraction of installed
ACTIVE_FRAC       = [0.25, 0.50, 0.75, 1.0]


def build_configs():
    configs = []
    for (kva, base_frac, feeder_km, cable_name, phase, n_installed, charger_kw, act_frac) in itertools.product(
        TRANSFORMER_KVA,
        BASE_LOAD_FRAC,
        FEEDER_LENGTH_KM,
        CABLE_TYPES.keys(),
        PHASE_BALANCE,
        NUM_INSTALLED,
        CHARGER_POWER_KW,
        ACTIVE_FRAC,
    ):
        n_active = max(1, round(n_installed * act_frac))
        base_load_kw = round(kva * base_frac, 1)
        cable = CABLE_TYPES[cable_name]
        configs.append({
            "transformer_kva":        kva,
            "base_load_kw":           base_load_kw,
            "feeder_length_km":       feeder_km,
            "cable_type":             cable_name,
            "r1": cable["r1"], "x1": cable["x1"],
            "r0": cable["r0"], "x0": cable["x0"],
            "phase_balance_class":    phase,
            "num_chargers_installed": n_installed,
            "num_chargers_active":    n_active,
            "charger_power_kw":       charger_kw,
        })
    return configs


# ---------------------------------------------------------------------------
# Run sweep
# ---------------------------------------------------------------------------

def run_sweep(base_url: str, configs: list[dict], out_path: Path) -> None:
    total = len(configs)
    print(f"Running {total:,} configurations against {base_url}/predict")
    print(f"Output → {out_path}\n")

    fieldnames = [
        # inputs
        "transformer_kva", "base_load_kw", "feeder_length_km",
        "cable_type", "r1", "x1", "r0", "x0",
        "phase_balance_class", "num_chargers_installed",
        "num_chargers_active", "charger_power_kw",
        # outputs
        "compatibility_class", "confidence",
        "prob_compatible", "prob_conditional", "prob_not_compatible",
        "recommended_max_active_chargers", "stage2_applied",
        "nominal_load_ratio", "nominal_headroom_kw",
        "transformer_loading_pct",
        # meta
        "status_code", "error",
    ]

    out_path.parent.mkdir(parents=True, exist_ok=True)

    counters = {"compatible": 0, "conditional": 0, "not_compatible": 0, "error": 0}
    start = datetime.now()

    with out_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        with httpx.Client(base_url=base_url, timeout=15.0) as client:
            for i, cfg in enumerate(configs, 1):
                row = dict(cfg)
                try:
                    resp = client.post("/predict", json=cfg)
                    row["status_code"] = resp.status_code
                    row["error"] = ""

                    if resp.status_code == 200:
                        data = resp.json()
                        row["compatibility_class"]            = data.get("compatibility_class", "")
                        row["confidence"]                     = data.get("confidence", "")
                        probs = data.get("class_probabilities", {})
                        row["prob_compatible"]                = probs.get("compatible", "")
                        row["prob_conditional"]               = probs.get("conditional", "")
                        row["prob_not_compatible"]            = probs.get("not_compatible", "")
                        row["recommended_max_active_chargers"]= data.get("recommended_max_active_chargers", "")
                        row["stage2_applied"]                 = data.get("stage2_applied", "")
                        row["nominal_load_ratio"]             = data.get("nominal_load_ratio", "")
                        row["nominal_headroom_kw"]            = data.get("nominal_headroom_kw", "")
                        row["transformer_loading_pct"]        = round(
                            data.get("nominal_load_ratio", 0) * 100, 2
                        )
                        cls = data.get("compatibility_class", "error")
                        counters[cls] = counters.get(cls, 0) + 1
                    else:
                        row["compatibility_class"] = ""
                        row["error"] = f"HTTP {resp.status_code}"
                        counters["error"] += 1

                except Exception as exc:
                    row["status_code"] = -1
                    row["error"] = str(exc)
                    row["compatibility_class"] = ""
                    counters["error"] += 1

                writer.writerow(row)

                # Progress every 500 rows
                if i % 500 == 0 or i == total:
                    elapsed = (datetime.now() - start).total_seconds()
                    rate = i / elapsed if elapsed > 0 else 0
                    eta  = (total - i) / rate if rate > 0 else 0
                    print(
                        f"  {i:>6}/{total}  "
                        f"compatible={counters['compatible']:>5}  "
                        f"conditional={counters['conditional']:>5}  "
                        f"not_compatible={counters['not_compatible']:>5}  "
                        f"errors={counters['error']:>3}  "
                        f"({rate:.0f} req/s, ETA {eta:.0f}s)"
                    )

    elapsed_total = (datetime.now() - start).total_seconds()
    print(f"\nDone in {elapsed_total:.1f}s")
    print(f"Results breakdown:")
    print(f"  compatible     : {counters['compatible']:>6} ({counters['compatible']/total*100:.1f}%)")
    print(f"  conditional    : {counters['conditional']:>6} ({counters['conditional']/total*100:.1f}%)")
    print(f"  not_compatible : {counters['not_compatible']:>6} ({counters['not_compatible']/total*100:.1f}%)")
    print(f"  errors         : {counters['error']:>6}")
    print(f"\nSaved to: {out_path.resolve()}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Grid compat parameter sweep")
    parser.add_argument("--url", default="http://localhost:8004", help="Service base URL")
    parser.add_argument(
        "--out",
        default="data/grid_compat_sweep_results.csv",
        help="Output CSV path",
    )
    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run a smaller subset (first 500 configs) for quick validation",
    )
    args = parser.parse_args()

    configs = build_configs()
    if args.quick:
        configs = configs[:500]
        print("Quick mode: running first 500 configs only")

    # Quick reachability check
    try:
        r = httpx.get(f"{args.url}/health", timeout=5.0)
        if r.status_code != 200:
            print(f"ERROR: Service health check failed ({r.status_code})")
            sys.exit(1)
        health = r.json()
        print(f"Service healthy. Models loaded: {health.get('models_loaded')}\n")
    except Exception as e:
        print(f"ERROR: Cannot reach {args.url} — {e}")
        sys.exit(1)

    run_sweep(args.url, configs, Path(args.out))
