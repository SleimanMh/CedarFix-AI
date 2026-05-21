"""Validate the generated Arabizi surface-form expansion layer."""
from __future__ import annotations

import csv
import sys
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PATH = ROOT / "data" / "knowledge_base" / "arabizi" / "arabizi_surface_forms_v15.csv"

REQUIRED_FIELDS = [
    "surface_id",
    "surface_form",
    "normalized_surface",
    "canonical_form",
    "source_layer",
    "source_id",
    "source_field",
    "sector",
    "issue_type",
    "category",
    "variant_rule",
    "confidence_level",
    "false_friend_risk",
    "risk_level",
    "allowed_uses",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "must_not_auto_promote",
    "source_reference",
    "created_at",
]

FORBIDDEN_ALLOWED_USES = {
    "routing",
    "severity_assignment",
    "sector_classification",
    "issue_type_decision",
    "core_vocab_promotion",
}

REQUIRED_BLOCKED_USES = {
    "routing",
    "severity_assignment",
    "sector_classification",
    "issue_type_decision",
    "core_vocab_promotion",
}

# Sector values that carry routing signal — surface forms must block all of them.
ROUTING_SECTOR_VALUES = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY"}


def split_uses(raw: str) -> set[str]:
    return {part.strip() for part in (raw or "").split("|") if part.strip()}


def validate(path: Path = DEFAULT_PATH) -> tuple[list[str], list[str], int, Counter[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    source_counts: Counter[str] = Counter()

    if not path.exists():
        return [f"missing surface-form file: {path}"], warnings, 0, source_counts

    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        missing = [field for field in REQUIRED_FIELDS if field not in (reader.fieldnames or [])]
        if missing:
            return [f"missing required fields: {missing}"], warnings, 0, source_counts
        rows = list(reader)

    seen_ids: set[str] = set()
    seen_surface_keys: set[tuple[str, str, str, str]] = set()
    for i, row in enumerate(rows, start=2):
        sid = row.get("surface_id", "").strip()
        surface = row.get("surface_form", "").strip()
        normalized = row.get("normalized_surface", "").strip()
        canonical = row.get("canonical_form", "").strip()
        source_layer = row.get("source_layer", "").strip()
        source_id = row.get("source_id", "").strip()
        source_counts[source_layer] += 1

        if not sid:
            errors.append(f"row {i}: blank surface_id")
        elif sid in seen_ids:
            errors.append(f"row {i}: duplicate surface_id={sid}")
        seen_ids.add(sid)

        if not surface:
            errors.append(f"row {i} ({sid}): blank surface_form")
        if not normalized:
            errors.append(f"row {i} ({sid}): blank normalized_surface")
        if surface.lower() != normalized:
            warnings.append(f"row {i} ({sid}): normalized_surface is not lowercase-normalized surface")
        if not canonical:
            errors.append(f"row {i} ({sid}): blank canonical_form")

        key = (normalized, canonical.lower(), source_layer, source_id)
        if key in seen_surface_keys:
            errors.append(f"row {i} ({sid}): duplicate surface/canonical/source key={key}")
        seen_surface_keys.add(key)

        allowed = split_uses(row.get("allowed_uses", ""))
        blocked = split_uses(row.get("blocked_uses", ""))
        forbidden = sorted(allowed & FORBIDDEN_ALLOWED_USES)
        if forbidden:
            errors.append(f"row {i} ({sid}): forbidden allowed_uses={forbidden}")
        missing_blocked = sorted(REQUIRED_BLOCKED_USES - blocked)
        if missing_blocked:
            errors.append(f"row {i} ({sid}): blocked_uses missing {missing_blocked}")

        # Guard: if sector carries a routing-capable value the row MUST have
        # sector_classification in blocked_uses (already covered above) AND
        # must NOT appear in allowed_uses.
        sector_val = row.get("sector", "").strip().upper()
        if sector_val in ROUTING_SECTOR_VALUES and "sector_classification" not in blocked:
            errors.append(
                f"row {i} ({sid}): sector={sector_val} is routing-capable but "
                f"sector_classification is not in blocked_uses"
            )

        if row.get("review_status", "").strip() != "REVIEW_ONLY_GENERATED":
            errors.append(f"row {i} ({sid}): review_status must be REVIEW_ONLY_GENERATED")
        if row.get("reviewer_id", "").strip() != "SYSTEM-V15":
            errors.append(f"row {i} ({sid}): reviewer_id must be SYSTEM-V15")
        if row.get("must_not_auto_promote", "").strip().lower() != "true":
            errors.append(f"row {i} ({sid}): must_not_auto_promote must be true")
        if row.get("false_friend_risk", "").strip().lower() not in {"true", "false"}:
            errors.append(f"row {i} ({sid}): false_friend_risk must be true/false")

    if len(rows) < 3000:
        warnings.append(f"surface-form layer has only {len(rows)} rows; target is >=3000")

    return errors, warnings, len(rows), source_counts


def main() -> None:
    errors, warnings, row_count, source_counts = validate()
    for warning in warnings[:50]:
        print(f"WARNING {warning}")
    if len(warnings) > 50:
        print(f"WARNING ... {len(warnings) - 50} additional warnings omitted")
    if errors:
        for error in errors[:50]:
            print(f"ERROR {error}")
        if len(errors) > 50:
            print(f"ERROR ... {len(errors) - 50} additional errors omitted")
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s), rows={row_count}")
        sys.exit(1)
    print(f"OK: arabizi_surface_forms_v15.csv valid ({row_count} rows, {len(warnings)} warnings)")
    for source, count in source_counts.most_common():
        print(f"  {source}: {count}")


if __name__ == "__main__":
    main()
