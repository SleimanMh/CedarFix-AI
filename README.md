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

## CI

Three jobs: **validate-and-test** → **arabizi-eval-gate** → **docker-build** (skips gracefully until Dockerfiles exist).
