"""
validate_arabizi_support_layers.py

V12 governance validator for the four support-layer artefacts:

  1. arabizi_general_word_bank.csv     — T3/T4 generic context words
  2. arabizi_protected_combos.csv      — phrase locks that override tokenisation
  3. arabizi_stoplist.csv              — noise / wrong-form terms
  4. arabizi_reliability_layer.json   — governance source-of-truth (metadata only)

Central rules verified:
  • Generic word bank entries NEVER assist routing, severity, or sector classification
  • Protected combos lock multi-token phrases; bank-extracted combos carry SYSTEM-V12
  • Stoplist entries are never auto-promoted (must_not_auto_promote=true)
  • Every APPROVED row must have a non-UNASSIGNED reviewer_id
  • must_not_auto_promote is a required boolean column on all three CSVs

Usage:
  python scripts/validate_arabizi_support_layers.py
  python scripts/validate_arabizi_support_layers.py --strict   # warnings become errors
  python scripts/validate_arabizi_support_layers.py --fix-ids  # list entries with bad IDs
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

GWB_PATH = ROOT / "data/knowledge_base/arabizi/arabizi_general_word_bank.csv"
PC_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_protected_combos.csv"
SL_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_stoplist.csv"
RL_PATH  = ROOT / "data/knowledge_base/arabizi/arabizi_reliability_layer.json"

# ── Frozen enumerations ──────────────────────────────────────────────────────

VALID_TIERS = {"T1_CORE_ROUTING", "T2_ISSUE_SPECIFIC", "T3_GENERIC_SUPPORT", "T4_VARIANT_LOOKUP"}
VALID_CONFIDENCE = {"HIGH", "MEDIUM", "LOW", "UNKNOWN"}
VALID_FALSE_FRIEND = {"true", "false"}
VALID_REVIEW_STATUS_GWB = {"PENDING_NATIVE_REVIEW", "APPROVED", "REJECTED", "DEFERRED"}
VALID_REVIEW_STATUS_PC  = {"PENDING_NATIVE_REVIEW", "APPROVED", "REJECTED", "DEFERRED"}
VALID_REVIEW_STATUS_SL  = {"PENDING_NATIVE_REVIEW", "APPROVED", "DEFERRED"}
VALID_SECTORS = {"ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY", "OTHER", "ALL"}
VALID_OVERRIDE_TYPES = {
    "COMPOUND_NOUN", "STATUS_PHRASE", "NEGATION_COMBO", "TEMPORAL_COMBO",
    "LOCATION_COMBO", "EVIDENCE_COMBO", "RISK_COMBO", "URGENCY_COMBO", "IDIOM",
    # V14 expansion pack types
    "DUPLICATE_CONTEXT_LOCK", "CLARITY_LOCK", "EVIDENCE_LOCK", "TIME_LOCK",
    "LOCATION_LOCK", "WATER_CONTEXT_LOCK", "FLOODING_CONTEXT_LOCK",
    "ELECTRICITY_CONTEXT_LOCK", "WASTE_CONTEXT_LOCK", "SAFETY_HITL_CONTEXT_LOCK",
}
VALID_SEVERITY_HINTS = {"LOW", "MEDIUM", "HIGH", "CRITICAL", "NONE", ""}

# The BLOCKING rule: generic vocab may NEVER influence these
GWB_REQUIRED_BLOCKED = {"routing", "severity_assignment", "sector_classification"}

# Required columns per file
GWB_REQUIRED_COLS = [
    "word_id", "arabic_script", "english_gloss", "romanized_canonical",
    "variants", "tier", "category", "allowed_uses", "blocked_uses",
    "dialect_region", "confidence_level", "false_friend_risk", "usage_notes",
    "source_reference", "review_status", "created_at",
    "reviewer_id", "must_not_auto_promote",
]
PC_REQUIRED_COLS = [
    "combo_id", "arabic_phrase", "romanized_canonical", "english_gloss",
    "component_tokens", "combined_sector", "combined_issue_type",
    "combined_severity_hint", "override_type", "override_reason",
    "false_friend_risk", "confidence_level", "source_reference",
    "review_status", "reviewer_id", "created_at",
    "must_not_auto_promote",
]
SL_REQUIRED_COLS = [
    "term", "normalized_term", "reason", "risk_level",
    "source_reference", "reviewer_id", "created_at",
    "must_not_auto_promote",
]

# ── Helpers ──────────────────────────────────────────────────────────────────

def read_csv(path: Path) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], []
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        cols = list(reader.fieldnames or [])
    return rows, cols


def col_check(actual_cols: list[str], required: list[str], label: str) -> list[str]:
    missing = [c for c in required if c not in actual_cols]
    if missing:
        return [f"FATAL [{label}]: missing required columns: {missing}"]
    return []


def bool_field(val: str) -> bool | None:
    """Parse must_not_auto_promote / false_friend_risk — returns None if unparseable."""
    v = val.strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


# ── GWB validator ────────────────────────────────────────────────────────────

def validate_gwb(strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rows, cols = read_csv(GWB_PATH)

    if not rows:
        return [f"FATAL [GWB]: file not found or empty: {GWB_PATH}"], []

    errs = col_check(cols, GWB_REQUIRED_COLS, "GWB")
    if errs:
        return errs, []

    seen_ids: set[str] = set()

    for i, row in enumerate(rows, start=2):
        wid = row.get("word_id", "").strip()
        loc = f"GWB row {i} ({wid})"

        # ID format
        if not re.fullmatch(r"GW\d{4}", wid):
            errors.append(f"{loc}: word_id must match GW[0-9]{{4}}, got {wid!r}")
        if wid in seen_ids:
            errors.append(f"{loc}: duplicate word_id")
        seen_ids.add(wid)

        # Central rule: routing/severity/sector must be in blocked_uses
        blocked = {b.strip() for b in row.get("blocked_uses", "").split("|")}
        missing_blocks = GWB_REQUIRED_BLOCKED - blocked
        if missing_blocks:
            errors.append(
                f"{loc}: blocked_uses missing required blocks: {sorted(missing_blocks)}"
            )

        # Central rule: routing_context must NOT appear in allowed_uses
        if "routing_context" in row.get("allowed_uses", ""):
            errors.append(f"{loc}: allowed_uses must NOT contain 'routing_context'")
        if "routing" in row.get("allowed_uses", "").split("|"):
            errors.append(f"{loc}: allowed_uses must NOT contain 'routing'")

        # Tier
        tier = row.get("tier", "").strip()
        if tier not in VALID_TIERS:
            warnings.append(f"{loc}: unrecognised tier={tier!r}")

        # review_status
        rs = row.get("review_status", "").strip()
        if rs not in VALID_REVIEW_STATUS_GWB:
            errors.append(f"{loc}: invalid review_status={rs!r}")

        # reviewer_id: APPROVED rows need a real reviewer
        rid = row.get("reviewer_id", "").strip()
        if rs == "APPROVED" and rid in ("UNASSIGNED", ""):
            errors.append(f"{loc}: APPROVED row must have reviewer_id (not UNASSIGNED)")

        # must_not_auto_promote
        mnap = bool_field(row.get("must_not_auto_promote", ""))
        if mnap is None:
            errors.append(f"{loc}: must_not_auto_promote must be true/false")
        elif mnap is False:
            errors.append(
                f"{loc}: generic word bank entries must have must_not_auto_promote=true"
            )

        # false_friend_risk
        ff = row.get("false_friend_risk", "").strip().lower()
        if ff not in VALID_FALSE_FRIEND:
            (errors if strict else warnings).append(
                f"{loc}: false_friend_risk must be true/false, got {ff!r}"
            )

        # confidence_level
        cl = row.get("confidence_level", "").strip().upper()
        if cl not in VALID_CONFIDENCE:
            warnings.append(f"{loc}: unrecognised confidence_level={cl!r}")

    return errors, warnings


# ── PC validator ─────────────────────────────────────────────────────────────

def validate_pc(strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rows, cols = read_csv(PC_PATH)

    if not rows:
        return [f"FATAL [PC]: file not found or empty: {PC_PATH}"], []

    errs = col_check(cols, PC_REQUIRED_COLS, "PC")
    if errs:
        return errs, []

    seen_ids: set[str] = set()
    bank_ids: set[str] = set()
    new_ids: set[str] = set()

    for i, row in enumerate(rows, start=2):
        cid = row.get("combo_id", "").strip()
        loc = f"PC row {i} ({cid})"

        if not re.fullmatch(r"PC-\d{4}", cid):
            errors.append(f"{loc}: combo_id must match PC-[0-9]{{4}}, got {cid!r}")
        if cid in seen_ids:
            errors.append(f"{loc}: duplicate combo_id")
        seen_ids.add(cid)

        is_bank = row.get("source_reference", "").startswith("candidate_bank:")
        if is_bank:
            bank_ids.add(cid)
        else:
            new_ids.add(cid)

        # combined_sector
        sector = row.get("combined_sector", "").strip().upper()
        if sector not in VALID_SECTORS:
            errors.append(f"{loc}: invalid combined_sector={sector!r}")

        # combined_severity_hint
        sev = row.get("combined_severity_hint", "").strip().upper()
        if sev not in VALID_SEVERITY_HINTS and sev != "":
            warnings.append(f"{loc}: unrecognised combined_severity_hint={sev!r}")

        # override_type
        ot = row.get("override_type", "").strip()
        if ot not in VALID_OVERRIDE_TYPES:
            warnings.append(f"{loc}: unrecognised override_type={ot!r}")

        # review_status
        rs = row.get("review_status", "").strip()
        if rs not in VALID_REVIEW_STATUS_PC:
            errors.append(f"{loc}: invalid review_status={rs!r}")

        # reviewer_id rules
        rid = row.get("reviewer_id", "").strip()
        if rs == "APPROVED" and rid in ("UNASSIGNED", ""):
            errors.append(f"{loc}: APPROVED row requires reviewer_id (not UNASSIGNED)")
        # Bank entries extracted by V12 build script should carry SYSTEM-V12
        if is_bank and rs == "APPROVED" and rid == "UNASSIGNED":
            errors.append(
                f"{loc}: bank-extracted APPROVED combo must have reviewer_id=SYSTEM-V12"
            )

        # must_not_auto_promote
        mnap = bool_field(row.get("must_not_auto_promote", ""))
        if mnap is None:
            errors.append(f"{loc}: must_not_auto_promote must be true/false")
        else:
            # Bank APPROVED entries: must_not_auto_promote=false is acceptable
            # New PENDING entries: must be true
            if rs == "PENDING_NATIVE_REVIEW" and mnap is False:
                (errors if strict else warnings).append(
                    f"{loc}: PENDING_NATIVE_REVIEW combo should have must_not_auto_promote=true"
                )

        # false_friend_risk
        ff = row.get("false_friend_risk", "").strip().lower()
        if ff not in VALID_FALSE_FRIEND:
            (errors if strict else warnings).append(
                f"{loc}: false_friend_risk must be true/false, got {ff!r}"
            )

        # confidence_level
        cl = row.get("confidence_level", "").strip().upper()
        if cl not in VALID_CONFIDENCE:
            warnings.append(f"{loc}: unrecognised confidence_level={cl!r}")

        # component_tokens must not be empty
        if not row.get("component_tokens", "").strip():
            errors.append(f"{loc}: component_tokens is empty")

    # Summary stats as warnings (informational)
    warnings.append(
        f"[PC info] {len(bank_ids)} bank-extracted entries, {len(new_ids)} V12-new entries"
    )

    return errors, warnings


# ── Stoplist validator ───────────────────────────────────────────────────────

def validate_stoplist(strict: bool) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    rows, cols = read_csv(SL_PATH)

    if not rows:
        return [f"FATAL [SL]: file not found or empty: {SL_PATH}"], []

    errs = col_check(cols, SL_REQUIRED_COLS, "SL")
    if errs:
        return errs, []

    seen_terms: set[str] = set()

    for i, row in enumerate(rows, start=2):
        term = row.get("term", "").strip().lower()
        loc = f"SL row {i} ({term!r})"

        if not term:
            errors.append(f"SL row {i}: blank term")
        if term in seen_terms:
            errors.append(f"{loc}: duplicate term")
        seen_terms.add(term)

        # must_not_auto_promote: all stoplist entries must be true
        mnap = bool_field(row.get("must_not_auto_promote", ""))
        if mnap is None:
            errors.append(f"{loc}: must_not_auto_promote must be true/false")
        elif mnap is False:
            errors.append(
                f"{loc}: stoplist entries must have must_not_auto_promote=true"
            )

        # risk_level sanity
        rl = row.get("risk_level", "").strip().upper()
        if rl not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
            warnings.append(f"{loc}: unrecognised risk_level={rl!r}")

    return errors, warnings


# ── Reliability-layer metadata validator ────────────────────────────────────

def validate_reliability_layer() -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []

    if not RL_PATH.exists():
        return [f"FATAL [RL]: file not found: {RL_PATH}"], []

    try:
        layer = json.loads(RL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"FATAL [RL]: JSON parse error: {exc}"], []

    meta = layer.get("metadata", {})

    # Required metadata keys
    for key in ("version", "purpose", "guardrails", "section_row_counts", "csv_file_registry"):
        if key not in meta:
            errors.append(f"[RL metadata]: missing key '{key}'")

    # csv_file_registry must point to both CSVs
    registry = meta.get("csv_file_registry", {})
    for expected_key in ("arabizi_general_word_bank.csv", "arabizi_protected_combos.csv"):
        if expected_key not in registry:
            errors.append(f"[RL csv_file_registry]: missing entry for '{expected_key}'")
        else:
            entry = registry[expected_key]
            if "path" not in entry:
                errors.append(f"[RL csv_file_registry][{expected_key}]: missing 'path' key")
            if "row_count" not in entry:
                warnings.append(
                    f"[RL csv_file_registry][{expected_key}]: missing 'row_count'"
                )

    # Guardrails: phrase-lock guardrail must be present
    guardrails = meta.get("guardrails", [])
    if not any("protected_combos" in g for g in guardrails):
        warnings.append(
            "[RL guardrails]: phrase-lock guardrail not found "
            "(expected mention of 'protected_combos')"
        )

    # Version must be at least v1.1
    version = meta.get("version", "")
    if not version.startswith("v1.1") and not version.startswith("v1."):
        warnings.append(f"[RL metadata]: version={version!r} — expected v1.1+")

    # Required JSON sections
    required_sections = [
        "general_word_bank", "variant_lookup", "stoplist",
        "false_friends", "internet_notation_rules", "oov_seed_queue",
    ]
    for section in required_sections:
        if section not in layer:
            errors.append(f"[RL]: missing top-level section '{section}'")

    return errors, warnings


# ── Cross-file consistency checks ────────────────────────────────────────────

def validate_cross(strict: bool) -> tuple[list[str], list[str]]:
    """Check that row counts in RL metadata match actual CSV rows."""
    errors: list[str] = []
    warnings: list[str] = []

    if not RL_PATH.exists():
        return [], []

    try:
        layer = json.loads(RL_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], []

    meta = layer.get("metadata", {})
    registry = meta.get("csv_file_registry", {})

    checks = [
        ("arabizi_general_word_bank.csv", GWB_PATH),
        ("arabizi_protected_combos.csv", PC_PATH),
    ]
    for key, path in checks:
        if key not in registry:
            continue
        declared_count = registry[key].get("row_count")
        if declared_count is None:
            continue
        rows, _ = read_csv(path)
        actual = len(rows)
        if actual != int(declared_count):
            (errors if strict else warnings).append(
                f"[CROSS] {key}: registry says {declared_count} rows, file has {actual}"
            )

    return errors, warnings


# ── Entrypoint ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate V12 Arabizi support layer artefacts."
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Treat warnings as errors (non-zero exit if any warning)."
    )
    parser.add_argument(
        "--gwb-only", action="store_true", help="Only validate general_word_bank."
    )
    parser.add_argument(
        "--pc-only", action="store_true", help="Only validate protected_combos."
    )
    args = parser.parse_args()

    all_errors: list[str] = []
    all_warnings: list[str] = []
    sections: list[tuple[str, list[str], list[str]]] = []

    run_all = not args.gwb_only and not args.pc_only

    if run_all or args.gwb_only:
        e, w = validate_gwb(args.strict)
        sections.append(("General Word Bank", e, w))
        all_errors.extend(e); all_warnings.extend(w)

    if run_all or args.pc_only:
        e, w = validate_pc(args.strict)
        sections.append(("Protected Combos", e, w))
        all_errors.extend(e); all_warnings.extend(w)

    if run_all:
        e, w = validate_stoplist(args.strict)
        sections.append(("Stoplist", e, w))
        all_errors.extend(e); all_warnings.extend(w)

        e, w = validate_reliability_layer()
        sections.append(("Reliability Layer JSON", e, w))
        all_errors.extend(e); all_warnings.extend(w)

        e, w = validate_cross(args.strict)
        sections.append(("Cross-file consistency", e, w))
        all_errors.extend(e); all_warnings.extend(w)

    # -- Report ----------------------------------------------------------------
    import sys
    out = open(sys.stdout.fileno(), mode="w", encoding="utf-8", buffering=1, closefd=False)

    out.write("=" * 70 + "\n")
    out.write("  V12 ARABIZI SUPPORT LAYER GOVERNANCE REPORT\n")
    out.write("=" * 70 + "\n")

    for section_name, errs, warns in sections:
        real_warns = [w for w in warns if not w.startswith("[") or "info" not in w.lower()]
        info_warns = [w for w in warns if "[" in w and "info" in w.lower()]
        status = "PASS" if not errs and not real_warns else (
            "FAIL" if errs else "WARN"
        )
        out.write(f"\n-- {section_name} [{status}]\n")
        for msg in info_warns:
            out.write(f"   i  {msg}\n")
        for msg in real_warns:
            out.write(f"   W  {msg}\n")
        for msg in errs:
            out.write(f"   E  {msg}\n")
        if not errs and not real_warns and not info_warns:
            out.write("   (no issues)\n")

    out.write("\n" + "=" * 70 + "\n")
    non_info = len([w for w in all_warnings if "info" not in w.lower()])
    out.write(f"  SUMMARY  errors={len(all_errors)}  warnings={non_info}\n")
    out.write("=" * 70 + "\n")

    if all_errors or (args.strict and all_warnings):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
