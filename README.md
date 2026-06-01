# CedarFix — AI-Powered Municipal Complaint Intelligence

Lebanon-specific multilingual municipal incident intelligence.

CedarFix converts fragmented citizen reports in Arabic, English, French,
Arabizi, and mixed language into validated, deduplicated, prioritized, and
explainable infrastructure incidents for municipal operations.

## Explain It To A Friend

Imagine people are reporting problems around a city: potholes, garbage piles,
water leaks, power hazards, flooding, broken internet, or safety issues. The
reports are messy: some are in English, some in Arabic, some in Lebanese
Arabizi, some include GPS, some include photos, and many people may report the
same real-world incident.

CedarFix is the system that turns those messy reports into an operational case:

1. It accepts the report and gives it a tracking ID.
2. It understands the language and issue type.
3. It checks whether the report is a duplicate of an existing incident.
4. It decides which municipality or public entity should handle it.
5. It refuses to auto-route dangerous or uncertain cases and sends them to a
   human reviewer.
6. It writes explanations for citizens and operators.
7. It tracks whether the incident was resolved or reopened.
8. It monitors whether model confidence is honest over time.
9. It only suggests resolution steps when those steps are backed by verified KB
   evidence.

The project is not just "classify complaint text." It is a miniature civic AI
pipeline with intake, routing, safety gates, explanations, lifecycle tracking,
monitoring, and grounded resolution planning.

## Operational Question

```text
Which reported incident should be escalated first, who should handle it, and why?
```

The project is intentionally not a generic complaint dashboard. The AI pipeline is
the incident-intelligence spine:

```text
citizen submission
  -> EEP  — validation, PII scrub, postgres persistence, Redis queue fallback
  -> IEP-1 — multilingual extraction, Lebanese arabizi NLP, sector/issue classification
  -> IEP-2 — near-duplicate detection and complaint fusion
  -> IEP-3 — calibrated routing to municipality or public entity
  -> IEP-6 — multimodal CLIP image↔text fusion (only when a photo is attached)
  -> IEP-4 — citizen-facing explanation and HITL audit narrative (terminal)
  -> IEP-5 — incident lifecycle + "reopen = retraining signal"
  -> IEP-8 — source-grounded resolution plan with faithfulness verification

IEP-7 — standalone calibration & drift monitor (ECE / Brier per sector)
Civic Intelligence Compiler — proof-carrying incident program tying every IEP
into one auditable autonomy decision
```

All services emit Prometheus metrics on `/metrics`; Prometheus scrapes every
service and Grafana renders the pipeline, language-quality, routing, and
calibration dashboards. See `docs/MONITORING_SIGNALS.md`.

## Current State

| Area | Status | Notes |
| --- | --- | --- |
| EEP | ✅ Built | FastAPI intake, request validation, PII scrub, Redis fallback, Dockerfile |
| IEP-1 | ✅ Built | Arabizi tokenization/normalization, sector/issue classification, v14 vocab |
| IEP-2 | ✅ Built | Similarity-hashing deduplication service, worker, Dockerfile |
| IEP-3 | ✅ Built | Municipality/entity routing service, router, worker, Dockerfile |
| IEP-4 | ✅ Built | Explainer service, citizen narrative generation, worker, Dockerfile |
| IEP-5 | ✅ Built | Incident lifecycle (event-sourced) + reopen→retraining-candidate signal |
| IEP-6 | ✅ Built | Multimodal CLIP zero-shot image↔text late fusion (agree/conflict/disambiguate) |
| IEP-7 | ✅ Built | Calibration & drift monitor — per-sector ECE/Brier, Prometheus gauges |
| IEP-8 | ✅ Built | Grounded resolution co-pilot — KB retrieval, citation verifier, abstention |
| Civic Compiler | ✅ Built | Belief state, proof obligations, counterfactuals, active sensing, autonomy governor |
| Monitoring | ✅ Live | Every service exposes `/metrics`; Prometheus scrape + Grafana provisioning in `infra/` |
| Deployment | ✅ Configured | `azure.yaml` maps all services to Azure Container Apps via `azd` |
| Knowledge base | ✅ Complete | 1,107 municipality registry rows, 21 entity records, 64 complaint types, 70 routing rules, 5,772-term language bank |
| Training data | ✅ Ready | v29 batch8 train (91,150) + val (10,562), locked batch7/telecom evals, top-tier reference set |

