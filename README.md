# CedarFix Command AI

> Multilingual municipal incident command system for Lebanon.  
> EECE503N / EECE798N — AUB, Spring 2026

CedarFix converts fragmented multilingual citizen reports (Arabic, English, French, Arabizi, mixed) into deduplicated, clustered, prioritized, and explainable infrastructure incidents for Lebanese municipal operations.

## Decision Loop

```text
Citizen report → EEP (ingest/validate)
              → IEP-1 (multilingual extraction + Arabizi drift)
              → IEP-2 (duplicate detection / cluster fusion)
              → IEP-3 (calibrated routing + priority)
              → IEP-4 (SHAP explanation / HITL queue)
              → MLflow feedback loop
```

## Services

| Service | Role | Status |
| --- | --- | --- |
| EEP | `POST /complaints` · `GET /complaints/{id}/status` | planned |
| IEP-1 | Language signal extraction, Arabizi OOV drift | heuristic probe live |
| IEP-2 | Dedup / cluster assignment (XLM-R + pgvector) | planned |
| IEP-3 | Calibrated routing (LightGBM + Platt + SHAP) | planned |
| IEP-4 | LLM explanation, HITL queue | planned |
| MLflow | Experiment tracking, champion/challenger | planned |
| PostgreSQL | Incident store | planned |
| Redis | Streams + Celery broker | planned |

## Repository Layout

```text
src/shared/          # Shared schemas, Arabizi features, lexical policy
scripts/             # Validators, eval harness, OOV analyzer, tests
data/corpus/         # Labeled reports, clusters, pairs (Batch 001 — 52 rows)
data/eval/           # Benchmark + evaluation artifacts
data/knowledge_base/ # Arabizi vocabulary v1.4.0
docs/                # Architecture contracts, drift radar, corpus protocol
.github/workflows/   # CedarFix CI (validate → eval gate → docker build)
```

## Quick Start

```bash
python -m venv .venv && source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run all validators + unit tests
python scripts/validate_arabizi_vocabulary.py
python scripts/validate_cedarfix_corpus.py
python scripts/validate_arabizi_oov_queue.py
python scripts/validate_arabizi_benchmark.py
python scripts/analyze_arabizi_oov.py --self-test
python -m unittest discover -s scripts/tests -p "test_*.py" -v

# Run Arabizi coverage evaluation (Batch 001)
python scripts/evaluate_arabizi_coverage.py

# Run adversarial Arabizi Stress Lab
python scripts/run_arabizi_stress_lab.py

# Generate a live Arabizi reliability certificate (JSON + HTML)
python scripts/certify_arabizi_input.py

# Audit whether Arabizi is ready for final best-in-class claims
python scripts/audit_arabizi_excellence_gates.py
python scripts/evaluate_arabizi_pair_coverage.py

# Audit full-project next-phase gates and rubric readiness
python scripts/audit_cedarfix_next_phase_gates.py
python scripts/audit_rubric_readiness.py
```

## Corpus — Batch 001

- **52 reports** · 12 clusters · 90 pairs (20% hard-negative ratio)
- **14 Arabizi / mixed** rows — reviewed and approved (`CODEX-A2`)
- Arabizi vocab: **v1.4.0** · 10 tokens promoted · benchmark SHA locked

## Key Numbers (Batch 001 Arabizi eval)

| Metric | Value |
| --- | --- |
| Mean known-term coverage | 97.7% |
| Mean OOV tokens / row | 0.21 |
| Drift score ≥ 2 rate | 28.6% |
| Issue-type probe recall | 100% (14/14) |

## Arabizi Stress Lab

`scripts/run_arabizi_stress_lab.py` attacks the language layer with messy
Lebanese Arabizi: missing numerals, repeated letters, fused no-space tokens,
panic shorthand, and French/English code-switching. It writes
`data/eval/arabizi_stress_lab_v1.json` and is covered by permanent unit tests.

Current purpose: demo/regression evidence, not final held-out F1.

## Live Reliability Certificate

`scripts/certify_arabizi_input.py` takes one live report, generates noisy
Arabizi variants, reruns IEP-1, and writes:

- `data/eval/arabizi_reliability_certificate_v1.json`
- `data/eval/arabizi_reliability_certificate_v1.html`

This is the presentation artifact for showing decision stability, OOV drift,
HITL triggers, and vocabulary lineage on a single live input.

## Next-Phase Arabizi Gates

`scripts/audit_arabizi_excellence_gates.py` and
`scripts/evaluate_arabizi_pair_coverage.py` keep the next phase honest:
Batch 002 scale, native Lebanese review, cross-language duplicate pairs,
hard negatives, unrelated negatives, and demo/evidence artifacts are all
tracked before any final best-in-class Arabizi claim is made.

## Full Project Gates

`scripts/audit_cedarfix_next_phase_gates.py` and
`scripts/audit_rubric_readiness.py` apply the same standard to the full
CedarFix project: IEP-2, IEP-3, IEP-4, MLOps, monitoring, cloud deployment,
demo evidence, QA breadth, and rubric readiness.

## CI

Three jobs: **validate-and-test** → **arabizi-eval-gate** → **docker-build** (skips gracefully until Dockerfiles exist).
