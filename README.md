# CedarFix Command AI

Lebanon-specific multilingual municipal incident intelligence.

CedarFix converts fragmented citizen reports in Arabic, English, French,
Arabizi, and mixed language into validated, deduplicated, prioritized, and
explainable infrastructure incidents for municipal operations.

## Operational Question

```text
Which reported incident should be escalated first, who should handle it, and why?
```

The project is intentionally not a generic complaint dashboard. The AI work is
the incident-intelligence spine:

```text
citizen submission
  -> EEP validation, PII scrub, queue fallback
  -> IEP-1 multilingual extraction + Arabizi drift signal
  -> IEP-2 duplicate / cluster fusion
  -> IEP-3 calibrated routing + priority
  -> IEP-4 explanation + HITL audit
  -> MLflow / monitoring / retraining candidate loop
```

## Current State

| Area | Status | Evidence |
| --- | --- | --- |
| EEP | Implemented locally | FastAPI service, request validation, PII scrub, Redis fallback, Dockerfile |
| IEP-1 | Implemented as heuristic probe + service | Arabizi/OOV features, extraction contract, worker, Dockerfile |
| IEP-2 | Not built yet | Pair labels and coverage artifacts are ready |
| IEP-3 | Not built yet | Routing/calibration is next after IEP-2 |
| IEP-4 | Prompt assets only | Service and tests still needed |
| Data | Batch 001+002 active | 80 reports, 18 clusters, 107 pairs |
| QA | Passing | 31 unit/regression tests |
| Final release | Not ready | Next-phase gates: 2/9 |

## Data

Gold data lives in `data/corpus/` and is human-authored for the CedarFix domain.
External Arabizi data was removed because it did not provide enough useful
Lebanese municipal signal.

| Dataset file | Purpose |
| --- | --- |
| `data/corpus/cedarfix_reports_v1.csv` | Labeled citizen reports |
| `data/corpus/cedarfix_clusters_v1.csv` | Incident cluster metadata |
| `data/corpus/cedarfix_pairs_v1.csv` | Duplicate, related, hard-negative, unrelated pair labels |
| `data/corpus/arabizi_oov_review_queue_v1.csv` | Arabizi/OOV drift review queue |
| `data/knowledge_base/arabizi_vocabulary.json` | Arabizi vocabulary v1.4.0 |
| `data/knowledge_base/*.csv|*.json|*.yaml` | GPS, route, sector, severity references |

Current Batch 001+002 counts:

| Metric | Count |
| --- | ---: |
| Reports | 80 |
| Clusters | 18 |
| Pairs | 107 |
| Arabizi rows | 32 |
| Mixed rows | 8 |
| Duplicate pairs | 71 |
| Related pairs | 8 |
| Hard-negative pairs | 14 |
| Unrelated pairs | 14 |

## Evidence Artifacts

| Artifact | Purpose |
| --- | --- |
| `data/eval/arabizi_benchmark_v0_regression.csv` | Frozen Arabizi regression benchmark |
| `data/eval/arabizi_coverage_batch001.json` | Batch 001 Arabizi coverage/OOV evaluation |
| `data/eval/arabizi_stress_lab_v1.json` | Adversarial Arabizi stress lab output |
| `data/eval/arabizi_reliability_certificate_v1.html` | Demo-ready live reliability certificate |
| `data/eval/arabizi_pair_coverage_v1.json` | Arabizi duplicate/negative pair coverage |
| `data/eval/arabizi_excellence_gates_v1.json` | Honest Arabizi readiness audit |
| `data/eval/cedarfix_next_phase_gates_v1.json` | Full-project next-phase gate audit |
| `data/eval/rubric_readiness_v1.json` | Conservative rubric readiness estimate |

Current Arabizi evidence:

| Metric | Value |
| --- | ---: |
| Arabizi/mixed rows | 40 |
| Mean known-term coverage | 85.0% |
| Mean OOV tokens per row | 1.24 |
| Issue-type probe recall | 100.0% |
| Arabizi-involving pairs | 57 |
| Cross-language duplicate pairs | 37 |
| Arabizi gates | 5/6 |

