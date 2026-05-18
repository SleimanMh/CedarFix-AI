#!/usr/bin/env python3
"""Audit Arabizi excellence gates for the next CedarFix phase.

This script is intentionally stricter than the basic validators. Validators
answer "is the data structurally clean?"  This audit answers "are we allowed
to claim best-in-class Arabizi reliability yet?"

Default mode writes an honest readiness artifact and exits 0. Use --strict in
CI/release promotion when all gates are expected to pass.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORTS_PATH = ROOT / "data" / "corpus" / "cedarfix_reports_v1.csv"
PAIRS_PATH = ROOT / "data" / "corpus" / "cedarfix_pairs_v1.csv"
BENCHMARK_PATH = ROOT / "data" / "eval" / "arabizi_benchmark_v0_regression.csv"
STRESS_PATH = ROOT / "data" / "eval" / "arabizi_stress_lab_v1.json"
CERT_PATH = ROOT / "data" / "eval" / "arabizi_reliability_certificate_v1.json"
OUTPUT_PATH = ROOT / "data" / "eval" / "arabizi_excellence_gates_v1.json"

ARABIZI_LANGS = {"arabizi", "mixed"}
NATIVE_REVIEWER_PREFIXES = ("NATIVE-", "LEB-", "DIALECT-")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def batch_of_report(report_id: str) -> str:
    parts = report_id.split("-")
    return parts[1] if len(parts) >= 3 else "UNKNOWN"


def language_pair(a: str, b: str) -> str:
    return "-".join(sorted([a, b]))


def is_native_reviewer(reviewer_id: str) -> bool:
    reviewer_id = reviewer_id.strip().upper()
    return any(reviewer_id.startswith(prefix) for prefix in NATIVE_REVIEWER_PREFIXES)


def pass_gate(actual: float, target: float) -> bool:
    return actual >= target


def audit() -> dict[str, Any]:
    reports = read_csv(REPORTS_PATH)
    pairs = read_csv(PAIRS_PATH)
    reports_by_id = {row["report_id"]: row for row in reports}
    arabizi_reports = [row for row in reports if row["language"] in ARABIZI_LANGS]
    batch_counter = Counter(batch_of_report(row["report_id"]) for row in arabizi_reports)
    native_reviewed = [row for row in arabizi_reports if is_native_reviewer(row.get("reviewer_id", ""))]

    arabizi_pair_rows: list[dict[str, str]] = []
    cross_language_duplicate_count = 0
    hard_negative_count = 0
    unrelated_count = 0
    pair_lang_counter: Counter[str] = Counter()

    for pair in pairs:
        a = reports_by_id[pair["report_id_a"]]
        b = reports_by_id[pair["report_id_b"]]
        if a["language"] not in ARABIZI_LANGS and b["language"] not in ARABIZI_LANGS:
            continue
        arabizi_pair_rows.append(pair)
        pair_lang_counter[language_pair(a["language"], b["language"])] += 1
        if pair["pair_label"] == "DUPLICATE" and a["language"] != b["language"]:
            cross_language_duplicate_count += 1
        if pair["pair_label"] == "HARD_NEGATIVE":
            hard_negative_count += 1
        if pair["pair_label"] == "UNRELATED":
            unrelated_count += 1

    artifact_status = {
        "benchmark_exists": BENCHMARK_PATH.exists(),
        "stress_lab_exists": STRESS_PATH.exists(),
        "live_certificate_exists": CERT_PATH.exists(),
    }

    gates = [
        {
            "gate_id": "ARZ-G01",
            "name": "Batch 002+ Arabizi/mixed scale",
            "target": ">=40 Arabizi/mixed rows total before final Arabizi F1 claims",
            "actual": len(arabizi_reports),
            "pass": pass_gate(len(arabizi_reports), 40),
            "why": "Small-N Batch 001 is regression evidence, not final model evidence.",
        },
        {
            "gate_id": "ARZ-G02",
            "name": "Native Lebanese/dialect review",
            "target": ">=90% of Arabizi/mixed rows reviewed by NATIVE-/LEB-/DIALECT- reviewer",
            "actual": round(len(native_reviewed) / max(1, len(arabizi_reports)), 4),
            "pass": pass_gate(len(native_reviewed) / max(1, len(arabizi_reports)), 0.90),
            "why": "Codex/Claude review is useful, but native dialect review is the strongest defense.",
        },
        {
            "gate_id": "ARZ-G03",
            "name": "Arabizi cross-language duplicate evidence",
            "target": ">=10 duplicate pairs where one side is Arabizi/mixed and languages differ",
            "actual": cross_language_duplicate_count,
            "pass": pass_gate(cross_language_duplicate_count, 10),
            "why": "CedarFix's originality depends on multilingual incident fusion, not standalone text classification.",
        },
        {
            "gate_id": "ARZ-G04",
            "name": "Arabizi hard-negative coverage",
            "target": ">=5 HARD_NEGATIVE pairs involving Arabizi/mixed",
            "actual": hard_negative_count,
            "pass": pass_gate(hard_negative_count, 5),
            "why": "Hard negatives prove the dedup model avoids false merges in realistic same-area cases.",
        },
        {
            "gate_id": "ARZ-G05",
            "name": "Arabizi unrelated-negative coverage",
            "target": ">=5 UNRELATED pairs involving Arabizi/mixed by Batch 002+",
            "actual": unrelated_count,
            "pass": pass_gate(unrelated_count, 5),
            "why": "Cross-cluster unrelated pairs stop semantic similarity from becoming false duplicates.",
        },
        {
            "gate_id": "ARZ-G06",
            "name": "Regression and demo artifacts",
            "target": "benchmark, stress lab, and live certificate artifacts exist",
            "actual": artifact_status,
            "pass": all(artifact_status.values()),
            "why": "The Arabizi claim needs reproducible evidence and a demo artifact, not only source code.",
        },
    ]

    readiness = "READY_FOR_FINAL_ARABIZI_CLAIM" if all(gate["pass"] for gate in gates) else "NOT_READY_FOR_FINAL_ARABIZI_CLAIM"

    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "scope": "Arabizi next-phase excellence gate audit",
            "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
            "strict_mode_note": "Default mode reports honestly and exits 0; --strict exits 1 if any gate fails.",
        },
        "summary": {
            "readiness": readiness,
            "gate_pass_count": sum(1 for gate in gates if gate["pass"]),
            "gate_total": len(gates),
            "arabizi_mixed_report_count": len(arabizi_reports),
            "arabizi_mixed_by_batch": dict(sorted(batch_counter.items())),
            "arabizi_pair_count": len(arabizi_pair_rows),
            "pair_language_breakdown": dict(sorted(pair_lang_counter.items())),
        },
        "gates": gates,
        "next_actions_ranked": [
            "Author Batch 002 with at least 26 additional Arabizi/mixed rows across Tripoli, Sidon, Zahleh, and Bekaa.",
            "Assign a native Lebanese dialect reviewer and update reviewer_id with NATIVE-/LEB-/DIALECT- prefix.",
            "Add at least 10 new Arabizi-involving cross-language duplicate pairs.",
            "Add at least 5 Arabizi-involving HARD_NEGATIVE and 5 UNRELATED pairs.",
            "Run raw vs normalized vs raw+normalized+OOV ablations after Batch 002.",
        ],
    }


def print_report(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("  CedarFix Arabizi Excellence Gate Audit")
    print("=" * 72)
    print(f"Readiness        : {summary['readiness']}")
    print(f"Gates passed     : {summary['gate_pass_count']}/{summary['gate_total']}")
    print(f"Arabizi/mixed N  : {summary['arabizi_mixed_report_count']}")
    print(f"Arabizi pairs    : {summary['arabizi_pair_count']}")
    print("\nGates:")
    for gate in result["gates"]:
        status = "PASS" if gate["pass"] else "BLOCKED"
        print(f"  {status:<7} {gate['gate_id']} {gate['name']} | actual={gate['actual']}")
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit CedarFix Arabizi excellence gates.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write JSON artifact.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any excellence gate is blocked.")
    args = parser.parse_args(argv)

    result = audit()
    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    if args.strict and result["summary"]["readiness"] != "READY_FOR_FINAL_ARABIZI_CLAIM":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