## Repository Layout

```text
.github/workflows/         CI pipeline (lint, test, Docker build)
azure.yaml                 Azure Developer CLI deployment config (eep + iep1-iep8 -> Container Apps)
docker-compose.yml         Local dev stack (all services + redis, postgres, prometheus, grafana)
infra/                     Prometheus scrape config + Grafana provisioning
requirements.txt           Python dependencies

src/
  route_complaint.py       Top-level runtime router (loads municipality CSVs + arabizi vocab)
  eep/                     External Event Pipeline — HTTP intake, PII scrub, queue
  iep1/                    Language extraction — arabizi NLP, sector/issue classification
  iep2/                    Deduplication Service — near-duplicate detection
  iep3/                    Routing Service — municipality and public entity mapping
  iep4/                    Explainer Service — citizen-facing resolution narratives
  iep5/                    Incident Lifecycle — event-sourced timeline + retraining signal
  iep6/                    Multimodal Fusion — CLIP zero-shot image↔text fusion
  iep7/                    Calibration & Drift Monitor — per-sector ECE/Brier
  iep8/                    Grounded Resolution Co-Pilot — retrieval + faithfulness verifier
  shared/                  Common schemas, metrics, civic_compiler, arabizi_features, arabizi_lexical_policy

data/
  knowledge_base/
    arabizi_vocabulary.json          Runtime arabizi lexicon (v14, 3.29 MB, 31k+ terms)
    arabizi/                         NLP support — master index, hard negatives, OOV queue, stoplist
    municipalities/                  Municipality runtime data (registry, aliases, mappings, unions)
    entities/                        Lebanese public entity definitions (MEW, EDL, OGERO, CDR, …)
    cedarfix_language_bank.csv       5,772 approved arabizi terms with sector/issue hints
    complaint_taxonomy.csv           64 complaint types with routing defaults and HITL flags
    routing_rules.csv                70 routing rules keyed to complaint_type_id
    remediation_workflows.csv        59 resolution workflows with SLA policies
    cedarfix_complaint_scenario_inventory.csv  165 complaint scenarios with failure modes
    [+ 7 more reference CSVs/JSONs]
  complaint_intelligence/
    municipality_research_tracker.csv   800-row municipality research tracker (merged)
    municipality_source_research.csv    12 source research records (merged)
    discovered_complaint_leads.csv      156 complaint leads
    normalized/municipal_official_process_seed.jsonl  78 seed CIE events
    [+ scaleout findings, source targets, schema, news policy]
  review_queue/            5 human review queues from legacy 100k complaint corpus
  training/                JSONL train/validation/test files, manifests, and backups
```

## Knowledge Base

| File | Rows | Purpose |
| --- | ---: | --- |
| `municipalities/national_municipality_registry.csv` | 1,107 | Canonical municipality registry rows |
| `municipalities/municipality_aliases.csv` | 3,870 | Name variant → registry/municipality ID lookup |
| `municipalities/municipality_service_mappings.csv` | 1,107 | Registry-row → service area mappings (runtime) |
| `municipalities/municipality_unions.csv` | 59 | Federation definitions |
| `municipalities/municipality_official_channels.csv` | 102 | Contact channel rows |
| `municipalities/municipality_complaint_workflows.csv` | 30 | Seed resolution workflow rows |
| `cedarfix_language_bank.csv` | 5,772 | Approved arabizi terms |
| `cedarfix_language_bank_review_queue.csv` | 7,298 | Candidate terms pending review |
| `complaint_taxonomy.csv` | 64 | Complaint type definitions |
| `routing_rules.csv` | 70 | Complaint → entity routing rules |
| `remediation_workflows.csv` | 59 | End-to-end resolution workflows |
| `arabizi/lebanese_arabizi_master_index.csv` | 31,032 | Full arabizi variant index |

