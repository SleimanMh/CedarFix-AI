#!/usr/bin/env python3
"""Audit the water-establishment routing pack end to end."""

from __future__ import annotations

import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.route_complaint import route


KB = ROOT / "data" / "knowledge_base"
WATER = KB / "water_establishments"
EVAL = ROOT / "data" / "eval" / "water_establishments_routing_eval_v1.jsonl"
REPORT = WATER / "water_production_audit_report.md"

ENTITIES = ["BMLWE", "NLWE", "SLWE", "BWE", "LRA", "MEW"]
PRODUCTION_FILES = [
    "water_entity_resolution.csv",
    "coverage_summary.csv",
    "contact_points.csv",
    "branch_service_areas.csv",
    "complaint_channels.csv",
    "required_fields.csv",
    "water_service_catalog.csv",
    "not_responsible_for.csv",
    "boundary_conditions.csv",
    "irrigation_boundaries.csv",
    "sla_policy.csv",
    "trusted_context.csv",
    "irl_complaint_patterns.csv",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def source_list(value: str) -> list[str]:
    return [item.strip() for item in value.replace(",", ";").split(";") if item.strip()]


def entity_matches(actual: str, expected: str) -> bool:
    if expected == "MUN":
        return actual not in {
            "BMLWE",
            "NLWE",
            "SLWE",
            "BWE",
            "MEW",
            "MOE",
            "LRA",
            "HITL",
            "CD",
            "EDL",
            "EDZ",
            "OGERO",
            "MPWT",
            "PRIVATE_PROPERTY_OR_BUILDING_MANAGEMENT",
            "PRIVATE_WATER_VENDOR_OR_CONSUMER_DISPUTE",
        }
    return actual == expected


def expected_codes_match(actual: list[str], expected: str) -> bool:
    codes = source_list(expected)
    if not codes:
        return True
    actual_set = set(actual)
    return all(code in actual_set for code in codes)


def run_eval() -> tuple[int, int, list[str]]:
    cases = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []
    for case in cases:
        result = route(case["prompt"])
        checks = {
            "sector": result.sector == case["expected_sector"],
            "primary": entity_matches(result.primary_entity, case["expected_primary_entity"]),
            "hitl": result.hitl_required == case["expected_hitl"],
            "complaint_type": result.complaint_type_id == case["expected_complaint_type_id"],
            "hitl_reason_codes": (
                True if not case["expected_hitl"]
                else expected_codes_match(result.hitl_reason_codes, case.get("expected_hitl_reason_codes", ""))
            ),
        }
        if case.get("expected_secondary_entity"):
            checks["secondary"] = result.secondary_entity == case["expected_secondary_entity"]
        if not all(checks.values()):
            failures.append(
                f"{case['id']}: {checks} -> primary={result.primary_entity}, "
                f"secondary={result.secondary_entity}, hitl_codes={result.hitl_reason_codes}"
            )
    return len(cases) - len(failures), len(cases), failures


def provenance_issues() -> list[str]:
    issues: list[str] = []
    for name in PRODUCTION_FILES:
        path = WATER / name
        rows = read_csv(path)
        if not rows:
            issues.append(f"{name}: missing or empty")
            continue
        fieldnames = rows[0].keys()
        for col in ("source_ids", "confidence"):
            if col not in fieldnames:
                issues.append(f"{name}: missing {col}")
                continue
            blanks = [index for index, row in enumerate(rows, start=2) if not row.get(col, "").strip()]
            if blanks:
                issues.append(f"{name}: blank {col} at lines {blanks[:8]}")
        if name == "water_entity_resolution.csv":
            for col in ("retrieved_date", "verification_status"):
                blanks = [index for index, row in enumerate(rows, start=2) if not row.get(col, "").strip()]
                if blanks:
                    issues.append(f"{name}: blank {col} at lines {blanks[:8]}")
    return issues


def main() -> int:
    resolver = read_csv(WATER / "water_entity_resolution.csv")
    contacts = read_csv(WATER / "contact_points.csv")
    channels = read_csv(WATER / "complaint_channels.csv")
    not_resp = read_csv(WATER / "not_responsible_for.csv")
    sla = read_csv(WATER / "sla_policy.csv")
    required = read_csv(WATER / "required_fields.csv")

    resolver_counts = Counter(row["water_entity_id"] for row in resolver)
    channel_modes: dict[str, set[str]] = defaultdict(set)
    for row in channels:
        channel_modes[row["entity_id"]].add(row["channel_type"])
    contact_counts = Counter(row["entity_id"] for row in contacts)
    not_resp_counts = Counter(row["entity_id"] for row in not_resp)
    required_counts = Counter(row["entity_id"] for row in required)
    sla_counts = Counter(row["entity_id"] for row in sla)
    published_sla_counts = Counter(
        row["entity_id"] for row in sla
        if row.get("official_sla", "") not in {"", "not_published"}
        or row.get("contact_response_time", "") not in {"", "not_published"}
    )
    eval_passed, eval_total, eval_failures = run_eval()
    provenance = provenance_issues()

    lines = [
        "# Water Production Audit Report",
        "",
        f"Generated: {date.today().isoformat()}",
        "",
        "## Routing Resolver Coverage",
        "",
        "| Entity | Municipalities | Contacts | Channel modes | Required-field rows | Not-responsible rows | SLA rows | Published response wording |",
        "|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for entity_id in ENTITIES:
        modes = ";".join(sorted(channel_modes.get(entity_id, []))) or "none"
        lines.append(
            f"| {entity_id} | {resolver_counts[entity_id]} | {contact_counts[entity_id]} | {modes} | "
            f"{required_counts[entity_id]} | {not_resp_counts[entity_id]} | {sla_counts[entity_id]} | {published_sla_counts[entity_id]} |"
        )

    lines.extend(
        [
            "",
            "## Eval Gate",
            "",
            f"- Water routing eval: {eval_passed}/{eval_total} passed.",
            f"- Failures: {len(eval_failures)}.",
        ]
    )
    if eval_failures:
        lines.append("")
        lines.append("### Eval Failures")
        lines.extend(f"- {failure}" for failure in eval_failures[:20])

    lines.extend(
        [
            "",
            "## Provenance Gate",
            "",
            f"- Production files checked: {len(PRODUCTION_FILES)}.",
            f"- Issues: {len(provenance)}.",
        ]
    )
    if provenance:
        lines.append("")
        lines.append("### Provenance Issues")
        lines.extend(f"- {issue}" for issue in provenance)

    lines.extend(
        [
            "",
            "## Remaining Manual Verification",
            "",
            "- BMLWE ticket/reference details remain browser/app-verification only.",
            "- NLWE public complaint reference-number policy is not published.",
            "- SLWE HQ address and individual transaction document pages still need manual extraction.",
            "- BWE official pages are browser-verifiable, but automated crawler TLS failures remain in page inventory.",
            "- LRA project-specific irrigation overlap needs map extraction before automatic LRA routing beyond named Litani/Qasimiya/Ras Al Ain cases.",
            "- Generic repair/restoration SLAs remain not published; do not promise restoration times.",
        ]
    )

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"Water production audit: {eval_passed}/{eval_total} evals passed")
    print(f"Provenance issues: {len(provenance)}")
    print(f"Report written: {REPORT.relative_to(ROOT)}")
    if eval_failures or provenance:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