Important limitation: Batch 001 is regression and demo evidence, not final
generalization evidence. Final Arabizi F1 claims require Batch 002+ scale and
native Lebanese dialect review.

## Repository Layout

```text
.github/workflows/   CI pipeline
data/corpus/         Human-authored reports, clusters, pair labels
data/eval/           Generated benchmark/evaluation/readiness artifacts
data/knowledge_base/ Routing, severity, GPS, Arabizi vocabulary references
docs/                Core project, annotation, corpus, and contract docs
prompts/             IEP-4 prompt versions
scripts/             Validators, evaluators, auditors, demo artifact generators
src/eep/             External Entry Point API
src/iep1/            Language-signal service and worker
src/shared/          Shared schemas and Arabizi feature logic
```

## Setup

PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Do not commit real secrets. For local Docker, create `.env.cedarfix` from the
safe template:

```powershell
Copy-Item .env.cedarfix.example .env.cedarfix
```

## Validate

Run the same core checks as CI:

```powershell
python scripts/validate_arabizi_vocabulary.py
python scripts/validate_cedarfix_corpus.py
python scripts/validate_arabizi_oov_queue.py
python scripts/validate_arabizi_benchmark.py
python -m unittest discover -s scripts/tests -p "test_*.py" -v
```

Expected current result:

```text
corpus/vocab/OOV/benchmark validators: 0 warnings
unit tests: 31 passed
```

## Evaluate And Audit

```powershell
python scripts/evaluate_arabizi_coverage.py
python scripts/run_arabizi_stress_lab.py
python scripts/certify_arabizi_input.py
python scripts/evaluate_arabizi_pair_coverage.py
python scripts/audit_arabizi_excellence_gates.py
python scripts/audit_cedarfix_next_phase_gates.py
python scripts/audit_rubric_readiness.py
python scripts/validate_arabizi_reliability.py
python scripts/build_arabizi_v13_variant_audit.py
```

Current readiness:

| Audit | Current result |
| --- | --- |
| Arabizi excellence gates | 5/6, not final-claim ready (ARZ-G02 needs native review) |
| Full project gates | 2/9, not final-release ready |
| Rubric readiness estimate | 30/60 weighted evidence points |

## Run Locally With Docker

```powershell
Copy-Item .env.cedarfix.example .env.cedarfix
docker compose --env-file .env.cedarfix up --build
```

Local services:

| Service | URL |
| --- | --- |
| EEP health | `http://127.0.0.1:8000/health` |
| IEP-1 health | `http://127.0.0.1:8001/health` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

The current Docker stack contains Postgres, Redis, EEP, and IEP-1. IEP-2,
IEP-3, IEP-4, MLflow, Prometheus, and Grafana are still planned.

## CI

GitHub Actions runs:

1. Validate corpus, vocabulary, OOV queue, benchmark, and unit tests.
2. Run Arabizi coverage evaluation and upload `arabizi_coverage_batch001.json`.
3. Build Docker images for services whose Dockerfiles exist.

## Key Docs

| File | Use |
| --- | --- |
| `docs/CEDARFIX_AI_FINAL_PROJECT_PLAN.md` | Full strategy and rubric plan |
| `docs/CORPUS_AUTHORING_PROTOCOL.md` | How to author/validate corpus batches |
| `docs/ANNOTATION_GUIDELINES.md` | Labeling rules and taxonomies |
| `docs/IEP1_LANGUAGE_SIGNAL_CONTRACT.md` | IEP-1 output contract |
| `docs/ARABIZI_DRIFT_RADAR.md` | Arabizi/OOV drift loop |
| `docs/LOCAL_DOCKER_RUNBOOK.md` | Docker runbook |

## Next Build Order

1. Build IEP-2 duplicate/cluster service with pair-evaluation artifact.
2. Build IEP-3 calibrated routing with threshold sweep and false-auto-route metrics.
3. Obtain native Lebanese dialect review for Batch 001+002 Arabizi rows (ARZ-G02).
4. Add IEP-4 explanation/HITL service with prompt tests and audit output.
5. Add MLflow plus Prometheus/Grafana with low-cardinality ML signals.
6. Deploy the public cloud EEP and save a healthcheck artifact.

Highest-ROI next step: **IEP-2 dedup/cluster service**.
