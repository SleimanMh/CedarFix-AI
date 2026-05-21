"""
Validate CedarFix external Arabizi source governance files.

The external source layer is intentionally not trusted vocabulary. This checker
guards the boundary between source-backed review candidates and production
promotion files.
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data/knowledge_base/arabizi/external_source_ledger.csv"
OOV_PATH = ROOT / "data/knowledge_base/arabizi/lebanese_external_oov_candidates.csv"

LEDGER_REQUIRED = [
    "source_id",
    "source_name",
    "url",
    "region",
    "license",
    "access_requirement",
    "allowed_uses",
    "blocked_uses",
    "raw_import_allowed",
    "local_status",
    "local_path",
    "citation_required",
    "notes",
    "verified_by",
    "verified_at",
]

OOV_REQUIRED = [
    "external_candidate_id",
    "surface_form",
    "normalized_form",
    "source_ids",
    "region",
    "observed_count_total",
    "document_count_total",
    "rbz_identification_count",
    "rbz_senzi_ai_count",
    "rbz_senzi_sa_count",
    "kaggle_raidy_count",
    "rbz_senzi_lexicon_count",
    "rbz_senzi_large_count",
    "rbz_thesis_translation_count",
    "arabizi_signal_score",
    "suggested_layer",
    "suggested_category",
    "confidence_level",
    "risk_level",
    "false_friend_risk",
    "allowed_uses",
    "blocked_uses",
    "review_status",
    "reviewer_id",
    "decision",
    "must_not_auto_promote",
    "notes",
    "created_at",
]

VALID_REVIEW_STATUS = {"PENDING_NATIVE_REVIEW", "APPROVED", "REJECTED", "DEFERRED"}
VALID_DECISION = {"UNREVIEWED", "APPROVE_FOR_GWB", "APPROVE_FOR_STOPLIST", "APPROVE_FOR_CANDIDATE_BANK", "REJECT", "DEFER"}
VALID_RISK = {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
VALID_CONFIDENCE = {"LOW", "MEDIUM", "HIGH"}
VALID_BOOL = {"true", "false"}
BLOCKED_REQUIRED = {"auto_promotion", "direct_routing", "severity_assignment"}


def read_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    if not path.exists():
        return [], []
    with path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader), list(reader.fieldnames or [])


def missing_columns(cols: list[str], required: list[str], label: str) -> list[str]:
    missing = [col for col in required if col not in cols]
    if missing:
        return [f"FATAL [{label}]: missing columns {missing}"]
    return []


def validate_ledger() -> tuple[list[str], list[str], set[str]]:
    rows, cols = read_csv(LEDGER_PATH)
    errors = missing_columns(cols, LEDGER_REQUIRED, "LEDGER")
    warnings: list[str] = []
    source_ids: set[str] = set()
    if errors:
        return errors, warnings, source_ids
    if not rows:
        return [f"FATAL [LEDGER]: empty or missing file: {LEDGER_PATH}"], warnings, source_ids

    for i, row in enumerate(rows, start=2):
        sid = row.get("source_id", "").strip()
        loc = f"LEDGER row {i} ({sid})"
        if not sid:
            errors.append(f"{loc}: blank source_id")
        if sid in source_ids:
            errors.append(f"{loc}: duplicate source_id")
        source_ids.add(sid)
        if not row.get("url", "").startswith(("http://", "https://")):
            errors.append(f"{loc}: url must be HTTP(S)")
        if not row.get("license", "").strip():
            errors.append(f"{loc}: blank license")
        if not row.get("verified_by", "").strip():
            errors.append(f"{loc}: blank verified_by")
        if "auto_promotion" not in row.get("blocked_uses", "") and row.get("raw_import_allowed") != "NO_RAW_TEXT":
            warnings.append(f"{loc}: blocked_uses should include auto_promotion")
        if "NO_ACCESS_YET" in row.get("raw_import_allowed", "") and row.get("local_status", "").startswith("DOWNLOADED"):
            errors.append(f"{loc}: impossible state: no access but downloaded")

    return errors, warnings, source_ids


def validate_oov(source_ids: set[str]) -> tuple[list[str], list[str]]:
    rows, cols = read_csv(OOV_PATH)
    errors = missing_columns(cols, OOV_REQUIRED, "OOV")
    warnings: list[str] = []
    if errors:
        return errors, warnings
    if not rows:
        return [f"FATAL [OOV]: empty or missing file: {OOV_PATH}"], warnings

    seen_ids: set[str] = set()
    seen_forms: set[str] = set()
    for i, row in enumerate(rows, start=2):
        cid = row.get("external_candidate_id", "").strip()
        loc = f"OOV row {i} ({cid})"
        if not re.fullmatch(r"EXT-LB-OOV-\d{4}", cid):
            errors.append(f"{loc}: invalid external_candidate_id")
        if cid in seen_ids:
            errors.append(f"{loc}: duplicate external_candidate_id")
        seen_ids.add(cid)

        form = row.get("surface_form", "").strip().lower()
        if not form:
            errors.append(f"{loc}: blank surface_form")
        if form in seen_forms:
            errors.append(f"{loc}: duplicate surface_form={form}")
        seen_forms.add(form)

        row_sources = {s for s in row.get("source_ids", "").split("|") if s}
        unknown = row_sources - source_ids
        if unknown:
            errors.append(f"{loc}: unknown source_ids={sorted(unknown)}")

        for count_col in [
            "observed_count_total",
            "document_count_total",
            "rbz_identification_count",
            "rbz_senzi_ai_count",
            "rbz_senzi_sa_count",
            "kaggle_raidy_count",
            "rbz_senzi_lexicon_count",
            "rbz_senzi_large_count",
            "rbz_thesis_translation_count",
            "arabizi_signal_score",
        ]:
            value = row.get(count_col, "")
            if not value.isdigit():
                errors.append(f"{loc}: {count_col} must be integer, got {value!r}")

        if row.get("review_status", "") not in VALID_REVIEW_STATUS:
            errors.append(f"{loc}: invalid review_status={row.get('review_status')!r}")
        if row.get("decision", "") not in VALID_DECISION:
            errors.append(f"{loc}: invalid decision={row.get('decision')!r}")
        if row.get("risk_level", "") not in VALID_RISK:
            errors.append(f"{loc}: invalid risk_level={row.get('risk_level')!r}")
        if row.get("confidence_level", "") not in VALID_CONFIDENCE:
            errors.append(f"{loc}: invalid confidence_level={row.get('confidence_level')!r}")
        if row.get("false_friend_risk", "").lower() not in VALID_BOOL:
            errors.append(f"{loc}: false_friend_risk must be true/false")
        if row.get("must_not_auto_promote", "").lower() != "true":
            errors.append(f"{loc}: external OOV rows must have must_not_auto_promote=true")

        blocked = {part.strip() for part in row.get("blocked_uses", "").split("|")}
        missing = BLOCKED_REQUIRED - blocked
        if missing:
            errors.append(f"{loc}: blocked_uses missing {sorted(missing)}")

        if row.get("review_status") == "APPROVED" and row.get("reviewer_id") == "UNASSIGNED":
            errors.append(f"{loc}: APPROVED row requires human reviewer_id")
        if "raw" in row.get("notes", "").lower() and "raw source text not copied" not in row.get("notes", "").lower():
            warnings.append(f"{loc}: notes mention raw data; confirm no raw text is stored")

    return errors, warnings


def main() -> int:
    ledger_errors, ledger_warnings, source_ids = validate_ledger()
    oov_errors, oov_warnings = validate_oov(source_ids)
    errors = ledger_errors + oov_errors
    warnings = ledger_warnings + oov_warnings

    if errors:
        print("FAIL: validate_arabizi_external_sources")
        for error in errors:
            print(f"ERROR: {error}")
    else:
        print("PASS: validate_arabizi_external_sources")

    for warning in warnings:
        print(f"WARNING: {warning}")

    print(f"Errors: {len(errors)}")
    print(f"Warnings: {len(warnings)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
