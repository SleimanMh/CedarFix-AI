#!/usr/bin/env python3
"""Evidence-based rubric readiness audit for CedarFix.

Scores are conservative 0/1/2 estimates based on implemented artifacts in the
repo. This is not a grading oracle; it is a ruthless checklist that says what
evidence is missing before each rubric item can credibly score 2.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "data" / "eval" / "rubric_readiness_v1.json"


def exists(relative: str) -> bool:
    return (ROOT / relative).exists()


def read_text(relative: str) -> str:
    path = ROOT / relative
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def compose_has(service: str) -> bool:
    return f"\n  {service}:" in read_text("docker-compose.yml")


def score_item(code: str, wording: str, score: int, evidence: list[str], missing_for_2: str) -> dict[str, Any]:
    return {
        "code": code,
        "wording": wording,
        "score": score,
        "evidence": evidence,
        "missing_for_2": missing_for_2 if score < 2 else "",
    }


def audit() -> dict[str, Any]:
    eep_iep1_ready = all(
        [
            exists("src/eep/main.py"),
            exists("src/iep1/main.py"),
            compose_has("eep"),
            compose_has("iep1"),
            exists("scripts/tests/test_eep_iep1_contracts.py"),
        ]
    )
    arabizi_artifacts = all(
        [
            exists("data/eval/arabizi_benchmark_v0_regression.csv"),
            exists("data/eval/arabizi_stress_lab_v1.json"),
            exists("data/eval/arabizi_reliability_certificate_v1.html"),
        ]
    )
    iep2_ready = exists("src/iep2/main.py") and exists("data/eval/iep2_pair_eval_v1.json")
    iep3_ready = exists("src/iep3/main.py") and exists("data/eval/iep3_calibration_v1.json")
    iep4_ready = exists("src/iep4/main.py") and exists("scripts/tests/test_iep4_explanations.py")
    mlops_ready = compose_has("mlflow") and exists("data/eval/mlflow_run_manifest_v1.json")
    obs_ready = compose_has("prometheus") and compose_has("grafana") and exists("docs/MONITORING_SIGNALS.md")
    cloud_ready = exists("data/eval/cloud_healthcheck_v1.json") and (exists("azure.yaml") or exists("infra") or exists(".azure"))

    baseline_gates = [
        score_item(
            "GT1",
            "Demo works end-to-end",
            1 if eep_iep1_ready else 0,
            ["EEP/IEP-1 local spine exists"] if eep_iep1_ready else [],
            "Build IEP-2/IEP-3/IEP-4 and run one full submission-to-explanation demo.",
        ),
        score_item(
            "GT2",
            "Public cloud API functional",
            2 if cloud_ready else 0,
            ["Cloud healthcheck artifact exists"] if cloud_ready else [],
            "Deploy EEP publicly and save cloud healthcheck artifact.",
        ),
        score_item(
            "GT3",
            "Architecture minimum met",
            1 if eep_iep1_ready else 0,
            ["Docker Compose includes EEP/IEP-1/Postgres/Redis"] if eep_iep1_ready else [],
            "Add independent IEP-2 and IEP-3 services plus EEP orchestration across them.",
        ),
        score_item(
            "GT4",
            "Required deliverables complete",
            1 if exists("README.md") and exists("docs/CEDARFIX_AI_FINAL_PROJECT_PLAN.md") else 0,
            ["README and project plan exist"],
            "Add final report, demo script, architecture diagram, and deployment docs.",
        ),
        score_item(
            "GT5",
            "Type-specific minimum met",
            1 if arabizi_artifacts else 0,
            ["Arabizi benchmark/stress/certificate artifacts exist"] if arabizi_artifacts else [],
            "Complete incident fusion + calibrated routing as the type-specific AI workflow.",
        ),
    ]

    weighted_items = [
        score_item("T1", "AI depth and non-triviality", 1, ["Arabizi OOV/drift + EEP/IEP-1 contracts"], "Implement IEP-2 multimodal dedup and IEP-3 calibrated routing with evidence."),
        score_item("T2", "IEP 1 independence and value", 2 if eep_iep1_ready and arabizi_artifacts else 1, ["IEP-1 service/probe, Arabizi gates, stress lab"], "Train/evaluate final IEP-1 model over Batch 002+ if claiming full ML."),
        score_item("T3", "IEP 2 independence and value", 2 if iep2_ready else 0, [], "Build dedup service, pair scoring, cluster assignment, and pair-eval artifact."),
        score_item("T4", "EEP orchestration logic", 1 if eep_iep1_ready else 0, ["EEP enqueues IEP-1 and handles queue fallback"], "Orchestrate IEP-1 -> IEP-2 -> IEP-3 -> IEP-4 with retries/timeouts/state transitions."),
        score_item("T5", "Tradeoff evidence", 1 if arabizi_artifacts else 0, ["Arabizi raw/stress/certificate evidence"], "Add dedup threshold tradeoffs, routing calibration sweeps, and ablation tables."),
        score_item("T6", "Execution quality and edge cases", 1 if eep_iep1_ready else 0, ["PII scrub, GPS/image validation, queue fallback"], "Add IEP-2/3/4 edge-case tests and timeout handling."),
        score_item("S1", "Service boundaries and contracts", 1 if eep_iep1_ready else 0, ["EEP/IEP-1 contracts"], "Add Pydantic contracts for IEP-2/3/4 outputs."),
        score_item("S2", "Validation and request constraints", 2 if exists("src/eep/models.py") else 0, ["EEP validates text/GPS/language/image"], ""),
        score_item("S3", "Errors, timeouts, retries, fallbacks", 1 if exists("src/eep/main.py") else 0, ["EEP queue-unavailable fallback"], "Add Redis retry/backoff, IEP worker timeout handling, and DLQ evidence."),
        score_item("S4", "Containerization and orchestration", 1 if compose_has("eep") and compose_has("iep1") else 0, ["Docker Compose for EEP/IEP-1/Postgres/Redis"], "Add IEP-2/3/4, MLflow, Prometheus, Grafana containers."),
        score_item("S5", "Deployment architecture and secrets", 1 if exists(".env.cedarfix.example") else 0, ["Safe env example exists"], "Add cloud deployment docs and secret handling in deployed environment."),
        score_item("P1", "Problem / research question clarity", 2 if exists("docs/CEDARFIX_AI_FINAL_PROJECT_PLAN.md") else 1, ["Project plan and README define decision loop"], ""),
        score_item("P2", "Baseline / benchmark rigor", 1 if exists("data/eval/arabizi_benchmark_v0_regression.csv") else 0, ["Arabizi regression benchmark exists"], "Add IEP-2/IEP-3 baselines and Batch 002 held-out split."),
        score_item("P3", "AI justification / contribution", 1 if arabizi_artifacts else 0, ["Arabizi reliability contribution"], "Show measurable lift over baselines for dedup/routing."),
        score_item("P4", "Value or publishability", 1 if exists("README.md") else 0, ["Lebanon-specific municipal framing"], "Add final evaluation, limitations, and reproducible demo evidence."),
        score_item("D1", "Demo completeness", 1 if exists("data/eval/arabizi_reliability_certificate_v1.html") else 0, ["Arabizi certificate demo artifact"], "Run end-to-end live submission through all services."),
        score_item("D2", "Technical clarity", 1 if exists("docs/IEP1_LANGUAGE_SIGNAL_CONTRACT.md") else 0, ["IEP-1 contract docs"], "Add architecture diagram and service-by-service demo annotations."),
        score_item("D3", "Evidence shown", 1 if arabizi_artifacts else 0, ["Stress lab/certificate/gates artifacts"], "Add IEP-2/3 metrics, MLflow run, and monitoring screenshots/artifacts."),
        score_item("D4", "Q&A and delivery", 0, [], "Prepare professor attack answers and 8-10 minute rehearsed script."),
        score_item("D5", "Visual polish / wow", 1 if exists("data/eval/arabizi_reliability_certificate_v1.html") else 0, ["HTML reliability certificate"], "Add command-center UI/dashboard/map and monitoring panel."),
        score_item("C1", "Originality", 2 if arabizi_artifacts else 1, ["Lebanese Arabizi reliability layer"], ""),
        score_item("C2", "Insightful design choices", 2 if arabizi_artifacts and exists("data/corpus/arabizi_oov_review_queue_v1.csv") else 1, ["OOV queue, stress lab, reliability certificate"], ""),
        score_item("Q1", "Test suite breadth", 1, ["Unit/regression tests exist"], "Reach 30+ tests including IEP-2/3/4 and API integration tests."),
        score_item("Q2", "Regression / validation strategy", 2 if arabizi_artifacts else 1, ["Validators, benchmark, stress lab, certificate"], ""),
        score_item("G1", "Commit history and ownership", 0, [], "Use branches/commits per teammate and issue-linked changes."),
        score_item("G2", "Branching, review, traceability", 0, [], "Create issue/PR trail and review checklist."),
        score_item("M1", "Automated lifecycle pipeline", 0, [], "Add MLflow training/eval/promotion workflow."),
        score_item("M2", "Experiment tracking and thresholds", 1 if exists("data/eval/arabizi_excellence_gates_v1.json") else 0, ["Arabizi gate artifacts"], "Add MLflow runs for IEP-2/3 thresholds."),
        score_item("M3", "Monitoring and ML-specific signals", 0, [], "Add Prometheus/Grafana and ML metrics contract."),
        score_item("M4", "Documentation completeness", 1, ["README and multiple contracts/docs exist"], "Add final report, deployment doc, monitoring doc, demo script."),
    ]

    weighted_score = sum(item["score"] for item in weighted_items)
    weighted_max = len(weighted_items) * 2
    return {
        "meta": {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "scope": "Conservative implemented-evidence rubric readiness",
            "output_path": str(OUTPUT_PATH.relative_to(ROOT)),
        },
        "summary": {
            "baseline_gate_pass_estimate": sum(1 for item in baseline_gates if item["score"] == 2),
            "baseline_gate_total": len(baseline_gates),
            "weighted_points_estimate": weighted_score,
            "weighted_points_max": weighted_max,
            "weighted_item_average": round(weighted_score / weighted_max, 4),
            "highest_roi_blockers": [
                "IEP-2 dedup service and pair-eval artifact",
                "IEP-3 calibrated routing and threshold sweep",
                "Cloud EEP deployment healthcheck",
                "MLflow + monitoring stack",
                "Final demo script and command-center visual",
            ],
        },
        "baseline_gates": baseline_gates,
        "weighted_items": weighted_items,
    }


def print_report(result: dict[str, Any]) -> None:
    summary = result["summary"]
    print("\n" + "=" * 72)
    print("  CedarFix Rubric Readiness Audit")
    print("=" * 72)
    print(f"Baseline gates at full pass : {summary['baseline_gate_pass_estimate']}/{summary['baseline_gate_total']}")
    print(f"Weighted points estimate    : {summary['weighted_points_estimate']}/{summary['weighted_points_max']}")
    print(f"Weighted item average       : {summary['weighted_item_average']:.1%}")
    print("\nHighest ROI blockers:")
    for idx, item in enumerate(summary["highest_roi_blockers"], start=1):
        print(f"  {idx}. {item}")
    print(f"\nArtifact: {OUTPUT_PATH.relative_to(ROOT)}")
    print("=" * 72 + "\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit CedarFix rubric readiness.")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout.")
    parser.add_argument("--no-save", action="store_true", help="Do not write JSON artifact.")
    args = parser.parse_args(argv)

    result = audit()
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
