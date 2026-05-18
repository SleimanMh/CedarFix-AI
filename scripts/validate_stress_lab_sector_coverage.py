#!/usr/bin/env python3
"""Validate that the Arabizi Stress Lab covers every sector that has meaningful
vocabulary coverage (>= MIN_VOCAB_TOKENS tokens in the vocabulary index).

Pass criteria
-------------
Every canonical sector with >= MIN_VOCAB_TOKENS vocabulary tokens must have at
least one stress scenario in the latest stress lab JSON artifact.

Default mode writes a JSON artifact and exits 0 regardless of result.
Use --strict for CI/release gating (exits 1 on any coverage gap).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
STRESS_LAB_PATH = ROOT / "data" / "eval" / "arabizi_stress_lab_v1.json"
OUTPUT_PATH = ROOT / "data" / "eval" / "stress_lab_sector_coverage_v1.json"

MIN_VOCAB_TOKENS = 10  # sectors below this threshold are excluded from the gate


def load_vocab_sector_counts(vocab_path: Path) -> dict[str, int]:
    """Return {sector: keyword_count} from the vocabulary index.

    The vocabulary JSON has the structure:
    {"sectors": {"ROADS": {"issue_type_keywords": {"pothole": [...], ...}, ...}, ...}}
    """
    data = json.loads(vocab_path.read_text(encoding="utf-8"))
    sectors: dict[str, Any] = data.get("sectors", {})
    counts: dict[str, int] = {}
    for sector, body in sectors.items():
        kw_map: dict[str, list[str]] = body.get("issue_type_keywords", {})
        counts[sector.upper()] = sum(len(kws) for kws in kw_map.values())
    return counts


def load_exercised_sectors(stress_lab_path: Path) -> set[str]:
    """Return the set of expected_sector values covered in the stress lab."""
    data = json.loads(stress_lab_path.read_text(encoding="utf-8"))
    # Prefer pre-computed sector_coverage if available (v1.1+)
    if "sector_coverage" in data:
        return set(data["sector_coverage"].get("exercised_sectors", []))
    # Fallback: derive from scenario_summary keys via variants
    exercised: set[str] = set()
    for row in data.get("variants", []):
        sector = row.get("predicted_sector") or row.get("expected_sector", "")
        if sector and sector != "OTHER":
            exercised.add(sector)
    return exercised


def run_coverage_check(
    vocab_path: Path = VOCAB_PATH,
    stress_lab_path: Path = STRESS_LAB_PATH,
) -> dict[str, Any]:
    """Run the coverage check and return a result dict."""
    # ── 1. Vocabulary sector counts ──────────────────────────────────────────
    vocab_counts = load_vocab_sector_counts(vocab_path)
    required_sectors = sorted(
        sector for sector, count in vocab_counts.items()
        if count >= MIN_VOCAB_TOKENS
    )

    # ── 2. Stress lab exercised sectors ──────────────────────────────────────
    exercised_sectors = load_exercised_sectors(stress_lab_path)

    # ── 3. Gap analysis ──────────────────────────────────────────────────────
    missing_sectors = sorted(set(required_sectors) - exercised_sectors)
    coverage_rate = (
        round(len(exercised_sectors & set(required_sectors)) / len(required_sectors), 4)
        if required_sectors else 1.0
    )

    passed = len(missing_sectors) == 0

    return {
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "vocab_path": str(vocab_path.relative_to(ROOT)),
        "stress_lab_path": str(stress_lab_path.relative_to(ROOT)),
        "min_vocab_tokens_threshold": MIN_VOCAB_TOKENS,
        "vocab_sector_counts": vocab_counts,
        "required_sectors": required_sectors,
        "exercised_sectors": sorted(exercised_sectors),
        "missing_sectors": missing_sectors,
        "coverage_rate": coverage_rate,
        "passed": passed,
        "verdict": "PASS" if passed else "FAIL",
        "message": (
            "All sectors with sufficient vocabulary are covered by at least one stress scenario."
            if passed
            else f"Coverage gap: {len(missing_sectors)} sector(s) not exercised — {missing_sectors}"
        ),
    }


def print_report(result: dict[str, Any]) -> None:
    print("\n" + "=" * 72)
    print("  CedarFix Stress Lab Sector Coverage Validator")
    print("=" * 72)
    print(f"Vocab sectors (>={MIN_VOCAB_TOKENS} tokens) : {len(result['required_sectors'])}")
    print(f"Sectors exercised                  : {len(result['exercised_sectors'])}")
    print(f"Coverage rate                      : {result['coverage_rate']:.0%}")
    print(f"Verdict                            : {result['verdict']}")
    print()
    for sector in result["required_sectors"]:
        token_count = result["vocab_sector_counts"].get(sector, 0)
        status = "COVERED" if sector in result["exercised_sectors"] else "MISSING"
        print(f"  {sector:<18}  tokens={token_count:<4}  {status}")
    if result["missing_sectors"]:
        print(f"\nGap: sectors not yet covered: {result['missing_sectors']}")
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true",
                        help="Exit 1 if any required sector is not covered.")
    parser.add_argument("--no-save", action="store_true",
                        help="Do not write JSON artifact.")
    parser.add_argument("--json", action="store_true",
                        help="Print machine-readable JSON to stdout.")
    args = parser.parse_args(argv)

    result = run_coverage_check()

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)

    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if args.strict and not result["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
