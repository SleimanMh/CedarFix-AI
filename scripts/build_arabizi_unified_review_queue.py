#!/usr/bin/env python
"""Build one human-review queue across all Arabizi review layers.

This script intentionally creates a review projection. It does not replace the
layer-specific source files, and it never promotes rows into production vocab.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
ARABIZI_DIR = ROOT / "data" / "knowledge_base" / "arabizi"
CORPUS_DIR = ROOT / "data" / "corpus"

OUTPUT = ARABIZI_DIR / "arabizi_unified_review_queue.csv"
SUMMARY_OUTPUT = ARABIZI_DIR / "arabizi_unified_review_queue_summary.json"

COMMON_BLOCKED_DECISIONS = (
    "auto_promotion|direct_routing|severity_assignment|sector_classification|"
    "issue_type_decision|core_vocab_promotion_without_layer_review"
)

FIELDNAMES = [
    "review_queue_id",
    "review_key",
    "review_family",
    "review_priority",
    "source_file",
    "source_row_id",
    "source_layer",
    "surface_form",
    "normalized_form",
    "canonical_form",
    "arabic_script",
    "english_gloss",
    "sector",
    "issue_type",
    "category",
    "dialect_region",
    "confidence_level",
    "risk_level",
    "false_friend_risk",
    "allowed_uses",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "decision",
    "suggested_action",
    "promotion_target",
    "must_not_auto_promote",
    "observed_count_total",
    "document_count_total",
    "source_reference",
    "source_ids",
    "usage_notes",
    "notes",
    "created_at",
    "original_payload_json",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [
            {k: (v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if any((v or "").strip() for v in row.values())
        ]


def first(row: dict[str, str], *keys: str, default: str = "") -> str:
    for key in keys:
        value = (row.get(key) or "").strip()
        if value:
            return value
    return default


def normalize_bool(value: str, default: str = "true") -> str:
    value_norm = (value or "").strip().lower()
    if value_norm in {"true", "yes", "1", "y"}:
        return "true"
    if value_norm in {"false", "no", "0", "n"}:
        return "false"
    return default


def review_key(*parts: str) -> str:
    cleaned = [part.strip().lower() for part in parts if part and part.strip()]
    return "|".join(cleaned)


def payload(row: dict[str, str]) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def base_row(row: dict[str, str], *, source_file: str, review_family: str) -> dict[str, str]:
    return {
        "review_queue_id": "",
        "review_key": "",
        "review_family": review_family,
        "review_priority": "P3_REVIEW",
        "source_file": source_file,
        "source_row_id": "",
        "source_layer": "",
        "surface_form": "",
        "normalized_form": "",
        "canonical_form": "",
        "arabic_script": "",
        "english_gloss": "",
        "sector": "",
        "issue_type": "",
        "category": "",
        "dialect_region": "",
        "confidence_level": "",
        "risk_level": "",
        "false_friend_risk": "false",
        "allowed_uses": "",
        "blocked_uses": COMMON_BLOCKED_DECISIONS,
        "review_status": first(row, "review_status", default="PENDING_REVIEW"),
        "reviewer_id": first(row, "reviewer_id", default="UNASSIGNED"),
        "decision": first(row, "decision", "action", default="UNREVIEWED"),
        "suggested_action": first(row, "suggested_action", "action"),
        "promotion_target": first(row, "promotion_target"),
        "must_not_auto_promote": normalize_bool(first(row, "must_not_auto_promote"), default="true"),
        "observed_count_total": first(row, "observed_count_total", "frequency"),
        "document_count_total": first(row, "document_count_total", "report_count"),
        "source_reference": first(row, "source_reference", "source_type"),
        "source_ids": first(row, "source_ids"),
        "usage_notes": first(row, "usage_notes", "override_reason", "reason"),
        "notes": first(row, "notes", "cleanup_reason", "recommended_replacements"),
        "created_at": first(row, "created_at", "cleanup_at_utc", default=now_utc()),
        "original_payload_json": payload(row),
    }


def map_candidate_bank(row: dict[str, str], source_file: str, family: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family=family)
    out.update(
        {
            "review_priority": "P1_DOMAIN_REVIEW" if family == "DOMAIN_CANDIDATE" else "P2_QUARANTINE_REVIEW",
            "source_row_id": first(row, "candidate_id"),
            "source_layer": "candidate_bank" if family == "DOMAIN_CANDIDATE" else "candidate_bank_quarantine",
            "surface_form": first(row, "variants", "english", "arabic_script"),
            "normalized_form": first(row, "english", "arabic_script"),
            "canonical_form": first(row, "english", "arabic_script"),
            "arabic_script": first(row, "arabic_script"),
            "english_gloss": first(row, "english"),
            "sector": first(row, "sector"),
            "issue_type": first(row, "issue_type"),
            "category": first(row, "category"),
            "dialect_region": first(row, "dialect_region"),
            "confidence_level": first(row, "confidence_level"),
            "risk_level": first(row, "risk_level"),
            "false_friend_risk": normalize_bool(first(row, "false_friend_risk"), default="false"),
            "source_reference": first(row, "source_reference", "source_type"),
            "usage_notes": first(row, "usage_notes"),
        }
    )
    out["review_key"] = review_key(out["source_layer"], out["sector"], out["issue_type"], out["normalized_form"])
    return out


def map_external_oov(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="EXTERNAL_OOV_CANDIDATE")
    priority = "P1_EXTERNAL_CROSS_SOURCE_REVIEW"
    if "SAFETY" in first(row, "suggested_layer", "suggested_category").upper():
        priority = "P0_SAFETY_OR_PROFANITY_REVIEW"
    elif int(first(row, "observed_count_total", default="0") or "0") >= 50:
        priority = "P1_HIGH_FREQUENCY_EXTERNAL_REVIEW"
    out.update(
        {
            "review_priority": priority,
            "source_row_id": first(row, "external_candidate_id"),
            "source_layer": first(row, "suggested_layer", default="external_oov"),
            "surface_form": first(row, "surface_form"),
            "normalized_form": first(row, "normalized_form", "surface_form"),
            "canonical_form": first(row, "normalized_form", "surface_form"),
            "category": first(row, "suggested_category"),
            "dialect_region": first(row, "region"),
            "confidence_level": first(row, "confidence_level"),
            "risk_level": first(row, "risk_level"),
            "false_friend_risk": normalize_bool(first(row, "false_friend_risk"), default="false"),
            "allowed_uses": first(row, "allowed_uses"),
            "blocked_uses": first(row, "blocked_uses", default=COMMON_BLOCKED_DECISIONS),
            "source_ids": first(row, "source_ids"),
            "notes": first(row, "notes"),
        }
    )
    out["review_key"] = review_key("external_oov", out["normalized_form"], out["source_layer"])
    return out


def map_general_word(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="GENERAL_SUPPORT_WORD")
    out.update(
        {
            "review_priority": "P2_GENERAL_SUPPORT_REVIEW",
            "source_row_id": first(row, "word_id"),
            "source_layer": "general_word_bank",
            "surface_form": first(row, "romanized_canonical", "variants"),
            "normalized_form": first(row, "romanized_canonical"),
            "canonical_form": first(row, "romanized_canonical"),
            "arabic_script": first(row, "arabic_script"),
            "english_gloss": first(row, "english_gloss"),
            "category": first(row, "category"),
            "dialect_region": first(row, "dialect_region"),
            "confidence_level": first(row, "confidence_level"),
            "false_friend_risk": normalize_bool(first(row, "false_friend_risk"), default="false"),
            "allowed_uses": first(row, "allowed_uses"),
            "blocked_uses": first(row, "blocked_uses", default=COMMON_BLOCKED_DECISIONS),
            "source_reference": first(row, "source_reference"),
            "usage_notes": first(row, "usage_notes"),
            "notes": first(row, "variants"),
        }
    )
    out["review_key"] = review_key("general_word", out["normalized_form"], out["category"])
    return out


def map_protected_combo(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="PROTECTED_COMBO")
    out.update(
        {
            "review_priority": "P1_PHRASE_LOCK_REVIEW",
            "source_row_id": first(row, "combo_id"),
            "source_layer": "protected_combos",
            "surface_form": first(row, "romanized_canonical"),
            "normalized_form": first(row, "romanized_canonical"),
            "canonical_form": first(row, "romanized_canonical"),
            "arabic_script": first(row, "arabic_phrase"),
            "english_gloss": first(row, "english_gloss"),
            "sector": first(row, "combined_sector"),
            "issue_type": first(row, "combined_issue_type"),
            "category": first(row, "override_type"),
            "confidence_level": first(row, "confidence_level"),
            "risk_level": first(row, "combined_severity_hint"),
            "false_friend_risk": normalize_bool(first(row, "false_friend_risk"), default="false"),
            "allowed_uses": "phrase_lock|normalization_support|false_positive_suppression",
            "blocked_uses": "naive_token_split|auto_promotion_without_combo_review",
            "source_reference": first(row, "source_reference"),
            "usage_notes": first(row, "override_reason"),
            "notes": first(row, "component_tokens"),
        }
    )
    out["review_key"] = review_key("protected_combo", out["normalized_form"], out["category"])
    return out


def map_stoplist(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="STOPLIST_TERM")
    out.update(
        {
            "review_priority": "P1_STOPLIST_AUDIT",
            "source_row_id": first(row, "term", "normalized_term"),
            "source_layer": "stoplist",
            "surface_form": first(row, "term"),
            "normalized_form": first(row, "normalized_term", "term"),
            "canonical_form": first(row, "normalized_term", "term"),
            "sector": "ALL",
            "issue_type": "STOPLIST",
            "category": "stoplist",
            "risk_level": first(row, "risk_level"),
            "allowed_uses": "stoplist_filtering|oov_suppression|false_positive_suppression",
            "blocked_uses": "routing|severity_assignment|sector_classification|issue_type_decision|core_vocab_promotion",
            "review_status": "STOPLIST_ACTIVE",
            "source_reference": first(row, "source_reference"),
            "usage_notes": first(row, "reason"),
        }
    )
    out["review_key"] = review_key("stoplist", out["normalized_form"])
    return out


def map_surface_form(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="GENERATED_SURFACE_FORM")
    out.update(
        {
            "review_priority": "P5_GENERATED_SURFACE_AUDIT",
            "source_row_id": first(row, "surface_id"),
            "source_layer": first(row, "source_layer", default="surface_forms"),
            "surface_form": first(row, "surface_form"),
            "normalized_form": first(row, "normalized_surface"),
            "canonical_form": first(row, "canonical_form"),
            "sector": first(row, "sector"),
            "issue_type": first(row, "issue_type"),
            "category": first(row, "category"),
            "confidence_level": first(row, "confidence_level"),
            "risk_level": first(row, "risk_level"),
            "false_friend_risk": normalize_bool(first(row, "false_friend_risk"), default="false"),
            "allowed_uses": first(row, "allowed_uses"),
            "blocked_uses": first(row, "blocked_uses", default=COMMON_BLOCKED_DECISIONS),
            "review_status": first(row, "review_status", default="REVIEW_ONLY_GENERATED"),
            "source_reference": first(row, "source_reference"),
            "notes": first(row, "variant_rule"),
        }
    )
    out["review_key"] = review_key("surface_form", out["normalized_form"], out["source_layer"], out["source_row_id"])
    return out


def map_local_oov(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="LOCAL_OOV_OBSERVATION")
    priority = "P1_LOCAL_OOV_REVIEW" if first(row, "risk_hint").upper() else "P2_LOCAL_OOV_REVIEW"
    out.update(
        {
            "review_priority": priority,
            "source_row_id": first(row, "candidate_id"),
            "source_layer": "local_oov_review_queue",
            "surface_form": first(row, "raw_variants", "normalized_token"),
            "normalized_form": first(row, "normalized_token"),
            "canonical_form": first(row, "normalized_token"),
            "sector": first(row, "proposed_sector"),
            "issue_type": first(row, "proposed_issue_type"),
            "category": first(row, "risk_hint"),
            "risk_level": first(row, "risk_hint"),
            "allowed_uses": "human_review|oov_triage|training_label_candidate",
            "blocked_uses": "auto_promotion_without_reviewer_decision|direct_routing",
            "source_reference": first(row, "batch"),
            "usage_notes": first(row, "example_text"),
            "notes": first(row, "notes"),
        }
    )
    out["review_key"] = review_key("local_oov", out["normalized_form"], out["sector"], out["issue_type"])
    return out


def map_bfl_quarantine(row: dict[str, str], source_file: str) -> dict[str, str]:
    out = base_row(row, source_file=source_file, review_family="BFL_QUARANTINE")
    out.update(
        {
            "review_priority": first(row, "review_priority", default="P0_AMBIGUITY_REVIEW"),
            "source_row_id": first(row, "variant_id", "candidate_id"),
            "source_layer": "bfl_quarantine",
            "surface_form": first(row, "variant"),
            "normalized_form": first(row, "normalized_variant", "variant"),
            "canonical_form": first(row, "normalized_variant", "variant"),
            "sector": first(row, "sector"),
            "issue_type": first(row, "issue_type"),
            "category": first(row, "category"),
            "risk_level": first(row, "trust_status"),
            "review_status": first(row, "trust_status", default="QUARANTINED"),
            "decision": first(row, "action", default="DO_NOT_IMPORT_UNTIL_REVIEWED"),
            "allowed_uses": "manual_review_only",
            "blocked_uses": "auto_import|auto_promotion|direct_routing",
            "usage_notes": first(row, "reason"),
            "notes": first(row, "recommended_replacements"),
        }
    )
    out["review_key"] = review_key("bfl_quarantine", out["normalized_form"], out["sector"], out["issue_type"])
    return out


SOURCES: list[tuple[Path, str, Callable[[dict[str, str], str], dict[str, str]]]] = [
    (ARABIZI_DIR / "arabizi_candidate_bank.csv", "DOMAIN_CANDIDATE", lambda r, s: map_candidate_bank(r, s, "DOMAIN_CANDIDATE")),
    (ARABIZI_DIR / "arabizi_candidate_bank_quarantine.csv", "QUARANTINED_CANDIDATE", lambda r, s: map_candidate_bank(r, s, "QUARANTINED_CANDIDATE")),
    (ARABIZI_DIR / "lebanese_external_oov_candidates.csv", "EXTERNAL_OOV_CANDIDATE", map_external_oov),
    (ARABIZI_DIR / "arabizi_general_word_bank.csv", "GENERAL_SUPPORT_WORD", map_general_word),
    (ARABIZI_DIR / "arabizi_protected_combos.csv", "PROTECTED_COMBO", map_protected_combo),
    (ARABIZI_DIR / "arabizi_stoplist.csv", "STOPLIST_TERM", map_stoplist),
    (ARABIZI_DIR / "arabizi_surface_forms_v15.csv", "GENERATED_SURFACE_FORM", map_surface_form),
    (CORPUS_DIR / "arabizi_oov_review_queue_v1.csv", "LOCAL_OOV_OBSERVATION", map_local_oov),
    (ARABIZI_DIR / "bfl_quarantine_p0.csv", "BFL_QUARANTINE", map_bfl_quarantine),
]


def build() -> tuple[list[dict[str, str]], dict[str, object]]:
    rows: list[dict[str, str]] = []
    source_counts: Counter[str] = Counter()
    family_counts: Counter[str] = Counter()
    priority_counts: Counter[str] = Counter()

    for path, _family, mapper in SOURCES:
        if not path.exists():
            continue
        source_file = str(path.relative_to(ROOT)).replace("\\", "/")
        for source_row in read_csv(path):
            unified = mapper(source_row, source_file)
            unified["review_queue_id"] = f"ARZ-URQ-{len(rows) + 1:06d}"
            rows.append({field: unified.get(field, "") for field in FIELDNAMES})
            source_counts[source_file] += 1
            family_counts[unified["review_family"]] += 1
            priority_counts[unified["review_priority"]] += 1

    summary: dict[str, object] = {
        "generated_at_utc": now_utc(),
        "output": str(OUTPUT.relative_to(ROOT)).replace("\\", "/"),
        "row_count": len(rows),
        "source_counts": dict(sorted(source_counts.items())),
        "review_family_counts": dict(sorted(family_counts.items())),
        "review_priority_counts": dict(sorted(priority_counts.items())),
        "guardrail": "Unified review queue is a human-review projection only. It does not replace source files and does not promote production vocabulary.",
    }
    return rows, summary


def main() -> None:
    rows, summary = build()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    with SUMMARY_OUTPUT.open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"Wrote {len(rows)} rows -> {OUTPUT.relative_to(ROOT)}")
    for family, count in sorted(summary["review_family_counts"].items()):
        print(f"  {family}: {count}")


if __name__ == "__main__":
    main()
