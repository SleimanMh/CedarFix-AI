"""
Clean CedarFix's Arabizi candidate bank into a domain-only promotion queue.

The candidate bank should contain terms that might eventually become production
issue vocabulary. Generic Lebanese Arabizi support words, protected phrase
locks, place names, and discourse terms belong in support layers or quarantine,
not in the promotion queue.
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARABIZI_DIR = ROOT / "data" / "knowledge_base" / "arabizi"
BANK_PATH = ARABIZI_DIR / "arabizi_candidate_bank.csv"
QUARANTINE_PATH = ARABIZI_DIR / "arabizi_candidate_bank_quarantine.csv"
RELIABILITY_LAYER_PATH = ARABIZI_DIR / "arabizi_reliability_layer.json"

CLEANUP_VERSION = "v13.1-candidate-bank-domain-cleanup"

DOMAIN_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY"}

SUPPORT_ONLY_CATEGORIES = {
    "adverb",
    "cause_effect_word",
    "civic_admin",
    "code_switch",
    "complaint_discourse",
    "complaint_phrase",
    "complaint_starter",
    "connector",
    "connector_time",
    "demonstrative",
    "descriptor",
    "discourse_general",
    "evidence_metadata",
    "evidence_word",
    "filler",
    "frequency",
    "impact_context",
    "institution",
    "internet_notation",
    "location_word",
    "modal",
    "negation",
    "noun_civic",
    "noun_entity",
    "noun_general",
    "noun_location",
    "noun_person",
    "noun_quality",
    "number_quantity",
    "particle",
    "people_word",
    "place_name_support",
    "possessive",
    "pronoun",
    "protected_combo",
    "quantifier",
    "question_word",
    "status_word",
    "time_expr",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_bool(value: str) -> str:
    normalized = (value or "").strip().lower()
    aliases = {"yes": "true", "no": "false", "y": "true", "n": "false"}
    normalized = aliases.get(normalized, normalized)
    if normalized in {"true", "false"}:
        return normalized
    # Unknown ambiguity signals are safer as true until a reviewer resolves them.
    return "true"


def should_keep(row: dict[str, str]) -> tuple[bool, str]:
    sector = (row.get("sector") or "").strip().upper()
    issue_type = (row.get("issue_type") or "").strip().upper()
    category = (row.get("category") or "").strip()

    if sector not in DOMAIN_SECTORS:
        return False, f"non_domain_sector:{sector or 'BLANK'}"
    if issue_type == "ALL_SUPPORT":
        return False, "support_issue_type:ALL_SUPPORT"
    if category in SUPPORT_ONLY_CATEGORIES:
        return False, f"support_category:{category}"
    return True, "kept_domain_candidate"


def clean_row(row: dict[str, str]) -> dict[str, str]:
    cleaned = dict(row)
    cleaned["sector"] = (cleaned.get("sector") or "").strip().upper()
    cleaned["issue_type"] = (cleaned.get("issue_type") or "").strip().upper()
    cleaned["review_status"] = (cleaned.get("review_status") or "PENDING_NATIVE_REVIEW").strip().upper()
    if not (cleaned.get("decision") or "").strip():
        cleaned["decision"] = "UNREVIEWED"
    if not (cleaned.get("reviewer_id") or "").strip():
        cleaned["reviewer_id"] = "UNASSIGNED"
    cleaned["false_friend_risk"] = normalize_bool(cleaned.get("false_friend_risk", ""))
    return cleaned


def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def update_reliability_metadata(kept_count: int, quarantined_count: int, reasons: Counter[str]) -> None:
    if not RELIABILITY_LAYER_PATH.exists():
        return

    data = json.loads(RELIABILITY_LAYER_PATH.read_text(encoding="utf-8"))
    metadata = data.setdefault("metadata", {})
    metadata["version"] = "v1.3-v13.1-candidate-bank-domain-cleanup"
    metadata["updated_at_utc"] = utc_now()

    counts = metadata.setdefault("section_row_counts", {})
    counts["candidate_bank_csv"] = kept_count
    counts["candidate_bank_quarantine_csv"] = quarantined_count

    registry = metadata.setdefault("csv_file_registry", {})
    registry["arabizi_candidate_bank.csv"] = {
        "path": "data/knowledge_base/arabizi/arabizi_candidate_bank.csv",
        "row_count": kept_count,
        "rule": "domain-sector candidate terms only; generic/support/protected rows are quarantined",
        "cleanup_version": CLEANUP_VERSION,
    }
    registry["arabizi_candidate_bank_quarantine.csv"] = {
        "path": "data/knowledge_base/arabizi/arabizi_candidate_bank_quarantine.csv",
        "row_count": quarantined_count,
        "rule": "review-only archive of rows removed from the production promotion queue",
        "cleanup_version": CLEANUP_VERSION,
    }
    metadata["v13_1_candidate_bank_cleanup"] = {
        "cleanup_version": CLEANUP_VERSION,
        "kept_domain_candidates": kept_count,
        "quarantined_rows": quarantined_count,
        "quarantine_reason_counts": dict(sorted(reasons.items())),
        "guardrail": (
            "Only domain-sector rows remain in arabizi_candidate_bank.csv. "
            "Quarantined rows are not eligible for core-vocabulary promotion until "
            "they are manually reclassified into a valid support layer or a domain issue target."
        ),
    }

    RELIABILITY_LAYER_PATH.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    with BANK_PATH.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)

    quarantine_fields = fieldnames + [
        "cleanup_version",
        "cleanup_reason",
        "cleanup_at_utc",
    ]
    kept: list[dict[str, str]] = []
    quarantined: list[dict[str, str]] = []
    reasons: Counter[str] = Counter()
    now = utc_now()

    for row in rows:
        keep, reason = should_keep(row)
        cleaned = clean_row(row)
        if keep:
            kept.append(cleaned)
        else:
            qrow = dict(cleaned)
            qrow["cleanup_version"] = CLEANUP_VERSION
            qrow["cleanup_reason"] = reason
            qrow["cleanup_at_utc"] = now
            quarantined.append(qrow)
            reasons[reason] += 1

    write_csv(BANK_PATH, fieldnames, kept)
    write_csv(QUARANTINE_PATH, quarantine_fields, quarantined)
    update_reliability_metadata(len(kept), len(quarantined), reasons)

    print(f"Cleaned {BANK_PATH.relative_to(ROOT)}")
    print(f"  kept domain candidates: {len(kept)}")
    print(f"  quarantined rows:       {len(quarantined)}")
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count}")


if __name__ == "__main__":
    main()
