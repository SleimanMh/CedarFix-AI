#!/usr/bin/env python3
"""Project-wide next-phase gates for CedarFix.

This is the same discipline as the Arabizi gates, but for the whole project:
IEP-2 dedup, IEP-3 routing/calibration, IEP-4 explanation/HITL, MLOps,
observability, cloud, QA, and demo readiness.

Default mode is advisory and exits 0. Use --strict only when preparing a final
release where all gates are expected to pass.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "eval" / "cedarfix_next_phase_gates_v1.json"


def exists(relative: str) -> bool:
    return (ROOT / relative).exists()


def read_text(relative: str) -> str:
    path = ROOT / relative
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def count_tests() -> int:
    test_dir = ROOT / "scripts" / "tests"
    total = 0
    for path in test_dir.glob("test_*.py"):
        total += path.read_text(encoding="utf-8", errors="ignore").count("def test_")
    return total


def compose_has(service_name: str) -> bool:
    text = read_text("docker-compose.yml")
    return f"\n  {service_name}:" in text


def gate(gate_id: str, name: str, target: str, actual: Any, passed: bool, why: str) -> dict[str, Any]:
    return {
        "gate_id": gate_id,
        "name": name,
        "target": target,
        "actual": actual,
        "pass": passed,
        "why": why,
    }


def audit() -> dict[str, Any]:
    test_count = count_tests()
    gates = [
        gate(
            "CFX-G01",
            "EEP + IEP-1 foundation",
            "EEP and IEP-1 source, Dockerfiles, compose services, and contract tests exist",
            {
                "eep_main": exists("src/eep/main.py"),
                "iep1_main": exists("src/iep1/main.py"),
                "eep_dockerfile": exists("src/eep/Dockerfile"),
                "iep1_dockerfile": exists("src/iep1/Dockerfile"),
                "compose_eep": compose_has("eep"),
                "compose_iep1": compose_has("iep1"),
                "contract_tests": exists("scripts/tests/test_eep_iep1_contracts.py"),
            },
            all(
                [
                    exists("src/eep/main.py"),
                    exists("src/iep1/main.py"),
                    exists("src/eep/Dockerfile"),
                    exists("src/iep1/Dockerfile"),
                    compose_has("eep"),
                    compose_has("iep1"),
                    exists("scripts/tests/test_eep_iep1_contracts.py"),
                ]
            ),
            "This is the current working spine: validated ingest plus language signal extraction.",
        ),
        gate(
            "CFX-G02",
            "IEP-2 duplicate/cluster service",
            "src/iep2 service, Dockerfile, compose service, and pair-evaluation artifact exist",
            {
                "iep2_main": exists("src/iep2/main.py"),
                "iep2_dockerfile": exists("src/iep2/Dockerfile"),
                "compose_iep2": compose_has("iep2"),
                "pair_eval_artifact": exists("data/eval/iep2_pair_eval_v1.json"),
            },
            all(
                [
                    exists("src/iep2/main.py"),
                    exists("src/iep2/Dockerfile"),
                    compose_has("iep2"),
                    exists("data/eval/iep2_pair_eval_v1.json"),
                ]
            ),
            "IEP-2 is the highest-ROI next build because it unlocks real incident fusion and T3.",
        ),
        gate(
            "CFX-G03",
            "IEP-3 calibrated routing and priority",
            "src/iep3 service, calibration artifact, threshold sweep, and route test suite exist",
            {
                "iep3_main": exists("src/iep3/main.py"),
                "iep3_dockerfile": exists("src/iep3/Dockerfile"),
                "compose_iep3": compose_has("iep3"),
                "calibration_artifact": exists("data/eval/iep3_calibration_v1.json"),
                "route_tests": exists("scripts/tests/test_iep3_routing.py"),
            },
            all(
                [
                    exists("src/iep3/main.py"),
                    exists("src/iep3/Dockerfile"),
                    compose_has("iep3"),
                    exists("data/eval/iep3_calibration_v1.json"),
                    exists("scripts/tests/test_iep3_routing.py"),
                ]
            ),
            "Calibration is what separates a serious triage system from a rules dashboard.",
        ),
        gate(
            "CFX-G04",
            "IEP-4 explanation and HITL service",
            "Prompts, explanation service, HITL decision contract, and prompt tests exist",
            {
                "prompts": all(
                    [
                        exists("prompts/iep4_citizen_v1.0.txt"),
                        exists("prompts/iep4_admin_v1.0.txt"),
                        exists("prompts/iep4_audit_v1.0.txt"),
                    ]
                ),
                "iep4_main": exists("src/iep4/main.py"),
                "compose_iep4": compose_has("iep4"),
                "prompt_tests": exists("scripts/tests/test_iep4_explanations.py"),
            },
            all(
                [
                    exists("prompts/iep4_citizen_v1.0.txt"),
                    exists("prompts/iep4_admin_v1.0.txt"),
                    exists("prompts/iep4_audit_v1.0.txt"),
                    exists("src/iep4/main.py"),
                    compose_has("iep4"),
                    exists("scripts/tests/test_iep4_explanations.py"),
                ]
            ),
            "Prompts are present, but the service and contract tests must make IEP-4 real.",
        ),
        gate(
            "CFX-G05",
            "MLOps lifecycle and experiment evidence",
            "MLflow service, training/eval scripts, model registry artifact, and promotion thresholds exist",
            {
                "compose_mlflow": compose_has("mlflow"),
                "training_scripts": exists("scripts/train_iep2_dedup.py") or exists("scripts/train_iep3_router.py"),
                "mlflow_artifact": exists("data/eval/mlflow_run_manifest_v1.json"),
                "promotion_doc": exists("docs/MLOPS_PROMOTION_POLICY.md"),
            },
            all(
                [
                    compose_has("mlflow"),
                    exists("data/eval/mlflow_run_manifest_v1.json"),
                    exists("docs/MLOPS_PROMOTION_POLICY.md"),
                ]
            ),
            "Rubric M1/M2 require lifecycle evidence, not just model code.",
        ),
        gate(
            "CFX-G06",
            "Observability",
            "Prometheus/Grafana services and low-cardinality ML metric contract exist",
            {
                "compose_prometheus": compose_has("prometheus"),
                "compose_grafana": compose_has("grafana"),
                "monitoring_doc": exists("docs/MONITORING_SIGNALS.md"),
                "metrics_tests": exists("scripts/tests/test_monitoring_metrics.py"),
            },
            all(
                [
                    compose_has("prometheus"),
                    compose_has("grafana"),
                    exists("docs/MONITORING_SIGNALS.md"),
                    exists("scripts/tests/test_monitoring_metrics.py"),
                ]
            ),
            "Monitoring needs ML-specific signals: drift, HITL rate, confidence, false auto-route risk.",
        ),
        gate(
            "CFX-G07",
            "Public cloud EEP readiness",
            "Azure/app deployment config, cloud runbook, and public healthcheck evidence exist",
            {
                "azure_yaml": exists("azure.yaml"),
                "infra": exists("infra") or exists(".azure"),
                "cloud_doc": exists("docs/CLOUD_DEPLOYMENT.md"),
                "public_healthcheck_artifact": exists("data/eval/cloud_healthcheck_v1.json"),
            },
            all(
                [
                    exists("docs/CLOUD_DEPLOYMENT.md"),
                    exists("data/eval/cloud_healthcheck_v1.json"),
                ]
            )
            and (exists("azure.yaml") or exists("infra") or exists(".azure")),
            "GT2 is a hard gate: the EEP must be publicly reachable for grading.",
        ),
        gate(
            "CFX-G08",
            "Demo evidence package",
            "Stress lab, reliability certificate, pair coverage, and final demo script exist",
            {
                "arabizi_stress_lab": exists("data/eval/arabizi_stress_lab_v1.json"),
                "reliability_certificate": exists("data/eval/arabizi_reliability_certificate_v1.html"),
                "pair_coverage": exists("data/eval/arabizi_pair_coverage_v1.json"),
                "demo_script": exists("docs/DEMO_SCRIPT.md"),
            },
            all(
                [
                    exists("data/eval/arabizi_stress_lab_v1.json"),
                    exists("data/eval/arabizi_reliability_certificate_v1.html"),
                    exists("data/eval/arabizi_pair_coverage_v1.json"),
                    exists("docs/DEMO_SCRIPT.md"),
                ]
            ),
            "The demo must show live input, intermediate AI outputs, metrics, fallback, and MLOps proof.",
        ),
        gate(
            "CFX-G09",
            "QA breadth",
            ">=30 unit/regression tests plus all validators present",
            {
                "test_count": test_count,
                "validators": {
                    "corpus": exists("scripts/validate_cedarfix_corpus.py"),
                    "vocab": exists("scripts/validate_arabizi_vocabulary.py"),
                    "benchmark": exists("scripts/validate_arabizi_benchmark.py"),
                    "oov_queue": exists("scripts/validate_arabizi_oov_queue.py"),
                },
            },
            test_count >= 30
            and all(
                [
                    exists("scripts/validate_cedarfix_corpus.py"),
                    exists("scripts/validate_arabizi_vocabulary.py"),
                    exists("scripts/validate_arabizi_benchmark.py"),
                    exists("scripts/validate_arabizi_oov_queue.py"),
                ]
            ),
            "QA needs to scale with the system as IEP-2/3/4 are added.",
        ),
    ]

    recommended_build_order = [
        {
            "rank": 1,
            "task": "Build IEP-2 dedup/cluster service with pair-evaluation artifact",
            "rubric_unlock": "T3, T4, T5, D3",
            "why": "Incident fusion is the core CedarFix originality beyond a complaint dashboard.",
        },
        {
            "rank": 2,
            "task": "Build IEP-3 calibrated routing with threshold sweep and false-auto-route metrics",
            "rubric_unlock": "T1, T5, M2, D3",
            "why": "Calibration makes the routing decision defensible under professor attack.",
        },
        {
            "rank": 3,
            "task": "Expand Batch 002 with Arabizi/mixed hard negatives and unrelated negatives",
            "rubric_unlock": "P2, T5, Q2, M2",
            "why": "Better data beats clever architecture with weak validation.",
        },
        {
            "rank": 4,
            "task": "Add IEP-4 explanation/HITL service with prompt tests and audit output",
            "rubric_unlock": "T4, D2, D3, M4",
            "why": "This connects AI outputs to human decisions and makes the demo understandable.",
        },
        {
            "rank": 5,
            "task": "Add MLflow + Prometheus/Grafana with low-cardinality ML signals",
            "rubric_unlock": "M1, M2, M3, S4",
            "why": "MLOps evidence is 10% of the rubric and strengthens Q&A.",
        },
        {
            "rank": 6,
            "task": "Prepare cloud deployment and public healthcheck artifact",
            "rubric_unlock": "GT2, S5, D1",
            "why": "Public cloud EEP is a hard gate.",
        },
    ]

    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "scope": "CedarFix next-phase readiness gates",
            "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
            "strict_mode_note": "Default mode reports honestly and exits 0; --strict exits 1 if any gate fails.",
        },
        "summary": {
            "readiness": "READY_FOR_FINAL_RELEASE" if all(item["pass"] for item in gates) else "NOT_READY_FOR_FINAL_RELEASE",
            "gate_pass_count": sum(1 for item in gates if item["pass"]),
            "gate_total": len(gates),
            "test_count": test_count,
        },
        "gates": gates,
        "recommended_build_order": recommended_build_order,
    }


def print_report(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("  CedarFix Next-Phase Gate Audit")
    print("=" * 72)
    print(f"Readiness    : {summary['readiness']}")
    print(f"Gates passed : {summary['gate_pass_count']}/{summary['gate_total']}")
    print(f"Test count   : {summary['test_count']}")
    print("\nGates:")
    for item in result["gates"]:
        status = "PASS" if item["pass"] else "BLOCKED"
        print(f"  {status:<7} {item['gate_id']} {item['name']}")
    print("\nTop next tasks:")
    for task in result["recommended_build_order"][:4]:
        print(f"  {task['rank']}. {task['task']} [{task['rubric_unlock']}]")
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit CedarFix next-phase gates.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write JSON artifact.")
    parser.add_argument("--strict", action="store_true", help="Exit 1 if any next-phase gate is blocked.")
    args = parser.parse_args(argv)

    result = audit()
    if not args.no_save:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT_PATH.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print_report(result)
    if args.strict and result["summary"]["readiness"] != "READY_FOR_FINAL_RELEASE":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
