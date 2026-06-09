# CedarFix AI

CedarFix AI is a multimodal public-infrastructure complaint intelligence system for Lebanon. Citizens submit a text complaint, an optional image, and an optional location. The system validates the complaint, understands the text and image, checks whether both modalities match, detects duplicates, scores operational priority, routes the issue to the responsible authority, and keeps audit/monitoring data for human review and model improvement.

The project is built as a microservice pipeline around Intelligence Engine Processors (IEPs). The gateway is the external entry point and orchestrates every stage from moderation to explanation and review.

## Goals

- Accept infrastructure complaints from citizens through a web UI and API.
- Support multilingual complaint text and image-based evidence.
- Use specialized AI stages instead of a single monolithic model call.
- Prevent unsafe automation by sending uncertain, contradictory, low-confidence, or unsupported cases to human review.
- Route complaints using a seeded Lebanese public-sector RAG knowledge base.
- Keep observability, model audit, evaluation, and retraining hooks available for MLOps.

## Supported Languages

### Complaint Input Languages

- English
- Arabic
- French
- Arabizi, Arabic written with Latin characters and number substitutes. This is supported in the backend text pipeline through heuristic detection plus LLM-assisted translation/extraction.

Language detection is implemented in `services/text_understanding/app/language_detector.py`, where Arabizi is checked before standard library language detection. Text extraction normalizes multilingual input and embeds the English translation or normalized text in `services/text_understanding/app/model.py`. For Arabizi, `services/text_understanding/app/llm_extractor.py` first attempts GPT-4o translation when `OPENAI_API_KEY` is configured, then uses the configured Qwen/OpenAI-compatible extractor; without those provider keys, the service falls back to rule-based extraction and quality is more limited.

### Project Languages And Formats

- Python for FastAPI services, AI logic, scripts, tests, and shared schemas. The Docker images use Python 3.11.
- HTML, CSS, and JavaScript for the static frontend.
- SQL for Postgres schema initialization and migrations.
- YAML for Docker Compose, Kubernetes, Prometheus, Grafana, and deployment manifests.
- JSON and JSONL for RAG data, routing knowledge, dashboards, and evaluation artifacts.

## Project Structure

```text
CedarFix-AI/
+-- docker-compose.yml                  # Local multi-service stack
+-- docker/                             # Shared Dockerfiles and grouped service runner
+-- infra/
|   +-- postgres/                       # Local DB init and migrations
|   +-- prometheus/                     # Prometheus scrape config
|   +-- grafana/                        # Dashboard provisioning and dashboards
+-- k8s/                                # Local Kubernetes profile
+-- k8s-gcp/                            # GCP/GKE deployment profile
+-- RAG Data/                           # Routing RAG corpus and municipality lookup data
+-- scripts/                            # RAG compilation, validation, seeding, and local utility scripts
+-- services/
|   +-- frontend/                       # Static citizen/admin UI served by nginx
|   +-- gateway/                        # External API, auth, orchestration, media validation
|   +-- text_understanding/             # IEP-1 multilingual text extraction
|   +-- image_understanding/            # IEP-2 CLIP/VLM image understanding
|   +-- embedding_service/              # IEP-3 multimodal embeddings and retrieval
|   +-- clustering_service/             # IEP-4 duplicate detection and clustering
|   +-- priority_engine/                # IEP-5 severity and priority scoring
|   +-- routing_engine/                 # IEP-6 Qdrant RAG routing
|   +-- explanation_service/            # IEP-7 user/admin explanation generation
|   +-- review_service/                 # IEP-8 human review and retraining queue
|   +-- monitoring_service/             # IEP-9 drift, evaluation, monitoring endpoints
+-- shared/                             # Shared Pydantic schemas, DB, metrics, storage, Qdrant helpers
+-- tests/                              # Unit, contract, and opt-in live integration tests
+-- final_system.md                     # Detailed architecture and pipeline documentation
+-- .env.example                        # Runtime environment variable template
```

## Pipeline Overview

