# CedarFix — AI-Powered Municipal Complaint Intelligence

Lebanon-specific multilingual municipal incident intelligence.

CedarFix converts fragmented citizen reports in Arabic, English, French,
Arabizi, and mixed language into validated, deduplicated, prioritized, and
explainable infrastructure incidents for municipal operations.

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
  -> IEP-4 — citizen-facing explanation and HITL audit narrative
```

## Current State

| Area | Status | Notes |
| --- | --- | --- |
| EEP | ✅ Built | FastAPI intake, request validation, PII scrub, Redis fallback, Dockerfile |
| IEP-1 | ✅ Built | Arabizi tokenization/normalization, sector/issue classification, v14 vocab |
| IEP-2 | ✅ Built | Similarity-hashing deduplication service, worker, Dockerfile |
| IEP-3 | ✅ Built | Municipality/entity routing service, router, worker, Dockerfile |
| IEP-4 | ✅ Built | Explainer service, citizen narrative generation, worker, Dockerfile |
| Monitoring | ✅ Configured | Prometheus scrape config + Grafana dashboard provisioning in `infra/` |
| Deployment | ✅ Configured | `azure.yaml` maps all services to Azure Container Apps via `azd` |
| Knowledge base | ✅ Complete | 1107 municipalities, 63 complaint types, 69 routing rules, 5772-term language bank |
| Training data | ✅ Ready | v29 batch8 train (75,555) + val (8,997), senzi sets, telecom batch |

## Repository Layout

```text
.github/workflows/         CI pipeline (lint, test, Docker build)
azure.yaml                 Azure Developer CLI deployment config (eep + iep1-4 → Container Apps)
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
  shared/                  Common schemas, arabizi_features, arabizi_lexical_policy

data/
  knowledge_base/
    arabizi_vocabulary.json          Runtime arabizi lexicon (v14, 3.29 MB, 31k+ terms)
    arabizi/                         NLP support — master index, hard negatives, OOV queue, stoplist
    municipalities/                  Municipality runtime data (registry, aliases, mappings, unions)
    entities/                        Lebanese public entity definitions (MEW, EDL, OGERO, CDR, …)
    cedarfix_language_bank.csv       5,772 approved arabizi terms with sector/issue hints
    complaint_taxonomy.csv           63 complaint types with routing defaults and HITL flags
    routing_rules.csv                69 routing rules keyed to complaint_type_id
    remediation_workflows.csv        59 resolution workflows with SLA policies
    cedarfix_complaint_scenario_inventory.csv  165 complaint scenarios with failure modes
    [+ 7 more reference CSVs/JSONs]
  complaint_intelligence/
    municipality_research_tracker.csv   800-municipality research tracker (merged)
    municipality_source_research.csv    12 source research records (merged)
    discovered_complaint_leads.csv      156 complaint leads
    normalized/municipal_official_process_seed.jsonl  78 seed CIE events
    [+ scaleout findings, source targets, schema, news policy]
  review_queue/            5 human review queues from legacy 100k complaint corpus
  training/                10 JSONL training files (v29 batch7/8, senzi, telecom)
```

## Knowledge Base

| File | Rows | Purpose |
| --- | ---: | --- |
| `municipalities/national_municipality_registry.csv` | 1,107 | Canonical municipality master |
| `municipalities/municipality_aliases.csv` | 3,829 | Name variant → canonical ID lookup |
| `municipalities/municipality_service_mappings.csv` | 1,094 | Municipality → service area mappings (runtime) |
| `municipalities/municipality_unions.csv` | 59 | Federation definitions |
| `municipalities/municipality_official_channels.csv` | 46 | Contact channels |
| `municipalities/municipality_complaint_workflows.csv` | 16 | Seed resolution workflows |
| `cedarfix_language_bank.csv` | 5,772 | Approved arabizi terms |
| `cedarfix_language_bank_review_queue.csv` | 7,298 | Candidate terms pending review |
| `complaint_taxonomy.csv` | 63 | Complaint type definitions |
| `routing_rules.csv` | 69 | Complaint → entity routing rules |
| `remediation_workflows.csv` | 59 | End-to-end resolution workflows |
| `arabizi/lebanese_arabizi_master_index.csv` | 31,032 | Full arabizi variant index |

## Training Data

| File | Examples | Purpose |
| --- | ---: | --- |
| `cidarfix_v29_batch8_train_v14_enriched.jsonl` | 75,555 | IEP-1 fine-tuning (v14 enriched) |
| `cidarfix_v29_batch8_val_v14_enriched.jsonl` | 8,997 | Validation |
| `cidarfix_v29_batch7_model_final_test_locked.jsonl` | 7,940 | Locked final test set (do not train on) |
| `senzi_hard_negatives_{train,val,test}.jsonl` | — | Contrastive boundary sharpening |
| `senzi_real_world_{train,val}.jsonl` | — | Domain adaptation from live reports |
| `telecom_batch2_{train,val}.jsonl` | — | Telecom sector (CDR, OGERO) |

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

All five services (eep, iep1-iep4) deploy as Azure Container Apps as defined in `azure.yaml`.

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
