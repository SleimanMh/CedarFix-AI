#!/usr/bin/env python3
"""Validate water-establishment knowledge-base shard."""

from __future__ import annotations

import csv
import re
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KB = ROOT / "data" / "knowledge_base"
WATER = KB / "water_establishments"

ID_COLUMNS = {
    "boundary_conditions.csv": "condition_id",
    "branch_service_areas.csv": "area_id",
    "complaint_channels.csv": "channel_id",
    "contact_points.csv": "contact_id",
    "coverage_summary.csv": "coverage_id",
    "irrigation_boundaries.csv": "boundary_id",
    "irl_complaint_patterns.csv": "pattern_id",
    "not_responsible_for.csv": "boundary_id",
    "page_inventory.csv": "inventory_id",
    "required_fields.csv": "requirement_id",
    "research_backlog.csv": "task_id",
    "sla_policy.csv": "sla_id",
    "source_candidate_review.csv": "review_id",
    "source_registry.csv": "source_id",
    "trusted_context.csv": "context_id",
    "water_entity_resolution.csv": "resolution_id",
    "water_service_catalog.csv": "service_id",
}

PRODUCTION_FACT_FILES = {
    "boundary_conditions.csv",
    "branch_service_areas.csv",
    "complaint_channels.csv",
    "contact_points.csv",
    "coverage_summary.csv",
    "irrigation_boundaries.csv",
    "irl_complaint_patterns.csv",
    "not_responsible_for.csv",
    "required_fields.csv",
    "sla_policy.csv",
    "trusted_context.csv",
    "water_entity_resolution.csv",
    "water_service_catalog.csv",
}

STRICT_PROVENANCE_FILES = {
    "water_entity_resolution.csv",
}

ALLOWED_CONFIDENCE = {
    "high",
    "medium_high",
    "medium",
    "low",
    "not_applicable",
}


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def load_source_ids() -> set[str]:
    source_ids: set[str] = set()
    for path in [KB / "source_registry.csv", WATER / "source_registry.csv"]:
        if not path.exists():
            continue
        _, rows = read_csv(path)
        for row in rows:
            source_id = row.get("source_id", "").strip()
            if source_id:
                source_ids.add(source_id)
    return source_ids


def split_source_ids(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", ";").split(";") if item.strip()]


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    source_ids = load_source_ids()
    counts: dict[str, int] = {}

    if not WATER.exists():
        errors.append(f"missing folder: {WATER}")
    else:
        for name, id_col in sorted(ID_COLUMNS.items()):
            path = WATER / name
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
                if "source_ids" in fieldnames:
                    missing_sources = [
                        index for index, row in enumerate(rows, start=2)
                        if not row.get("source_ids", "").strip()
                    ]
                    if missing_sources:
                        errors.append(f"{name}: blank source_ids at lines {missing_sources[:10]}")
                if "confidence" in fieldnames:
                    bad_confidence = [
                        (index, row.get("confidence", ""))
                        for index, row in enumerate(rows, start=2)
                        if row.get("confidence", "").strip() not in ALLOWED_CONFIDENCE
                    ]
                    if bad_confidence:
                        errors.append(f"{name}: invalid confidence values {bad_confidence[:10]}")

            if name in STRICT_PROVENANCE_FILES:
                for required_col in ("retrieved_date", "verification_status"):
                    if required_col not in fieldnames:
                        errors.append(f"{name}: strict provenance file missing {required_col}")
                    else:
                        blanks = [
                            index for index, row in enumerate(rows, start=2)
                            if not row.get(required_col, "").strip()
                        ]
                        if blanks:
                            errors.append(f"{name}: blank {required_col} at lines {blanks[:10]}")

            for line_no, row in enumerate(rows, start=2):
                if None in row:
                    errors.append(f"{name}:{line_no}: row has extra fields {row[None]}")
                for col, value in row.items():
                    if value is None:
                        errors.append(f"{name}:{line_no}: column {col} has missing value")
                        continue
                    if col != "source_ids":
                        continue
                    for source_id in split_source_ids(value):
                        if source_id not in source_ids:
                            errors.append(f"{name}:{line_no}: unknown source_id {source_id}")

    inventory = WATER / "page_inventory.csv"
    if inventory.exists():
        _, rows = read_csv(inventory)
        fetch_errors = [row for row in rows if row.get("notes", "").startswith("fetch_error")]
        if fetch_errors:
            warnings.append(f"page_inventory: {len(fetch_errors)} fetch errors remain for manual review")
        candidate_count = sum(1 for row in rows if row.get("source_status") == "official_candidate")
        warnings.append(f"page_inventory: {candidate_count} official candidate pages are review queue items")

    review_queue = WATER / "source_candidate_review.csv"
    if review_queue.exists():
        _, rows = read_csv(review_queue)
        promote_count = sum(1 for row in rows if row.get("action") == "promote_candidate")
        review_count = sum(1 for row in rows if row.get("action") == "review_later")
        warnings.append(
            f"source_candidate_review: {promote_count} promote candidates and {review_count} later-review rows"
        )

    print("Water-establishments KB validation:")
    for name, count in sorted(counts.items()):
        print(f"  {name:<28} : {count}")
    print(f"  source ids available          : {len(source_ids)}")
    for warning in warnings:
        print(f"WARNING: {warning}")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1

    print("OK [water_establishments_kb]: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
