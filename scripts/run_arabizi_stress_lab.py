#!/usr/bin/env python3
"""Demo-grade Arabizi Stress Lab for CedarFix.

The stress lab is intentionally not a final model evaluation. It is a
repeatable, adversarial demo/evidence artifact that asks one operational
question:

Can IEP-1 keep the same municipal decision under messy Lebanese Arabizi while
surfacing uncertainty through drift, OOV, and HITL signals?

It uses the same shared probe and issue classifier as the EEP/IEP-1 contract
tests, then writes a JSON artifact for MLflow/demo lineage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.iep1.extractor import classify_issue_type_from_signal  # noqa: E402
from src.shared.arabizi_features import analyze_language_signal, load_vocabulary_index  # noqa: E402
from src.shared.schemas import ROUTE_CONFIDENCE_THRESHOLD  # noqa: E402

OUTPUT_PATH = ROOT / "data" / "eval" / "arabizi_stress_lab_v1.json"
VOCAB_PATH = ROOT / "data" / "knowledge_base" / "arabizi_vocabulary.json"
SCENARIO_SET_VERSION = "1.1"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@dataclass(frozen=True)
class StressVariant:
    variant_id: str
    raw_text: str
    language_hint: str
    perturbation: str
    expected_behavior: str
    acceptable_issue_types: tuple[str, ...] = ()


@dataclass(frozen=True)
class StressScenario:
    scenario_id: str
    expected_sector: str
    expected_issue_type: str
    expected_route_entity: str
    expected_severity: str
    variants: tuple[StressVariant, ...]


SCENARIOS: tuple[StressScenario, ...] = (
    StressScenario(
        scenario_id="STRESS-ROADS-POTHOLE",
        expected_sector="ROADS",
        expected_issue_type="POTHOLE",
        expected_route_entity="MUN",
        expected_severity="HIGH",
        variants=(
            StressVariant(
                "roads_clean_arabizi",
                "fi jora kbire 3al tari2 w l wad3 m5atra ktir",
                "arabizi",
                "clean reviewed-style Arabizi with unknown risk modifier",
                "keep ROADS/POTHOLE and force HITL from high-risk OOV",
            ),
            StressVariant(
                "roads_digit_omission_repeat",
                "fi hofraaaaaa 3al share3 l 7amra jemb l virgin",
                "arabizi",
                "omitted 7 plus repeated letters",
                "recover pothole signal from hofra/jora family and mark orthographic noise",
            ),
            StressVariant(
                "roads_no_space",
                "fishare3l7amra fi jora kbire",
                "arabizi",
                "fused no-space mobile typing",
                "do not crash; preserve pothole signal with lower coverage",
            ),
            StressVariant(
                "roads_panic_digits",
                "5tr444444 fi jora 3al tari2 7add l madrase",
                "arabizi",
                "panic shorthand with repeated digits",
                "force HITL while preserving pothole issue",
            ),
            StressVariant(
                "roads_fr_mix",
                "route fiya jora dangereuse 3al tari2 bi hamra",
                "mixed",
                "French/Arabizi code-switch",
                "keep pothole route and expose mixed-script/code-mix evidence",
            ),
        ),
    ),
    StressScenario(
        scenario_id="STRESS-ELECTRICITY-TRANSFORMER",
        expected_sector="ELECTRICITY",
        expected_issue_type="TRANSFORMER_FAULT",
        expected_route_entity="EDL",
        expected_severity="CRITICAL",
        variants=(
            StressVariant(
                "electricity_transformer_clean",
                "transformateur m7arrak bi borj 7ammoud w fi ri7et 7ar2",
                "mixed",
                "French technical loanword plus Arabizi safety context",
                "route to transformer fault and force safety HITL",
            ),
            StressVariant(
                "electricity_transformer_panic",
                "5tr444444 transformateur m7arrak bi borj 7ammoud",
                "mixed",
                "panic shorthand before French loanword",
                "keep transformer fault and force HITL",
            ),
            StressVariant(
                "electricity_transformer_spaced",
                "fi transformateur 3am yitla3 ri7et 7ar2 7add l bine",
                "mixed",
                "different phrase order and location terms",
                "keep transformer fault under phrase-order variation",
            ),
            StressVariant(
                "electricity_transformer_mixed_wire",
                "transformateur mcharrak w silk kahraba mekshouf 3al ard",
                "mixed",
                "transformer/wire ambiguity",
                "prefer transformer fault from explicit transformateur and preserve safety evidence",
                ("TRANSFORMER_FAULT", "EXPOSED_WIRE"),
            ),
        ),
    ),
    StressScenario(
        scenario_id="STRESS-WATER-SEWAGE",
        expected_sector="WATER",
        expected_issue_type="SEWAGE_OVERFLOW",
        expected_route_entity="BMLWE",
        expected_severity="CRITICAL",
        variants=(
            StressVariant(
                "water_sewage_clean",
                "may ws5a w ri7et sarif 3al tari2 bi bliss",
                "arabizi",
                "short dirty-water/sewage ambiguity",
                "prefer WATER/SEWAGE_OVERFLOW and force semantic-ambiguity HITL",
            ),
            StressVariant(
                "water_sewage_overflow",
                "sarif sa77i 3am yetfa2ar bi share3 bliss rass beirut",
                "arabizi",
                "overflow verb plus formal-ish sewer phrase",
                "keep sewage overflow under richer phrasing",
            ),
            StressVariant(
                "water_sewage_smell",
                "may sawda 3al rasif w ri7a ma btit7ammal",
                "arabizi",
                "black water and smell without explicit sarif",
                "keep water sector; may require HITL if exact issue is uncertain",
                ("SEWAGE_OVERFLOW", "DIRTY_WATER"),
            ),
        ),
    ),
    StressScenario(
        scenario_id="STRESS-SAFETY-FIRE",
        expected_sector="SAFETY",
        expected_issue_type="FIRE",
        expected_route_entity="CD",
        expected_severity="CRITICAL",
        variants=(
            StressVariant(
                "safety_fire_clean",
                "fi 7ariki bi l bine w nnar 3am tit3ala bi share3 hamra",
                "arabizi",
                "clean Arabizi fire report with nnar high-risk token",
                "force SAFETY/FIRE and force HITL from high-risk nnar+7ariki tokens",
            ),
            StressVariant(
                "safety_fire_panic",
                "5tr 5tr 7ariki w nnar bi bine 3al ma3rad",
                "arabizi",
                "panic shorthand with repeated 5tr prefix before fire tokens",
                "keep SAFETY/FIRE and force HITL from 5tr panic marker",
            ),
            StressVariant(
                "safety_gas_mix",
                "ghaz 3am yinba3et men l share3 w 2awiye ktir bi raouche",
                "arabizi",
                "gas smell with 2awiye (toxic fumes) — adjacent SAFETY issue type",
                "keep SAFETY sector; GAS_LEAK is acceptable adjacent to FIRE route",
                ("FIRE", "GAS_LEAK"),
            ),
            StressVariant(
                "safety_fire_fr_mix",
                "situation critique, 7ariki bi l bine 3al hamra, danger imminent",
                "mixed",
                "French danger framing around Arabizi fire token",
                "keep SAFETY/FIRE under French code-switch; expose code-mix evidence",
            ),
        ),
    ),
    StressScenario(
        scenario_id="STRESS-WASTE-COLLECTION",
        expected_sector="WASTE",
        expected_issue_type="GARBAGE_NOT_COLLECTED",
        expected_route_entity="MUN",
        expected_severity="MEDIUM",
        variants=(
            StressVariant(
                "waste_clean",
                "jmaou zibele 3amme titrakam w ma 7ada byiji bi share3 dahye",
                "arabizi",
                "clean Arabizi garbage accumulation with jmaou (accumulated) token",
                "route WASTE/GARBAGE_NOT_COLLECTED to MUN",
            ),
            StressVariant(
                "waste_overflowing",
                "kuumet zibele 3al rasif w ri7a khafer ktir bi share3 verdun",
                "arabizi",
                "overflowing bin with ri7a khafer (foul smell) — adjacent WASTE issue",
                "keep WASTE sector; OVERFLOWING_BIN acceptable adjacent to GARBAGE_NOT_COLLECTED",
                ("GARBAGE_NOT_COLLECTED", "OVERFLOWING_BIN"),
            ),
            StressVariant(
                "waste_noise_letters",
                "kuumettttt zibele w ri7a la tit7ammal bi share3 bliss",
                "arabizi",
                "orthographic noise: repeated letters in kuumet variant",
                "keep WASTE sector despite orthographic drift; UNCLASSIFIED issue acceptable",
                ("GARBAGE_NOT_COLLECTED", "OVERFLOWING_BIN", "UNCLASSIFIED"),
            ),
            StressVariant(
                "waste_fr_mix",
                "ordures non ramassees depuis 3 jours, kuumet zibele w ri7a bi borj hammoud",
                "mixed",
                "French ordures + Arabizi kuumet code-switch with temporal context",
                "keep WASTE under French code-switch; expose mixed-script evidence",
                ("GARBAGE_NOT_COLLECTED", "OVERFLOWING_BIN"),
            ),
        ),
    ),
    StressScenario(
        scenario_id="STRESS-FLOODING-DRAIN",
        expected_sector="FLOODING",
        expected_issue_type="BLOCKED_DRAIN",
        expected_route_entity="MUN",
        expected_severity="HIGH",
        variants=(
            StressVariant(
                "flooding_drain_clean",
                "balo3a msdoude w miye 3am tit3abba bi share3 makhoul",
                "arabizi",
                "clean Arabizi blocked-drain report with balo3a+msdoude tokens",
                "route FLOODING/BLOCKED_DRAIN to MUN",
            ),
            StressVariant(
                "flooding_drain_panic",
                "5tr444 balo3a msdoude w l share3 killo miye bi dbaye",
                "arabizi",
                "panic prefix with repeated digits before blocked-drain tokens",
                "keep FLOODING/BLOCKED_DRAIN and force HITL from 5tr panic marker",
            ),
            StressVariant(
                "flooding_drain_repeated",
                "sayel w miye 3am tit3abba bi share3 makhoul, balo3a msdoude",
                "arabizi",
                "reordered tokens — sayel then balo3a",
                "keep FLOODING/BLOCKED_DRAIN under phrase-order variation",
            ),
            StressVariant(
                "flooding_road_adjacent",
                "tari2 ghatat w sayel kbir bi jemmayzeh w l miye 3am tirfa3",
                "arabizi",
                "ghatat (flooding verb) + sayel — adjacent ROAD_FLOODED issue type",
                "keep FLOODING sector; ROAD_FLOODED acceptable adjacent to BLOCKED_DRAIN",
                ("BLOCKED_DRAIN", "ROAD_FLOODED"),
            ),
        ),
    ),
)


def analyze_variant(
    scenario: StressScenario,
    variant: StressVariant,
    *,
    vocab,
) -> dict[str, Any]:
    signal = analyze_language_signal(
        variant.raw_text,
        language_hint=variant.language_hint,
        report_id=variant.variant_id,
    )
    sector, issue_type, issue_confidence = classify_issue_type_from_signal(signal, vocab)
    stable_sector = sector == scenario.expected_sector
    stable_issue = issue_type == scenario.expected_issue_type
    acceptable_issue_types = variant.acceptable_issue_types or (scenario.expected_issue_type,)
    acceptable_decision = stable_sector and issue_type in acceptable_issue_types
    force_hitl = signal.force_hitl(route_confidence=issue_confidence)

    return {
        "scenario_id": scenario.scenario_id,
        "variant_id": variant.variant_id,
        "raw_text": variant.raw_text,
        "language_hint": variant.language_hint,
        "perturbation": variant.perturbation,
        "expected_behavior": variant.expected_behavior,
        "expected_sector": scenario.expected_sector,
        "expected_issue_type": scenario.expected_issue_type,
        "acceptable_issue_types": list(acceptable_issue_types),
        "predicted_sector": sector,
        "predicted_issue_type": issue_type,
        "issue_confidence": issue_confidence,
        "stable_sector": stable_sector,
        "stable_issue": stable_issue,
        "acceptable_decision": acceptable_decision,
        "force_hitl": force_hitl,
        "drift_score": signal.drift_score,
        "normalization_coverage": signal.normalization_coverage,
        "normalization_confidence": signal.normalization_confidence,
        "code_mix_ratio": signal.code_mix_ratio,
        "arabizi_marker_density": signal.arabizi_marker_density,
        "oov_token_count": signal.oov_token_count,
        "oov_high_risk_count": signal.oov_high_risk_count,
        "oov_tokens": [token.token for token in signal.oov_tokens],
        "known_terms": signal.known_terms,
        "orthographic_noise_count": int(signal.explanation_features.get("orthographic_noise_count", 0)),
        "semantic_ambiguity": bool(signal.explanation_features.get("semantic_ambiguity", False)),
    }


def run_stress_lab() -> dict[str, Any]:
    vocab = load_vocabulary_index()
    rows: list[dict[str, Any]] = []
    for scenario in SCENARIOS:
        for variant in scenario.variants:
            rows.append(analyze_variant(scenario, variant, vocab=vocab))

    total = max(1, len(rows))
    drift_distribution = {f"score_{idx}": 0 for idx in range(4)}
    for row in rows:
        drift_distribution[f"score_{row['drift_score']}"] += 1

    scenario_summary: dict[str, dict[str, Any]] = {}
    for scenario in SCENARIOS:
        scenario_rows = [row for row in rows if row["scenario_id"] == scenario.scenario_id]
        n = max(1, len(scenario_rows))
        scenario_summary[scenario.scenario_id] = {
            "variant_count": len(scenario_rows),
            "stable_sector_rate": round(sum(row["stable_sector"] for row in scenario_rows) / n, 4),
            "stable_issue_rate": round(sum(row["stable_issue"] for row in scenario_rows) / n, 4),
            "acceptable_decision_rate": round(sum(row["acceptable_decision"] for row in scenario_rows) / n, 4),
            "hitl_rate": round(sum(row["force_hitl"] for row in scenario_rows) / n, 4),
            "mean_coverage": round(sum(row["normalization_coverage"] for row in scenario_rows) / n, 4),
            "max_drift_score": max(row["drift_score"] for row in scenario_rows),
            "unique_oov_tokens": sorted({token for row in scenario_rows for token in row["oov_tokens"]}),
        }

    stable_issue_count = sum(row["stable_issue"] for row in rows)
    stable_sector_count = sum(row["stable_sector"] for row in rows)
    acceptable_decision_count = sum(row["acceptable_decision"] for row in rows)
    hitl_count = sum(row["force_hitl"] for row in rows)
    oov_union = sorted({token for row in rows for token in row["oov_tokens"]})

    # Sector coverage matrix: which of the canonical 6 sectors are exercised
    _all_sectors = ("ROADS", "WATER", "ELECTRICITY", "WASTE", "FLOODING", "SAFETY")
    _exercised_sectors = sorted({s.expected_sector for s in SCENARIOS})
    sector_coverage = {
        "exercised_sectors": _exercised_sectors,
        "all_sectors": list(_all_sectors),
        "missing_sectors": [s for s in _all_sectors if s not in _exercised_sectors],
        "coverage_rate": round(len(_exercised_sectors) / len(_all_sectors), 4),
    }

    instability_rows = [
        {
            "variant_id": row["variant_id"],
            "expected": f"{row['expected_sector']}/{row['expected_issue_type']}",
            "predicted": f"{row['predicted_sector']}/{row['predicted_issue_type']}",
            "drift_score": row["drift_score"],
            "oov_tokens": row["oov_tokens"],
        }
        for row in rows
        if not row["stable_issue"]
    ]
    unacceptable_rows = [
        {
            "variant_id": row["variant_id"],
            "acceptable_issue_types": row["acceptable_issue_types"],
            "predicted": f"{row['predicted_sector']}/{row['predicted_issue_type']}",
            "drift_score": row["drift_score"],
            "oov_tokens": row["oov_tokens"],
        }
        for row in rows
        if not row["acceptable_decision"]
    ]

    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "artifact": str(OUTPUT_PATH.relative_to(ROOT)),
            "script": str((ROOT / "scripts" / "run_arabizi_stress_lab.py").relative_to(ROOT)),
            "scenario_set_version": SCENARIO_SET_VERSION,
            "vocab_version": vocab.version,
            "vocab_sha256": sha256_file(VOCAB_PATH),
            "route_confidence_threshold": ROUTE_CONFIDENCE_THRESHOLD,
            "scope": "demo stress/regression evidence, not final held-out accuracy",
            "external_data_used": False,
            "scenario_count": len(SCENARIOS),
            "variant_count": len(rows),
        },
        "acceptance_gates": {
            "min_stable_sector_rate": 0.90,
            "min_acceptable_decision_rate": 0.90,
            "min_strict_issue_rate_observed": 0.65,
            "requires_hitl_variant_count_at_least": 10,
            "requires_oov_or_noise_variant_count_at_least": 10,
            "requires_sector_coverage_rate": 1.0,
        },
        "summary": {
            "stable_sector_rate": round(stable_sector_count / total, 4),
            "stable_issue_rate": round(stable_issue_count / total, 4),
            "acceptable_decision_rate": round(acceptable_decision_count / total, 4),
            "hitl_rate": round(hitl_count / total, 4),
            "mean_coverage": round(sum(row["normalization_coverage"] for row in rows) / total, 4),
            "mean_oov_count": round(sum(row["oov_token_count"] for row in rows) / total, 2),
            "drift_distribution": drift_distribution,
            "orthographic_noise_variant_count": sum(1 for row in rows if row["orthographic_noise_count"] > 0),
            "semantic_ambiguity_variant_count": sum(1 for row in rows if row["semantic_ambiguity"]),
            "oov_or_noise_variant_count": sum(
                1 for row in rows if row["oov_token_count"] > 0 or row["orthographic_noise_count"] > 0
            ),
            "unique_oov_tokens": oov_union,
            "instability_count": len(instability_rows),
            "unacceptable_count": len(unacceptable_rows),
        },
        "sector_coverage": sector_coverage,
        "scenario_summary": scenario_summary,
        "instability_rows": instability_rows,
        "unacceptable_rows": unacceptable_rows,
        "variants": rows,
    }


def print_report(result: dict[str, Any]) -> None:
    meta = result["meta"]
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("  CedarFix Arabizi Stress Lab")
    print(f"  Vocab version : {meta['vocab_version']}")
    print(f"  Scope         : {meta['scope']}")
    print(f"  Variants      : {meta['variant_count']} across {meta['scenario_count']} scenarios")
    print("=" * 72)
    cov = result["sector_coverage"]
    print(f"Sector coverage    : {cov['coverage_rate']:.0%} ({len(cov['exercised_sectors'])}/{len(cov['all_sectors'])} sectors: {', '.join(cov['exercised_sectors'])})")
    if cov["missing_sectors"]:
        print(f"  ⚠  Missing sectors: {', '.join(cov['missing_sectors'])}")
    print(f"Stable sector rate : {summary['stable_sector_rate']:.1%}")
    print(f"Strict issue rate  : {summary['stable_issue_rate']:.1%}")
    print(f"Acceptable decision: {summary['acceptable_decision_rate']:.1%}")
    print(f"HITL trigger rate  : {summary['hitl_rate']:.1%}")
    print(f"Mean coverage      : {summary['mean_coverage']:.1%}")
    print(f"Mean OOV / variant : {summary['mean_oov_count']:.2f}")
    print(f"OOV/noise variants : {summary['oov_or_noise_variant_count']}")
    print(f"Unique OOV tokens  : {', '.join(summary['unique_oov_tokens']) or 'none'}")
    print("\nPer-scenario:")
    for scenario_id, item in result["scenario_summary"].items():
        print(
            f"  {scenario_id:<32} "
            f"issue={item['stable_issue_rate']:.0%} "
            f"ok={item['acceptable_decision_rate']:.0%} "
            f"hitl={item['hitl_rate']:.0%} "
            f"cov={item['mean_coverage']:.0%} "
            f"max_drift={item['max_drift_score']}"
        )
    if result["instability_rows"]:
        print("\nInstability rows:")
        for row in result["instability_rows"]:
            print(
                f"  {row['variant_id']}: expected {row['expected']} "
                f"predicted {row['predicted']} drift={row['drift_score']}"
            )
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the CedarFix Arabizi Stress Lab.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write the JSON artifact.")
    args = parser.parse_args(argv)

    result = run_stress_lab()
    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