Municipality counts are intentionally labeled by what they count: `1,107` is
complete registry-row/runtime coverage, while `800` is currently populated
official `municipality_id` coverage. Rows without official IDs route through
`registry_id` fallback.

## Training Data

| File | Examples | Purpose |
| --- | ---: | --- |
| `cidarfix_v29_batch8_train_v14_enriched.jsonl` | 91,150 | IEP-1 fine-tuning (v14 enriched) |
| `cidarfix_v29_batch8_val_v14_enriched.jsonl` | 10,562 | Validation |
| `cidarfix_v29_batch7_model_final_test_locked.jsonl` | 7,940 | Locked final test set (do not train on) |
| `cidarfix_v29_top_tier_generated_v1.jsonl` | 242 | Curated reference examples |
| `cidarfix_telecom_eval_locked.jsonl` | 150 | Locked telecom-specific evaluation set |

## Setup

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

## Run Locally With Docker

```powershell
Copy-Item .env.cedarfix.example .env.cedarfix
docker compose --env-file .env.cedarfix up --build
```

Local services:

| Service | URL |
| --- | --- |
| EEP | `http://127.0.0.1:8000/health` |
| IEP-1 | `http://127.0.0.1:8001/health` |
| IEP-2 | `http://127.0.0.1:8002/health` |
| IEP-3 | `http://127.0.0.1:8003/health` |
| IEP-4 | `http://127.0.0.1:8004/health` |
| IEP-5 | `http://127.0.0.1:8005/health` |
| IEP-6 | `http://127.0.0.1:8006/health` |
| IEP-7 | `http://127.0.0.1:8007/calibration/latest` |
| IEP-8 | `http://127.0.0.1:8008/health` (POST `/resolve` for a grounded plan) |
| Prometheus | `http://127.0.0.1:9090` |
| Grafana | `http://127.0.0.1:3000` |
| PostgreSQL | `127.0.0.1:5432` |
| Redis | `127.0.0.1:6379` |

## Deploy to Azure

