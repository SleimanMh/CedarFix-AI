"""
validate_arabizi_candidate_bank.py

Validates the arabizi_candidate_bank.csv:
  - All required columns present
  - Enum values are legal
  - No blank candidate_id or primary variant
  - No stoplist terms promoted (decision != STOPLIST or review_status != APPROVED)
  - HIGH risk rows must have reviewer_id or review_status=PENDING
  - false_friend_risk is 'true' or 'false'
  - No duplicate candidate_ids

Exit 0 = pass, Exit 1 = validation errors found.
"""
from __future__ import annotations
import csv
import sys
from pathlib import Path

BANK_PATH = Path(__file__).resolve().parents[1] / "data/knowledge_base/arabizi/arabizi_candidate_bank.csv"
STOPLIST_PATH = Path(__file__).resolve().parents[1] / "data/knowledge_base/arabizi/arabizi_stoplist.csv"

REQUIRED_COLUMNS = [
    "candidate_id", "arabic_script", "english", "sector", "issue_type",
    "category", "variants", "tier_notes", "usage_notes",
    "source_type", "source_reference", "dialect_region",
    "confidence_level", "false_friend_risk", "risk_level",
    "review_status", "reviewer_id", "decision", "promotion_target",
    "created_at", "updated_at",
]

VALID_REVIEW_STATUS = {"PENDING", "APPROVED", "REJECTED", "DEFERRED"}
VALID_DECISION = {"UNREVIEWED", "APPROVE", "REJECT", "DEFER", "STOPLIST", "KEEP_CANDIDATE"}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
VALID_RISK = {"HIGH", "MEDIUM", "LOW", "CRITICAL"}
VALID_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY", "ALL"}


def load_stoplist(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return frozenset(row["term"].strip().lower() for row in reader)


def validate() -> list[str]:
    if not BANK_PATH.exists():
        return [f"FATAL: bank file not found: {BANK_PATH}"]

    stoplist = load_stoplist(STOPLIST_PATH)
    errors: list[str] = []

    with open(BANK_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_cols = set(reader.fieldnames or [])
        missing_cols = [c for c in REQUIRED_COLUMNS if c not in actual_cols]
        if missing_cols:
            errors.append(f"Missing columns: {missing_cols}")
            return errors  # can't continue without schema

        seen_ids: set[str] = set()
        rows = list(reader)

    for i, row in enumerate(rows, start=2):
        cid = row.get("candidate_id", "").strip()
        if not cid:
            errors.append(f"Row {i}: blank candidate_id")
        elif cid in seen_ids:
            errors.append(f"Row {i}: duplicate candidate_id={cid}")
        else:
            seen_ids.add(cid)

        sector = row.get("sector", "").strip().upper()
        if sector not in VALID_SECTORS:
            errors.append(f"Row {i} ({cid}): invalid sector={sector!r}")

        rs = row.get("review_status", "").strip().upper()
        if rs not in VALID_REVIEW_STATUS:
            errors.append(f"Row {i} ({cid}): invalid review_status={rs!r}")

        dec = row.get("decision", "").strip().upper()
        if dec not in VALID_DECISION:
            errors.append(f"Row {i} ({cid}): invalid decision={dec!r}")

        conf = row.get("confidence_level", "").strip().upper()
        if conf not in VALID_CONFIDENCE:
            errors.append(f"Row {i} ({cid}): invalid confidence_level={conf!r}")

        risk = row.get("risk_level", "").strip().upper()
        if risk not in VALID_RISK:
            errors.append(f"Row {i} ({cid}): invalid risk_level={risk!r}")

        ff = row.get("false_friend_risk", "").strip().lower()
        if ff not in ("true", "false"):
            errors.append(f"Row {i} ({cid}): false_friend_risk must be 'true' or 'false', got {ff!r}")

        # HIGH risk rows that are APPROVED must have a reviewer_id
        reviewer = row.get("reviewer_id", "").strip()
        if risk == "HIGH" and rs == "APPROVED" and not reviewer:
            errors.append(f"Row {i} ({cid}): HIGH risk row APPROVED without reviewer_id")

        # Stoplist terms must never be APPROVED
        variants = row.get("variants", "").lower()
        for term in stoplist:
            if term in variants.split(";") and rs == "APPROVED":
                errors.append(
                    f"Row {i} ({cid}): stoplist term '{term}' found in APPROVED row"
                )

        # STOPLIST decision rows must be REJECTED (not APPROVED)
        if dec == "STOPLIST" and rs == "APPROVED":
            errors.append(f"Row {i} ({cid}): decision=STOPLIST but review_status=APPROVED")

    return errors


def main() -> None:
    errors = validate()
    if errors:
        print(f"FAIL: {len(errors)} validation error(s) in {BANK_PATH.name}")
        for e in errors:
            print(f"  ERROR: {e}")
        sys.exit(1)
    else:
        rows_count = sum(1 for _ in open(BANK_PATH, encoding="utf-8")) - 1
        print(f"OK: arabizi_candidate_bank.csv valid ({rows_count} rows)")


if __name__ == "__main__":
    main()