1. `frontend` collects the complaint text, image, user login, and location.
2. `gateway` receives `/complaints`, saves media, normalizes location, splits multi-complaint text, and starts the background pipeline.
3. IEP-0 moderation flags or rejects suspicious and unsafe submissions before the expensive AI stages.
4. IEP-1 text understanding and IEP-2 image understanding run in parallel.
5. The media validation gate checks whether text and image support, contradict, or fail to clarify each other.
6. IEP-3 creates MPNet/CLIP embeddings and retrieves similar complaints from Qdrant.
7. IEP-4 detects duplicates and assigns clusters.
8. IEP-5 scores severity and priority.
9. IEP-6 routes with Qdrant RAG and a Qwen routing judge when enabled.
10. IEP-7 creates the final explanation.
11. IEP-8 queues human review when automation is unsafe.
12. IEP-9 observability runs alongside the request path: instrumented services expose metrics and audit logs, while the optional monitoring profile exposes drift reports, retraining hooks, and GPT-4o evaluation.

The detailed design is in `final_system.md`; the executable orchestration is in `services/gateway/app/orchestrator.py`.

## Runtime Services

| Service | Port | Purpose |
| --- | ---: | --- |
| `frontend` | 80 | Citizen, tracking, login, admin, and review UI |
| `api-service` / gateway | 8000 | External API, auth, uploads, orchestration |
| `priority-engine` | 8005 | Priority and severity scoring, grouped inside `api-service` |
| `explanation-service` | 8007 | Decision explanation, grouped inside `api-service` |
| `review-service` | 8008 | Human review and retraining, grouped inside `api-service` |
| `text-understanding` | 8001 | Multilingual text extraction, grouped inside `ai-service` |
| `embedding-service` | 8003 | Text/image embedding, Qdrant retrieval, alignment |
| `clustering-service` | 8004 | Duplicate detection and clustering |
| `routing-engine` | 8006 | RAG routing to Lebanese authorities |
| `vision-service` | 8002 | Image quality, CLIP, VLM image understanding |
| `postgres` | 5432 | Local relational database |
| `qdrant` | 6333/6334 | Local vector database |
| `mlflow` | 5000 | Optional audit/experiment tracking profile |
| `prometheus` | 9090 | Optional metrics profile |
| `grafana` | 3000 | Optional dashboards profile |
| `monitoring-service` | 8009 | Optional drift and evaluation profile |

In the default Docker Compose stack, `api-service` runs the gateway, priority, explanation, and review FastAPI apps through `docker/run_group.py`. `ai-service` runs text understanding, embedding, clustering, and routing the same way. The exposed ports still map to the individual app endpoints listed above.

## Environment Variables

Create a local `.env` before running:

```powershell
Copy-Item .env.example .env
```

Then edit `.env` with your own provider keys and endpoints. Real `.env` files are ignored by Git.

### Important For A Useful Local Run