Requires [Azure Developer CLI](https://learn.microsoft.com/azure/developer/azure-developer-cli/):

```powershell
azd auth login
azd up
```

All services (eep, iep1-iep8) deploy as Azure Container Apps as defined in `azure.yaml`.

## CI

GitHub Actions (`.github/workflows/ci.yml`) runs on every push:

1. Lint and test
2. Build Docker images for all services

## Route Logic

`src/route_complaint.py` is the runtime entry point. At startup it loads:
- `data/knowledge_base/municipalities/municipality_aliases.csv`
- `data/knowledge_base/municipalities/municipality_service_mappings.csv`
- `data/knowledge_base/municipalities/national_municipality_registry.csv`
- `data/knowledge_base/arabizi_vocabulary.json`

### IEP-3 and `route_complaint.py`

IEP-3 does **not** duplicate routing logic. Its worker imports the canonical,
source-backed router from `src/route_complaint.py` (`kb_route`) and wraps it with
`_route_with_kb()`: the knowledge-base route is *promoted* over the legacy
sector→agency map only for vetted sectors (`_KB_PROMOTION_SECTORS`), and falls
back to the legacy decision when the KB router is uncertain or errors. This keeps
a single source of truth for entity mappings while letting IEP-3 add calibration,
priority scoring, and HITL gating on top.

### IEP-8 — Grounded Resolution Co-Pilot

IEP-8 is the trust-critical answer to "what should actually happen about this
complaint?" — without hallucinating. After a complaint is routed, IEP-8:

1. **Retrieves** the most relevant *verified* facts from the entity KB using
   TF-IDF (`src/iep8/retriever.py`).
2. **Synthesises** an extractive plan where every step carries `[fact_id · source]`
   citations it was built from.
3. **Verifies** each step via a conservative lexical entailment proxy
   (`support_score`). Hallucinated steps — claims not in retrieved evidence — are
   dropped before any plan is issued.
4. **Detects conflicts**: when two facts of the same sensitive type (contact
   hotline, SLA, emergency instruction) carry irreconcilable values, IEP-8 flags
   the contradiction and defers to a human rather than advising arbitrarily.
5. **Diagnoses gaps**: every abstention emits a structured `EvidenceGap` naming
   the missing fact types and uncovered query terms. `GET /gaps` aggregates these
   into a **citizen-impact-ranked acquisition backlog** — a self-maintaining
   roadmap for growing the KB moat.
6. **Decides with calibrated confidence**: issues a plan (with `plan_confidence`
   and `ops_brief` for the reviewer) only when verified groundedness ≥ 0.80.
   For life-safety sectors, no-KB-coverage, low groundedness, or irreconcilable
   evidence it **abstains** and forces human review — never weakening the HITL spine.

**Guaranteed, not claimed**: `test_iep8_grounding_benchmark.py` over the 14-case
`resolution_grounding_eval_v1.jsonl` fixture proves **zero hallucinated citations**
across every case. Try it live: `POST http://127.0.0.1:8008/resolve`.

## Demo Seeding

To populate the incident-lifecycle timeline (IEP-5) and calibration snapshots
(IEP-7) for a live demo without standing up the full async stack:

```powershell
$env:PYTHONUTF8=1
.\.venv\Scripts\python.exe scripts/seed_demo_pipeline.py
```

This writes a small set of complaints, incidents (including a reopen →
retraining candidate), and routing outcomes into the configured database so
`GET /incidents/{id}/timeline` and `GET /calibration/latest` return real data.

## Civic Intelligence Compiler Demo

To show the strongest AI story in one artifact:

```powershell
.\.venv\Scripts\python.exe scripts/demo_civic_compiler.py
```

The script compiles IEP-1/2/3/4/5/6/7/8 signals into a proof-carrying incident
program: belief state, evidence atoms, proof obligations, counterfactual routes,
active-sensing questions, and the final autonomy decision.

## Recent Hardening (Round-2 — 2026-06-01)

Summary of the most recent safety, multilingual, KB, and active-learning hardening
work done in this repo.

- **Safety / Routing**: Added a FLOODING HITL gate and targeted FLOODING
   regexes to ensure life-safety cases (indoor emergency / immediate danger)
   escalate to human review and civil-defence workflows rather than being auto-routed.
- **IEP-1 (Multilingual)**: Rewrote the sector/issue classifier into a
   multilingual cascade: Arabic/Arabizi keyword scoring + optional embedding-based
   fall-back (toggle with `CEDARFIX_IEP1_USE_MULTILINGUAL=1`). This fixes near-
   zero recall on Arabic-script inputs from the prior char-gram-only model.
- **IEP-8 (Grounding)**: TF-IDF retriever now applies Arabic/Arabizi
   normalization and tokenization so KB evidence is returned for Arabic queries.
- **Active learning**: EEP exposes a feedback endpoint and persists
   `RetrainingCandidate` records so human corrections seed a retraining queue.
- **KB hygiene**: Municipality CSVs received backfills (registry IDs added)
   and expansions to channel/workflow rows to improve routing completeness.
- **Evals & tests**: Added/expanded eval fixtures (flooding, Arabic multilingual,
   image fusion, grounding) and updated tests. Current validated test run:
   **143 passed, 12 skipped, 0 failures**.

Next actions: per-IEP README files were added under `src/iep*/README.md` to
explain purpose, inputs/outputs, env toggles, and test commands; consider
adding a retraining consumer to automate model updates from the retraining queue.
