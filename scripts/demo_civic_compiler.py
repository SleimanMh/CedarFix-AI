"""Run the CedarFix Civic Intelligence Compiler demo.

This is the two-minute professor demo in script form. It runs a representative
Arabizi report through the dependency-light pipeline and prints the compiled
incident program: beliefs, proof obligations, active questions, counterfactuals,
and the autonomy decision.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.shared.civic_compiler import compile_demo_case  # noqa: E402

DEFAULT_TEXT = "fi may m2ata3a w fi soura masoura 3am tsarrib 7ad l tari2 bi zahle"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CedarFix proof-carrying civic AI demo")
    parser.add_argument("--complaint-id", default="CF-KILLER-DEMO")
    parser.add_argument("--text", default=DEFAULT_TEXT)
    parser.add_argument("--gps-lat", type=float, default=33.8466)
    parser.add_argument("--gps-lon", type=float, default=35.9020)
    parser.add_argument(
        "--image-sector",
        default="WATER",
        help="Synthetic IEP-6 sector for the demo photo; use ROADS to force conflict.",
    )
    parser.add_argument("--image-confidence", type=float, default=0.91)
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print the full incident program JSON instead of the short dossier.",
    )
    return parser


def main() -> None:
    args = _build_parser().parse_args()
    program = compile_demo_case(
        complaint_id=args.complaint_id,
        text=args.text,
        gps_lat=args.gps_lat,
        gps_lon=args.gps_lon,
        image_sector=args.image_sector,
        image_confidence=args.image_confidence,
    )

    if args.json:
        print(json.dumps(program.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return

    print("\n=== CedarFix Civic Intelligence Compiler ===")
    print(program.thesis)
    print("\n--- Incident Program DSL ---")
    print(program.dsl)
    print("\n--- Scoreboard ---")
    for key, value in program.scoreboard.items():
        print(f"{key}: {value}")
    print("\n--- Proof Obligations ---")
    for item in program.proof_obligations:
        print(f"{item.id}: {item.status.value} | {item.reason}")
    print("\n--- Active Sensing ---")
    if program.active_sensing:
        for item in program.active_sensing:
            print(f"{item.id}: {item.question} ({item.trigger})")
    else:
        print("none")
    print("\n--- Counterfactual Routes ---")
    if program.counterfactual_routes:
        for item in program.counterfactual_routes:
            print(f"{item.id}: {item.condition} -> {item.routing_entity}")
    else:
        print("none")
    print("\n--- Autonomy Decision ---")
    print(f"{program.autonomy_decision.level.value} risk={program.autonomy_decision.risk_score:.2f}")
    print("allowed:", ", ".join(program.autonomy_decision.allowed_actions))
    print("forbidden:", ", ".join(program.autonomy_decision.forbidden_actions))


if __name__ == "__main__":
    main()