| Variable | Used By | Notes |
| --- | --- | --- |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` | `postgres` | Local database credentials used by Docker Compose. |
| `DATABASE_URL` | API, AI, monitoring, seed scripts | Docker Compose hardcodes container database URLs to the `postgres` service. Use a `localhost` URL when running host-side scripts. |
| `JWT_SECRET_KEY` | `services/gateway/app/auth.py` | Required for login/session tokens. Replace in production. |
| `QWEN_BASE_URL`, `QWEN_MODEL`, `QWEN_API_KEY` | text, splitter, routing, duplicate judge | OpenAI-compatible Qwen endpoint. Defaults can point to a local/hosted endpoint. |
| `VLM_BASE_URL`, `VLM_MODEL`, `VLM_API_KEY` | image understanding | OpenAI-compatible VLM endpoint. If unset, image service uses CLIP-only image understanding. |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | Arabizi translation, text fallback, VLM-path image fallback, evaluation | Optional for minimal local testing, important for full fallback behavior. GPT-4o vision fallback is attempted only after the configured VLM image path fails. |
| `QDRANT_HOST`, `QDRANT_PORT`, `QDRANT_URL`, `QDRANT_API_KEY` | embeddings, routing, seed scripts | Use host/port for local Qdrant; use URL/API key for Qdrant Cloud. |
| `STORAGE_BACKEND`, `GCS_BUCKET`, `UPLOADS_DIR` | gateway, image service, audit | `local` uses Docker volume; `gcs` requires a bucket and cloud credentials. |
| `GOOGLE_MAPS_API_KEY` | location normalization | Optional; seed/fuzzy lookup still works without it. |

### Common Tuning And MLOps Keys

| Variable | Purpose |
| --- | --- |
| `ROUTING_RAG_ENABLED`, `ROUTING_RAG_TOP_K`, `ROUTING_QDRANT_COLLECTION` | RAG retrieval behavior for IEP-6 routing. |
| `AUTO_ROUTE_THRESHOLD`, `REVIEW_THRESHOLD` | Confidence gates for auto-routing versus human review. |
| `AUGMENT_TEXT_EMBEDDING_WITH_IMAGE_CAPTION`, `STORE_IMAGE_CANDIDATE_EMBEDDINGS` | IEP-3 embedding augmentation and image-candidate storage behavior. |
| Duplicate thresholds | Current IEP-4 duplicate thresholds are hardcoded in `services/clustering_service/app/decision.py`: `0.92` for duplicates and `0.72` for related same-cluster decisions. |
| `MEDIA_ALIGNMENT_*` | LLM-based text/image alignment override settings. |
| `MULTI_COMPLAINT_SPLITTER_*` | Multi-complaint splitting behavior. |
| `ROUTING_KNOWLEDGE_DOCS`, `MUNICIPALITY_LOOKUP_DOCS` | Optional host-side seed script inputs for routing and municipality lookup data. |
| `LLM_AUDIT_*`, `MLFLOW_TRACKING_URI` | LLM request/response audit and MLflow metadata. |
| `PROMETHEUS_URL`, `EVALUATION_*` | Monitoring service and offline GPT-4o judge evaluation. |
| `GRAFANA_USER`, `GRAFANA_PASSWORD` | Local Grafana login when the monitoring profile is enabled. |

Docker Compose hardcodes some container-internal values, such as Postgres and Qdrant service hostnames, and also hardcodes several local thresholds. Its `.env` interpolation mainly covers provider keys, storage, media-alignment settings, splitter settings, Qdrant Cloud credentials, Grafana credentials, and evaluation settings. For local threshold changes, edit `docker-compose.yml`; for Kubernetes deployments, edit the relevant ConfigMap. See `.env.example`, `docker-compose.yml`, `k8s/configmap.yaml`, `k8s/secrets.example.yaml`, `k8s-gcp/configmap.yaml`, and `k8s-gcp/secrets.example.yaml` for the canonical runtime configuration sources.

## Run Locally With Docker Compose

Prerequisites:

- Docker Desktop or Docker Engine with Docker Compose.
- Enough disk space for Python packages and local Hugging Face model cache.
- Provider endpoints/keys in `.env` for full LLM and VLM behavior.

Start the default stack:

```powershell
cd CedarFix-AI
Copy-Item .env.example .env
docker compose up --build
```

Open:

- Frontend: `http://localhost/`
- Gateway API docs: `http://localhost:8000/docs`
- Gateway health: `http://localhost:8000/health`
- Qdrant API: `http://localhost:6333` (`/dashboard` is available when the Qdrant image serves its web UI)

Start with monitoring, MLflow, Prometheus, Grafana, and monitoring service:

```powershell
docker compose --profile monitoring up --build
```

Monitoring URLs:

- MLflow: `http://localhost:5000`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`
- Monitoring service: `http://localhost:8009/health`

## Seed Routing Knowledge

The Docker stack starts Qdrant and Postgres, but the routing RAG collection must be seeded for production-like routing.

From the repository root, after the database and Qdrant are running, use a Python environment with `psycopg2-binary`, `qdrant-client`, and `sentence-transformers` installed:

```powershell
$env:DATABASE_URL="postgresql://cedarfix:cedarfix_secret@localhost:5432/cedarfix"
$env:QDRANT_HOST="localhost"
$env:QDRANT_PORT="6333"
$env:ROUTING_KNOWLEDGE_DOCS="RAG Data/compiled/routing_knowledge_compiled_production.json"
python scripts\seed_routing_knowledge.py
```

To regenerate and validate the RAG corpus before seeding:

```powershell
python scripts\compile_routing_knowledge.py
python scripts\validate_routing_knowledge.py
```

More details are in `RAG Data/README.md`.

## Run Tests

