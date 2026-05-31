#!/usr/bin/env python3
"""Validate waste/environment knowledge-base shard."""

from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "knowledge_base"
SHARD = KB / "waste_environment"

ID_COLUMNS = {
    "boundary_conditions.csv": "condition_id",
    "complaint_channels.csv": "channel_id",
    "contact_points.csv": "contact_id",
    "not_responsible_for.csv": "boundary_id",
    "required_fields.csv": "requirement_id",
    "research_backlog.csv": "task_id",
    "sla_policy.csv": "sla_id",
    "source_registry.csv": "source_id",
}

PRODUCTION_FACT_FILES = {
    "boundary_conditions.csv",
    "complaint_channels.csv",
    "contact_points.csv",
    "not_responsible_for.csv",
    "required_fields.csv",
    "sla_policy.csv",
}

ALLOWED_CONFIDENCE = {"high", "medium_high", "medium", "low", "not_applicable"}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_source_ids() -> set[str]:
    source_ids: set[str] = set()
    for source_path in KB.glob("**/source_registry.csv"):
        _, rows = read_csv(source_path)
        for row in rows:
            source_id = row.get("source_id", "").strip()
            if source_id:
                source_ids.add(source_id)
    return source_ids


def split_source_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", ";").split(";") if item.strip()]


def main() -> int:
    errors: list[str] = []
    counts: dict[str, int] = {}
    source_ids = load_source_ids()

    if not SHARD.exists():
        errors.append(f"missing folder: {SHARD}")
    else:
        for name, id_col in sorted(ID_COLUMNS.items()):
            path = SHARD / name
            if not path.exists():
                errors.append(f"missing file: {path.relative_to(ROOT)}")
                continue
            fieldnames, rows = read_csv(path)
            counts[name] = len(rows)
            if not fieldnames:
                errors.append(f"{name}: missing header")
                continue
            if id_col not in fieldnames:
                errors.append(f"{name}: missing id column {id_col}")
            values = [row.get(id_col, "").strip() for row in rows]
            blanks = [index for index, value in enumerate(values, start=2) if not value]
            duplicates = sorted(value for value, count in Counter(values).items() if value and count > 1)
            if blanks:
                errors.append(f"{name}: blank {id_col} at lines {blanks[:10]}")
            if duplicates:
                errors.append(f"{name}: duplicate {id_col} values {duplicates[:10]}")
            if name in PRODUCTION_FACT_FILES:
                for required_col in ("source_ids", "confidence"):
                    if required_col not in fieldnames:
                        errors.append(f"{name}: production fact file missing {required_col}")
                if "confidence" in fieldnames:
                    bad_confidence = [
                        (index, row.get("confidence", ""))
                        for index, row in enumerate(rows, start=2)
                        if row.get("confidence", "").strip() not in ALLOWED_CONFIDENCE
                    ]
                    if bad_confidence:
                        errors.append(f"{name}: invalid confidence values {bad_confidence[:10]}")
            for line_no, row in enumerate(rows, start=2):
                if None in row:
                    errors.append(f"{name}:{line_no}: row has extra fields {row[None]}")
                for col, value in row.items():
                    if value is None:
                        errors.append(f"{name}:{line_no}: column {col} has missing value")
                        continue
                    if col == "source_ids":
                        for source_id in split_source_ids(value):
                            if source_id not in source_ids:
                                errors.append(f"{name}:{line_no}: unknown source_id {source_id}")

    print("Waste/environment KB validation:")
    for name, count in sorted(counts.items()):
        print(f"  {name:<28} : {count}")
    print(f"  source ids available          : {len(source_ids)}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OK [waste_environment_kb]: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())