#!/usr/bin/env python3
"""Evaluate FLOODING / drainage routing guardrails.

FLOODING covers local storm-drain blockage and rainwater-not-draining cases.
These resolve to the local drainage authority (the municipality). The router may
return the literal sentinel ``FLOODING``, ``MUN``, or a resolved municipality id
(numeric) depending on how much location context is present — all of these are
"municipal drainage", so ``expected_primary_entity == "FLOODING"`` accepts any of
them and rejects any cross-sector utility/national entity.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from src.route_complaint import route


ROOT = pathlib.Path(__file__).resolve().parents[1]
EVAL = ROOT / "data" / "eval" / "flooding_routing_eval_v1.jsonl"

_NON_MUNICIPAL = {
    "BMLWE", "NLWE", "SLWE", "BWE", "MEW", "MOE", "LRA",
    "EDL", "EDZ", "OGERO", "MPWT", "CDR", "TRA", "ISF", "CD",
}


def entity_matches(actual: str, expected: str) -> bool:
    if expected == "FLOODING":
        # Municipal drainage: sentinel, MUN, or any resolved municipality id.
        return actual not in _NON_MUNICIPAL and actual != "HITL"
    return actual == expected


def expected_codes_match(actual: list[str], expected: str) -> bool:
    codes = [item.strip() for item in expected.replace(",", ";").split(";") if item.strip()]
    if not codes:
        return True
    actual_set = set(actual)
    return all(code in actual_set for code in codes)


def main() -> int:
    cases = [json.loads(line) for line in EVAL.read_text(encoding="utf-8").splitlines() if line.strip()]
    failures: list[str] = []

    for case in cases:
        result = route(case["prompt"])
        checks = {
            "sector": result.sector == case["expected_sector"],
            "primary": entity_matches(result.primary_entity, case["expected_primary_entity"]),
            "hitl": result.hitl_required == case["expected_hitl"],
            "complaint_type": result.complaint_type_id == case["expected_complaint_type_id"],
            "hitl_reason_codes": expected_codes_match(
                result.hitl_reason_codes, case.get("expected_hitl_reason_codes", "")
            ),
        }
        if not all(checks.values()):
            failures.append(
                f"{case['id']}: checks={checks} got="
                f"sector={result.sector} primary={result.primary_entity} "
                f"hitl={result.hitl_required} hitl_codes={result.hitl_reason_codes} "
                f"type={result.complaint_type_id}"
            )

    print(f"Flooding/drainage routing eval: {len(cases) - len(failures)}/{len(cases)} passed")
    if failures:
        print("Failures:")
        for failure in failures:
            print(f"  {failure}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