Install test requirements in a Python environment:

```powershell
python -m pip install -r tests\requirements.txt
```

Run fast unit and contract tests:

```powershell
python -m pytest tests -m "unit or contract" -q
```

Run with coverage:

```powershell
python -m pytest tests -m "unit or contract" --cov=services --cov=cedarfix_shared --cov-branch
```

Run opt-in live integration tests:

```powershell
$env:CEDARFIX_RUN_QDRANT_TESTS="true"
$env:CEDARFIX_QDRANT_URL="http://127.0.0.1:6333"
$env:CEDARFIX_RUN_DB_TESTS="true"
$env:CEDARFIX_DATABASE_URL="postgresql://cedarfix:cedarfix_secret@127.0.0.1:5432/cedarfix"
$env:CEDARFIX_RUN_LOCAL_HEALTH_CHECKS="true"
python -m pytest tests/integration -q -rs
```

The test structure and readiness gates are documented in `tests/README.md` and `tests/integration/README.md`.

## Deployment

Local Kubernetes manifests live in `k8s/`. GCP/GKE manifests live in `k8s-gcp/`.

Live GCP URLs:

- App: `http://8.233.150.116/`
- MLflow: `http://136.112.186.183/`

Deployment-specific configuration is split between:

- ConfigMaps: non-secret runtime settings, service URLs, thresholds, model names, collection names.
- Secrets: `DATABASE_URL`, `JWT_SECRET_KEY`, `OPENAI_API_KEY`, `QWEN_API_KEY`, `VLM_API_KEY`, `QDRANT_API_KEY`, and other credentials.
- Infrastructure manifests: Postgres/Qdrant local manifests, Cloud SQL proxy/GCS/Qdrant Cloud settings for GCP, Prometheus, Grafana, MLflow, ingress, managed certificates, and service accounts.

Read `k8s/README.md` and `k8s-gcp/README.md` before deploying.

## Key API Paths

- `POST /auth/register` and `POST /auth/login`: user authentication.
- `POST /complaints`: submit text, location, and optional image.
- `GET /complaints/{complaint_id}`: fetch a complaint decision.
- `GET /my-complaints`: authenticated user complaint history.
- `GET /admin/stats`, `/admin/complaints`, `/admin/review-queue`, `/admin/review-resolved`, `/admin/duplicates`: admin dashboards and review workflows.
- `POST /admin/review/{item_id}/resolve`: resolve human review items.
- `GET /admin/retraining`, `/admin/retraining/{complaint_id}`, `/admin/retraining/export`: review and export retraining records.
- `GET /media?ref=...`: read local or GCS-backed media.
- `/metrics`: Prometheus metrics on most FastAPI services.
- `/health`: service health checks.

## Rubric Traceability

This section maps each rubric heading to the parts of the project where it is implemented or documented. It intentionally does not assign grades.

### AI Technical Complexity And Execution

- AI depth and non-triviality: the full IEP pipeline is documented in `final_system.md` and implemented through `services/gateway/app/orchestrator.py`.
- IEP-1 independence and value: multilingual text understanding lives in `services/text_understanding/`, with language detection, LLM extraction, translation/fallback behavior, and MPNet embeddings.
- IEP-2 independence and value: image understanding lives in `services/image_understanding/`, with image quality checks, CLIP embeddings, VLM analysis, visual candidates, and GPT-4o fallback inside the configured VLM path.
- EEP/gateway orchestration logic: request intake, auth, uploads, media validation, background processing, service calls, and final decision assembly live in `services/gateway/app/main.py` and `services/gateway/app/orchestrator.py`.
- Tradeoff evidence: fallback design, confidence thresholds, human-review gates, RAG/no-candidate behavior, and route safety rules are documented in `final_system.md` and implemented in `services/gateway/app/orchestrator.py`, `services/routing_engine/app/router.py`, and `services/clustering_service/app/decision.py`.
- Execution quality and edge cases: contradiction handling, vague text with image, multi-issue image handling, location-aware duplicate logic, RAG no-match review, and low-confidence review paths are covered in gateway/routing/clustering code and tests under `tests/unit/`.

### Software Methodology

