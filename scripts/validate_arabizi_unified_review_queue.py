#!/usr/bin/env python
"""Validate the unified Arabizi review queue projection."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
QUEUE = ROOT / "data" / "knowledge_base" / "arabizi" / "arabizi_unified_review_queue.csv"
SUMMARY = ROOT / "data" / "knowledge_base" / "arabizi" / "arabizi_unified_review_queue_summary.json"

REQUIRED_COLUMNS = {
    "review_queue_id",
    "review_key",
    "review_family",
    "review_priority",
    "source_file",
    "source_row_id",
    "source_layer",
    "surface_form",
    "normalized_form",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "decision",
    "must_not_auto_promote",
    "original_payload_json",
}

MUST_BLOCK_FOR_REVIEW_ONLY = {
    "EXTERNAL_OOV_CANDIDATE",
    "GENERATED_SURFACE_FORM",
    "BFL_QUARANTINE",
}


def read_rows() -> tuple[list[str], list[dict[str, str]]]:
    if not QUEUE.exists():
        raise FileNotFoundError(f"Missing {QUEUE}")
    with QUEUE.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), [
            {k: (v or "").strip() for k, v in row.items()}
            for row in reader
            if any((v or "").strip() for v in row.values())
        ]


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    header, rows = read_rows()
    missing = REQUIRED_COLUMNS - set(header)
    if missing:
        errors.append(f"Missing required columns: {', '.join(sorted(missing))}")

    seen_ids: set[str] = set()
    families: Counter[str] = Counter()
    sources: Counter[str] = Counter()

    for idx, row in enumerate(rows, start=2):
        row_id = row.get("review_queue_id", "")
        if not row_id:
            errors.append(f"line {idx}: missing review_queue_id")
        elif row_id in seen_ids:
            errors.append(f"line {idx}: duplicate review_queue_id {row_id}")
        seen_ids.add(row_id)

        for col in ("review_family", "source_file", "source_row_id", "source_layer", "surface_form", "normalized_form"):
            if not row.get(col):
                errors.append(f"line {idx} ({row_id}): missing {col}")

        family = row.get("review_family", "")
        families[family] += 1
        sources[row.get("source_file", "")] += 1

        blocked = row.get("blocked_uses", "").lower()
        if family in MUST_BLOCK_FOR_REVIEW_ONLY and "auto" not in blocked:
            errors.append(f"line {idx} ({row_id}): {family} must block automatic use")

        if family in {"GENERAL_SUPPORT_WORD", "GENERATED_SURFACE_FORM"}:
            for forbidden in ("routing", "severity", "sector", "issue"):
                if forbidden not in blocked:
                    errors.append(f"line {idx} ({row_id}): {family} must block {forbidden}")

        if family in MUST_BLOCK_FOR_REVIEW_ONLY and row.get("must_not_auto_promote", "").lower() != "true":
            errors.append(f"line {idx} ({row_id}): {family} must set must_not_auto_promote=true")

        payload = row.get("original_payload_json", "")
        try:
            json.loads(payload)
        except json.JSONDecodeError as exc:
            errors.append(f"line {idx} ({row_id}): original_payload_json is invalid JSON: {exc}")

    if SUMMARY.exists():
        with SUMMARY.open("r", encoding="utf-8") as handle:
            summary = json.load(handle)
        if summary.get("row_count") != len(rows):
            errors.append(f"summary row_count={summary.get('row_count')} but CSV has {len(rows)} rows")
    else:
        warnings.append(f"Missing optional summary file: {SUMMARY}")

    print(f"Unified Arabizi review queue: {len(rows)} rows")
    for family, count in sorted(families.items()):
        print(f"  {family}: {count}")
    print(f"Sources: {len(sources)}")

    if warnings:
        print("\nWarnings:")
        for warning in warnings:
            print(f"  - {warning}")

    if errors:
        print("\nErrors:")
        for error in errors:
            print(f"  - {error}")
        return 1

    print("\nOK: unified review queue passed validation")
    return 0


if __name__ == "__main__":
    sys.exit(main())
