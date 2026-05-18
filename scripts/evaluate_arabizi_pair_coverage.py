#!/usr/bin/env python3
"""Measure Arabizi-involving duplicate-pair coverage for IEP-2 readiness."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data" / "corpus" / "cedarfix_pairs_v1.csv"
OUTPUT_PATH = ROOT / "data" / "eval" / "arabizi_pair_coverage_v1.json"

ARABIZI_LANGS = {"arabizi", "mixed"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def pair_language(a: str, b: str) -> str:
    return "-".join(sorted([a, b]))


def evaluate() -> dict[str, Any]:
    reports = read_csv(REPORTS_PATH)
    pairs = read_csv(PAIRS_PATH)
    reports_by_id = {row["report_id"]: row for row in reports}

    label_counts: Counter[str] = Counter()
    language_counts: Counter[str] = Counter()
    label_by_language: dict[str, Counter[str]] = defaultdict(Counter)
    sector_counts: Counter[str] = Counter()
    rows: list[dict[str, Any]] = []

    for pair in pairs:
        report_a = reports_by_id[pair["report_id_a"]]
        report_b = reports_by_id[pair["report_id_b"]]
        if report_a["language"] not in ARABIZI_LANGS and report_b["language"] not in ARABIZI_LANGS:
            continue

        language_pair = pair_language(report_a["language"], report_b["language"])
        label = pair["pair_label"]
        label_counts[label] += 1
        language_counts[language_pair] += 1
        label_by_language[language_pair][label] += 1
        sector_counts[report_a["sector"]] += 1
        if report_b["sector"] != report_a["sector"]:
            sector_counts[report_b["sector"]] += 1

        rows.append(
            {
                "pair_id": pair["pair_id"],
                "pair_label": label,
                "language_pair": language_pair,
                "report_id_a": report_a["report_id"],
                "report_id_b": report_b["report_id"],
                "sector_a": report_a["sector"],
                "sector_b": report_b["sector"],
                "issue_type_a": report_a["issue_type"],
                "issue_type_b": report_b["issue_type"],
                "duplicate_role_a": report_a["duplicate_role"],
                "duplicate_role_b": report_b["duplicate_role"],
                "rationale": pair["rationale"],
            }
        )

    total = max(1, len(rows))
    negative_count = label_counts["HARD_NEGATIVE"] + label_counts["UNRELATED"]
    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "scope": "Arabizi-involving pair-label coverage for IEP-2 readiness",
            "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
        },
        "summary": {
            "arabizi_pair_count": len(rows),
            "duplicate_count": label_counts["DUPLICATE"],
            "related_count": label_counts["RELATED"],
            "hard_negative_count": label_counts["HARD_NEGATIVE"],
            "unrelated_count": label_counts["UNRELATED"],
            "negative_ratio": round(negative_count / total, 4),
            "cross_language_duplicate_count": sum(
                1
                for row in rows
                if row["pair_label"] == "DUPLICATE" and row["language_pair"] not in {"arabizi-arabizi", "mixed-mixed"}
            ),
        },
        "label_breakdown": dict(sorted(label_counts.items())),
        "language_pair_breakdown": dict(sorted(language_counts.items())),
        "label_by_language_pair": {
            language: dict(sorted(counts.items()))
            for language, counts in sorted(label_by_language.items())
        },
        "sector_breakdown": dict(sorted(sector_counts.items())),
        "pair_details": rows,
    }


def print_report(result: dict[str, Any]) -> None:
    s = result["summary"]
    print("\n" + "=" * 72)
    print("  CedarFix Arabizi Pair Coverage")
    print("=" * 72)
    print(f"Arabizi-involving pairs : {s['arabizi_pair_count']}")
    print(f"Duplicates              : {s['duplicate_count']}")
    print(f"Related                 : {s['related_count']}")
    print(f"Hard negatives          : {s['hard_negative_count']}")
    print(f"Unrelated               : {s['unrelated_count']}")
    print(f"Negative ratio          : {s['negative_ratio']:.1%}")
    print(f"Cross-language dupes    : {s['cross_language_duplicate_count']}")
    print("\nLanguage pairs:")
    for language_pair, count in result["language_pair_breakdown"].items():
        print(f"  {language_pair:<16} {count}")
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Arabizi pair coverage for IEP-2 readiness.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write JSON artifact.")
    args = parser.parse_args(argv)

    result = evaluate()
    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