- Service boundaries and contracts: service folders under `services/`, grouped Docker images in `docker-compose.yml`, and shared Pydantic contracts in `shared/cedarfix_shared/schemas.py`.
- Validation and request constraints: FastAPI/Pydantic models in service `main.py` files, schema field constraints in `shared/cedarfix_shared/schemas.py`, and contract tests in `tests/contract/`.
- Error handling, timeouts, retries, fallbacks: gateway HTTP timeout/error metrics in `services/gateway/app/orchestrator.py`, LLM/VLM fallbacks in `services/text_understanding/app/llm_extractor.py` and `services/image_understanding/app/analyzer.py`, and routing fallback/review paths in `services/routing_engine/app/router.py`.
- Containerization and orchestration: `docker-compose.yml`, `docker/*.Dockerfile`, service Dockerfiles, and `docker/run_group.py`.
- Deployment architecture and secrets: `k8s/`, `k8s-gcp/`, `k8s*/configmap.yaml`, and `k8s*/secrets.example.yaml`.

### Application / Research Positioning

- Problem/research question clarity: system purpose, target users, and pipeline boundaries are described in `final_system.md` and the `Goals` section above.
- Baseline/benchmark rigor: offline judge evaluation is implemented in `services/monitoring_service/app/evaluation_judge.py`; deterministic unit/contract tests live in `tests/`; synthetic data generation lives in `scripts/seed_data.py`.
- AI contribution justification: multimodal extraction, media validation, duplicate detection, RAG routing, confidence gating, and human-review/active-learning loops are documented in `final_system.md` and implemented across the IEP service folders.
- Value or publishability: the project targets a concrete Lebanese public-infrastructure complaint workflow with auditable routing, operational dashboards, and retraining data export in `services/review_service/` and `services/gateway/app/database.py`.

### Creativity & Innovation

- Originality: CedarFix combines citizen complaint intake, multimodal understanding, authority routing, duplicate clustering, human review, and active-learning storage for a Lebanon-specific infrastructure workflow.
- Insightful design choices: the system separates text, image, embedding, duplicate, priority, routing, explanation, review, and monitoring into independent services; uses RAG to avoid invented authorities; and keeps human review as a safety boundary when confidence is low.

### Quality Assurance

- Test suite breadth: unit tests cover routing, gateway orchestration, media validation, embedding alignment, priority, clustering, and helper behavior in `tests/unit/`.
- Regression/validation strategy: contract tests validate shared schemas, RAG data, infrastructure manifests, and dependency boundaries in `tests/contract/`; live readiness probes are opt-in under `tests/integration/`.

### GitHub Repository

- Commit history and ownership: this depends on the GitHub repository history rather than source files. The project is organized for clear ownership through service-level modules and IEP comments.
- Branching, review, traceability: PR/branch history is tracked in GitHub. In-source traceability is supported by service names, IEP numbering, tests, deployment manifests, and the rubric/documentation mapping in this README.

### MLOps / Observability / Documentation

- Automated lifecycle hooks: scheduled evaluation, hourly drift metric refresh, manual retraining trigger hooks, review queues, and retraining exports live in `services/monitoring_service/`, `services/review_service/`, and the gateway admin/retraining endpoints. The current retraining trigger logs a placeholder MLflow run; reviewed-data export is implemented, while the full model training loop is still a hook.
- Experiment tracking and runtime thresholds: MLflow helper utilities and LLM audit logging live in `shared/cedarfix_shared/mlflow_utils.py` and `shared/cedarfix_shared/llm_audit.py`. Configurable thresholds live in `.env.example`, `docker-compose.yml`, and Kubernetes ConfigMaps, while hardcoded IEP-4 duplicate thresholds are noted above.
- Monitoring and ML-specific signals: Prometheus metrics are defined in `shared/cedarfix_shared/metrics.py`, mounted through `/metrics` on the instrumented FastAPI services, and visualized by Grafana dashboards in `infra/grafana/dashboards/` and `k8s-gcp/grafana/dashboards/`. Current drift logic reports routing/correction-rate proxies and keeps `embedding_drift` as a placeholder value.
- Documentation completeness: root README, `final_system.md`, `RAG Data/README.md`, `tests/README.md`, `k8s/README.md`, and `k8s-gcp/README.md`.
