"""
validate_arabizi_candidate_bank.py

Validates the controlled Arabizi candidate bank.

This validator distinguishes between staging rows and promotion-ready rows:
  - PENDING/DEFERRED rows may contain broad candidate concepts for review
  - APPROVED promotion rows must resolve to a concrete official taxonomy target
  - production-unsafe constructs such as issue_type=ALL are blocked from promotion
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BANK_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_candidate_bank.csv"
DEFAULT_STOPLIST_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_reliability_layer.json"
GUIDELINES_PATH = ROOT / "docs/ANNOTATION_GUIDELINES.md"

REQUIRED_COLUMNS = [
    "candidate_id",
    "arabic_script",
    "english",
    "sector",
    "issue_type",
    "category",
    "variants",
    "tier_notes",
    "usage_notes",
    "source_type",
    "source_reference",
    "dialect_region",
    "confidence_level",
    "false_friend_risk",
    "risk_level",
    "review_status",
    "reviewer_id",
    "decision",
    "promotion_target",
    "created_at",
    "updated_at",
]

VALID_REVIEW_STATUS = {"PENDING", "APPROVED", "REJECTED", "NEEDS_EVIDENCE", "DEFERRED"}
VALID_DECISION = {
    "UNREVIEWED",
    "APPROVE",
    "PROMOTE_TO_CORE",
    "REJECT",
    "DEFER",
    "STOPLIST",
    "KEEP_CANDIDATE",
    "MERGE_DUPLICATE",
}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
VALID_RISK = {"HIGH", "MEDIUM", "LOW", "CRITICAL"}
VALID_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY", "OTHER", "ALL"}
SUPPORT_CATEGORIES = {
    "connector",
    "time_expr",
    "severity_marker",
    "complaint_phrase",
    "institution",
    # Candidate-bank staging categories used by the current imported row set.
    "connector_time",
    "complaint_starter",
    "noun_entity",
    "noun_location",
    "noun_event",
    "adj_quality",
    "adj_risk",
    "adj_severity",
    "adv_severity",
}
PROMOTE_DECISIONS = {"APPROVE", "PROMOTE_TO_CORE"}
SAFETY_TERMS = {
    "fire",
    "nar",
    "7ari2a",
    "7are2",
    "sa32",
    "sa3q",
    "shar2ata",
    "silk",
    "wire",
    "ghaz",
    "gas",
    "collapse",
    "inhiyar",
    "zalzal",
    "armed",
    "masalla7",
    "suspicious",
    "mshbouh",
    "injury",
    "isabe",
    "wfat",
}


def load_expected_issue_types() -> dict[str, set[str]]:
    text = GUIDELINES_PATH.read_text(encoding="utf-8")
    match = re.search(r"```\n(ROADS:.*?)\n```", text, re.S)
    if not match:
        raise ValueError("Could not find issue taxonomy block in ANNOTATION_GUIDELINES.md")

    expected: dict[str, set[str]] = {}
    for line in match.group(1).splitlines():
        sector, values = line.split(":", 1)
        expected[sector.strip().upper()] = {value.strip().upper() for value in values.split(",")}
    return expected


def load_stoplist(path: Path) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        terms: set[str] = set()
        for row in data.get("stoplist", []):
            terms.add((row.get("term") or "").strip().lower())
            terms.add((row.get("normalized_term") or "").strip().lower())
        terms.discard("")
        return frozenset(terms)
    with open(path, encoding="utf-8") as f:
        terms = set()
        for row in csv.DictReader(f):
            terms.add((row.get("term") or "").strip().lower())
            terms.add((row.get("normalized_term") or "").strip().lower())
        terms.discard("")
        return frozenset(terms)


def parse_promotion_target(raw: str) -> tuple[str, str] | None:
    target = raw.strip().replace(".", "/")
    if not target or "/" not in target:
        return None
    sector, issue_type = [part.strip().upper() for part in target.split("/", 1)]
    return (sector, issue_type) if sector and issue_type else None


def split_variants(raw: str) -> list[str]:
    return [variant.strip() for variant in raw.split(";") if variant.strip()]


def is_safety_sensitive(row: dict[str, str]) -> bool:
    haystack = " ".join(
        [
            row.get("sector", ""),
            row.get("issue_type", ""),
            row.get("category", ""),
            row.get("variants", ""),
            row.get("english", ""),
            row.get("usage_notes", ""),
        ]
    ).lower()
    return any(term in haystack for term in SAFETY_TERMS)


def validate(bank_path: Path, stoplist_path: Path) -> tuple[list[str], list[str], int]:
    if not bank_path.exists():
        return [f"FATAL: bank file not found: {bank_path}"], [], 0

    stoplist = load_stoplist(stoplist_path)
    taxonomy = load_expected_issue_types()
    errors: list[str] = []
    warnings: list[str] = []

    with open(bank_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        actual_cols = set(reader.fieldnames or [])
        missing_cols = [column for column in REQUIRED_COLUMNS if column not in actual_cols]
        if missing_cols:
            return [f"Missing columns: {missing_cols}"], warnings, 0
        rows = list(reader)

    seen_ids: set[str] = set()
    variant_targets: dict[str, set[tuple[str, str]]] = defaultdict(set)

    for i, row in enumerate(rows, start=2):
        cid = row.get("candidate_id", "").strip()
        if not cid:
            errors.append(f"Row {i}: blank candidate_id")
        elif cid in seen_ids:
            errors.append(f"Row {i}: duplicate candidate_id={cid}")
        else:
            seen_ids.add(cid)

        sector = row.get("sector", "").strip().upper()
        issue_type = row.get("issue_type", "").strip().upper()
        category = row.get("category", "").strip()
        review_status = row.get("review_status", "").strip().upper()
        decision = row.get("decision", "").strip().upper()
        confidence = row.get("confidence_level", "").strip().upper()
        risk = row.get("risk_level", "").strip().upper()
        false_friend = row.get("false_friend_risk", "").strip().lower()
        reviewer = row.get("reviewer_id", "").strip()
        variants = split_variants(row.get("variants", ""))

        if sector not in VALID_SECTORS:
            errors.append(f"Row {i} ({cid}): invalid sector={sector!r}")
        if issue_type != "ALL" and sector in taxonomy and issue_type not in taxonomy[sector]:
            message = f"Row {i} ({cid}): issue_type={issue_type!r} not in taxonomy for {sector}"
            if review_status == "APPROVED" or decision in PROMOTE_DECISIONS:
                errors.append(message)
            else:
                warnings.append(message)
        if sector == "ALL" and category not in SUPPORT_CATEGORIES:
            errors.append(f"Row {i} ({cid}): sector=ALL allowed only for support categories")
        if review_status not in VALID_REVIEW_STATUS:
            errors.append(f"Row {i} ({cid}): invalid review_status={review_status!r}")
        if decision not in VALID_DECISION:
            errors.append(f"Row {i} ({cid}): invalid decision={decision!r}")
        if confidence not in VALID_CONFIDENCE:
            errors.append(f"Row {i} ({cid}): invalid confidence_level={confidence!r}")
        if risk not in VALID_RISK:
            errors.append(f"Row {i} ({cid}): invalid risk_level={risk!r}")
        if false_friend not in ("true", "false"):
            errors.append(f"Row {i} ({cid}): false_friend_risk must be true/false")
        if not variants:
            errors.append(f"Row {i} ({cid}): variants is empty")

        if review_status in {"APPROVED", "REJECTED"} and not reviewer:
            errors.append(f"Row {i} ({cid}): {review_status} row requires reviewer_id")
        if is_safety_sensitive(row) and review_status in {"APPROVED", "REJECTED"} and not reviewer:
            errors.append(f"Row {i} ({cid}): safety-sensitive reviewed row requires manual reviewer_id")

        if decision in PROMOTE_DECISIONS:
            if review_status != "APPROVED":
                errors.append(f"Row {i} ({cid}): promotion decision requires review_status=APPROVED")
            if sector == "ALL" or issue_type == "ALL":
                errors.append(f"Row {i} ({cid}): ALL sector/issue_type cannot be promoted")
            target = parse_promotion_target(row.get("promotion_target", ""))
            if target is None:
                errors.append(f"Row {i} ({cid}): promotion decision requires sector/issue_type promotion_target")
            else:
                target_sector, target_issue_type = target
                if target_sector not in taxonomy:
                    errors.append(f"Row {i} ({cid}): invalid promotion target sector={target_sector}")
                elif target_issue_type not in taxonomy[target_sector]:
                    errors.append(
                        f"Row {i} ({cid}): invalid promotion target issue_type={target_sector}/{target_issue_type}"
                    )

        variant_lowers = [variant.lower() for variant in variants]
        blocked = sorted(set(variant_lowers) & stoplist)
        if blocked and (review_status == "APPROVED" or decision in PROMOTE_DECISIONS):
            errors.append(f"Row {i} ({cid}): stoplist term(s) cannot be approved/promoted: {blocked}")
        if decision == "STOPLIST" and review_status == "APPROVED":
            errors.append(f"Row {i} ({cid}): decision=STOPLIST cannot have review_status=APPROVED")

        for variant in variant_lowers:
            variant_targets[variant].add((sector, issue_type))

    false_friend_rows = {
        variant.lower(): row.get("false_friend_risk", "").strip().lower() == "true"
        for row in rows
        for variant in split_variants(row.get("variants", ""))
    }
    for variant, targets in sorted(variant_targets.items()):
        concrete_targets = {target for target in targets if "ALL" not in target}
        if len(concrete_targets) > 1 and not false_friend_rows.get(variant, False):
            warnings.append(
                f"Variant {variant!r} appears under multiple meanings {sorted(concrete_targets)}; "
                "mark false_friend_risk=true before approval"
            )

    return errors, warnings, len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Arabizi candidate bank.")
    parser.add_argument("--candidate-bank", type=Path, default=DEFAULT_BANK_PATH)
    parser.add_argument("--stoplist-path", type=Path, default=DEFAULT_STOPLIST_PATH)
    parser.add_argument("--strict-warnings", action="store_true", help="Treat warnings as failures")
    args = parser.parse_args()

    errors, warnings, rows_count = validate(args.candidate_bank, args.stoplist_path)
    for warning in warnings:
        print(f"WARNING {warning}")

    if errors or (args.strict_warnings and warnings):
        print(f"FAIL: {len(errors)} error(s), {len(warnings)} warning(s) in {args.candidate_bank.name}")
        for error in errors:
            print(f"  ERROR: {error}")
        sys.exit(1)

    print(f"OK: arabizi_candidate_bank.csv valid ({rows_count} rows, {len(warnings)} warnings)")


if __name__ == "__main__":
    main()
