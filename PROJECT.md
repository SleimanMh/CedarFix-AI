# CedarFix AI — Complete Project Documentation

## Table of Contents
1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Infrastructure Services](#3-infrastructure-services)
4. [AI Pipeline — IEP by IEP](#4-ai-pipeline--iep-by-iep)
5. [Shared Library](#5-shared-library)
6. [Frontend](#6-frontend)
7. [Data Flow — Step by Step](#7-data-flow--step-by-step)
8. [Database Schema](#8-database-schema)
9. [Complaint Types & Routing Rules](#9-complaint-types--routing-rules)
10. [Media Validation Gate](#10-media-validation-gate)
11. [Text-Image Alignment (MODAL_CONFLICT Detection)](#11-text-image-alignment-modal_conflict-detection)
12. [Monitoring & MLOps](#12-monitoring--mlops)
13. [Environment Variables](#13-environment-variables)
14. [Running the Project](#14-running-the-project)
15. [Known Constraints & TODOs](#15-known-constraints--todos)

---

## 1. Project Overview

**CedarFix AI** is a Lebanese public infrastructure complaint platform. Citizens submit a text description — optionally with a photo — and an AI pipeline automatically:

1. Understands the complaint language (Arabic, French, English, Arabizi)
2. Classifies the issue type (pothole, flooding, electricity outage, etc.)
3. Analyzes any attached image using computer vision
4. Detects whether the text and image are consistent with each other
5. Groups the complaint with similar existing reports (duplicate detection)
6. Assigns a priority score based on severity, cluster size, and location risk
7. Routes the complaint to the correct Lebanese government entity
8. Generates a human-readable explanation of the decision
9. Flags low-confidence or contradictory submissions for human review

The entire pipeline runs fully automatically. Human reviewers only touch edge cases.

---

## 2. System Architecture

```
Browser (port 80)
    └── nginx (cedarfix-frontend)
           ├── /             → Static HTML/CSS/JS
           ├── /api/         → proxy → Gateway :8000
           └── /review-api/  → proxy → Review Service :8008

Gateway :8000  (EEP — Entry/Exit Point)
    ├── POST /complaints      (multipart form: text + optional image)
    └── Orchestrates IEP-1 through IEP-8 in sequence

IEP-1  Text Understanding    :8001   (sentence-transformers + Qwen LLM)
IEP-2  Image Understanding   :8002   (CLIP zero-shot)
IEP-3  Embedding + Alignment :8003   (fusion + Qdrant storage + cosine alignment)
IEP-4  Clustering            :8004   (HDBSCAN + duplicate detection)
IEP-5  Priority Engine       :8005   (rule-based scorer)
IEP-6  Routing Engine        :8006   (rule-based router)
IEP-7  Explanation Service   :8007   (template/LLM)
IEP-8  Review Service        :8008   (human review queue + admin corrections)

Infrastructure:
    PostgreSQL  :5432   (persistent storage)
    Qdrant      :6333   (vector database)
    MLflow      :5000   (experiment tracking)
    Prometheus  :9090   (metrics)
    Grafana     :3000   (dashboards)
```

All services share a Docker bridge network named `cedarfix-net` and communicate by container name (e.g. `http://text-understanding:8001`).

---

## 3. Infrastructure Services

### PostgreSQL (`cedarfix-postgres`)
- Version: PostgreSQL 15 Alpine
- Credentials: user=`cedarfix`, password=`cedarfix_secret`, db=`cedarfix`
- Initialized at first start by `infra/postgres/init.sql`
- Holds all complaint records, clusters, admin corrections, and the human review queue
- Port: `5432`

### Qdrant (`cedarfix-qdrant`)
- A dedicated vector database for similarity search
- Stores 768-dim fused embeddings for every complaint
- Collection name: `complaints`
- Port: `6333` (HTTP), `6334` (gRPC)
- IEP-3 writes to it; IEP-3 and IEP-4 read from it

### MLflow (`cedarfix-mlflow`)
- Tracks model experiments and serves a model registry
- Backend store: PostgreSQL (`cedarfix` database)
- Used by IEP-5 (priority) and IEP-6 (routing) to load trained models when available
- Port: `5000`

### Prometheus (`cedarfix-prometheus`)
- Scrapes `/metrics` from all services every 15 seconds
- Config: `infra/prometheus/prometheus.yml`
- Port: `9090`

### Grafana (`cedarfix-grafana`)
- Pre-provisioned with three dashboards:
  - `01_pipeline_health.json` — latency and throughput per IEP stage
  - `02_ai_behavior.json` — complaint type distribution, confidence histograms
  - `03_drift_monitor.json` — routing accuracy, admin correction rate, embedding drift
- Port: `3000`, default login: `admin` / `cedarfix_grafana`

---

## 4. AI Pipeline — IEP by IEP

### EEP — Gateway (`services/gateway/`)
**Container:** `cedarfix-gateway` | **Port:** `8000`

The entry and exit point for every complaint.

**Endpoint:** `POST /complaints` (multipart form)
- `text` (required, 10–2000 chars)
- `image` (optional file)
- `latitude`, `longitude`, `address_hint`, `district`, `user_id` (all optional)

**Key files:**
- `app/main.py` — FastAPI app, saves uploaded image to `/data/uploads`, calls orchestrator, stores result to PostgreSQL
- `app/orchestrator.py` — orchestrates the full pipeline (see §7)
- `app/database.py` — async SQLAlchemy, saves `ComplaintDecision` JSON to `complaints` table
- `app/config.py` — reads service URLs from environment

**Timeout:** 60 seconds per HTTP call to any downstream service.

---

### IEP-1 — Text Understanding (`services/text_understanding/`)
**Container:** `cedarfix-text-understanding` | **Port:** `8001`

**Endpoint:** `POST /analyze`
- Input: `{ complaint_id, text }`
- Output: `TextUnderstandingResult` (see §5)

**What it does:**
1. Detects language: Arabic (`ar`), French (`fr`), English (`en`), Arabizi (`arabizi`)
2. Calls the LLM extractor (`llm_extractor.py`)
3. Encodes the English translation with `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` (768-dim)
4. Returns structured extraction including issue type, category, location, severity, signals, confidence

**LLM routing (`llm_extractor.py`):**
- Arabic/French/English → **Qwen2.5-3B-Instruct** on RunPod (OpenAI-compatible endpoint)
- Arabizi → **GPT-4o** for translation only, then Qwen for classification
- Falls back to rule-based `StructuredExtractor` if both LLMs are unavailable

**LLM system prompt** instructs the model to return structured JSON with:
- `issue_type` (one of the 13 known types)
- `category` (roads / drainage / electricity / water / sanitation / telecom / other / …)
- `severity` (LOW / MEDIUM / HIGH / CRITICAL)
- `location_mentions`, `keywords`, `summary`, `signals`, `confidence`

**Category validation:** The `_VALID_CATEGORIES` set in `llm_extractor.py` prevents the LLM from hallucinating non-standard categories (e.g., "traffic" instead of "roads"). If the LLM returns an invalid category, `_ISSUE_TO_CATEGORY` provides the correct fallback.

**Rule-based fallback (`extractor.py`):**
- `ISSUE_HIERARCHY` maps each `ComplaintType` to `(category, subcategory)`
- `ISSUE_KEYWORDS` maps each `ComplaintType` to a list of matching English keywords
- `_LOCATION_PATTERN` regex extracts Lebanese location names
- `DISTRICT_MAP` and `GOVERNORATE_MAP` normalize location names to official districts

**Model:** `paraphrase-multilingual-mpnet-base-v2` loaded from `./data/models` (HuggingFace cache volume). Takes ~5–10 seconds to load on startup.

---

### IEP-2 — Image Understanding (`services/image_understanding/`)
**Container:** `cedarfix-image-understanding` | **Port:** `8002`

**Endpoint:** `POST /analyze`
- Input: `{ complaint_id, image_filename? }` (filename in shared uploads volume)
- Output: `ImageUnderstandingResult`

**What it does:**
1. Loads the image from `/data/uploads/{image_filename}`
2. Checks image quality (minimum 128×128 pixels)
3. Runs CLIP zero-shot classification against infrastructure prompt bank
4. Scores severity using four CLIP severity prompts
5. Returns `VisualUnderstandingJSON`: `visual_category`, `visual_subcategory`, detected objects, caption, confidence

**Infrastructure CLIP prompts include:**
- Road damage / pothole, flooding, garbage, broken traffic light, cracked sidewalk, dark street lamp, leaking pipe, etc.

**Negative prompts** filter out unrelated images (selfies, food, landscapes).

**Model:** `openai/clip-vit-base-patch32` (512-dim embeddings) loaded from the same HuggingFace cache volume.

When no image is submitted, IEP-2 returns `{ image_present: false }` immediately without calling the model.

---

### IEP-3 — Embedding Service (`services/embedding_service/`)
**Container:** `cedarfix-embedding-service` | **Port:** `8003`

**Endpoint:** `POST /embed`
- Input: `{ complaint_id, text_result, image_result }`
- Output: `EmbeddingServiceResult`

**What it does:**
1. Takes the 768-dim text embedding from IEP-1 and the 512-dim CLIP image embedding from IEP-2
2. Projects the image embedding to 768-dim using a fixed random projection matrix (`fusion.py`)
3. Computes a weighted average fusion: `fused = (1-w) * text + w * image` where `w = 0.3 × image_relevance` (capped at 0.4)
4. Stores the fused embedding in Qdrant under the `complaints` collection
5. Retrieves the top-N most similar existing complaints by cosine similarity
6. Computes text-image alignment (`alignment.py`)

**Alignment computation (`alignment.py`):**
- **Primary path:** uses `clip_text_embedding` (CLIP encoding of the complaint text, returned by IEP-2) — cosine similarity against the image embedding is a semantically valid comparison since both live in the same 512-dim CLIP space
- **Fallback path:** if `clip_text_embedding` is absent, projects the image embedding into the 768-dim text space and computes cosine with the text embedding — scores are downscaled × 0.7 and capped at `UNCERTAIN`

**Alignment statuses:** `SUPPORTS`, `CONTRADICTS`, `UNRELATED`, `UNCERTAIN`, `NO_IMAGE`

**Reconciliation statuses:** `TEXT_AND_IMAGE_SUPPORT`, `IMAGE_OVERRIDES_WEAK_TEXT`, `TEXT_OVERRIDES_WEAK_IMAGE`, `MODAL_CONFLICT`, `INSUFFICIENT_EVIDENCE`

---

### IEP-4 — Clustering Service (`services/clustering_service/`)
**Container:** `cedarfix-clustering-service` | **Port:** `8004`

**Endpoint:** `POST /cluster`
- Input: `{ complaint_id, fused_embedding, complaint_type, … }`
- Output: `MultimodalClusteringResult`

**What it does:**
1. Queries Qdrant for the most similar existing complaints
2. Applies similarity thresholds:
   - `≥ 0.92` → `DUPLICATE`
   - `≥ 0.78` → `NEAR_DUPLICATE`
   - `< 0.78` → `NEW`
3. Assigns the complaint to an existing cluster (HDBSCAN) or creates a new one
4. Detects `escalation_signal = True` if the cluster is growing rapidly
5. Persists cluster data to PostgreSQL

**HDBSCAN parameters:** `min_cluster_size=5` (configurable via env)

---

### IEP-5 — Priority Engine (`services/priority_engine/`)
**Container:** `cedarfix-priority-engine` | **Port:** `8005`

**Endpoint:** `POST /score`
- Input: complaint type, cluster size, visual severity, location district, similarity score
- Output: `PriorityResult` with `priority_score` (0–1) and `SeverityLevel`

**Scoring formula:**
```
score = base_type_score
      + min(cluster_size × 0.05, 0.30)   ← recurring = more urgent
      + visual_severity_boost             ← CRITICAL=0.4, HIGH=0.3, MEDIUM=0.15
      + location_risk_boost               ← high-risk districts: Tripoli, Tyre, Sidon…
```
Normalized to [0, 1] then mapped to `LOW / MEDIUM / HIGH / CRITICAL`.

**Base type scores:** `flooding=0.8`, `electricity_outage=0.7`, `road_damage=0.6`, `pothole=0.5`, `traffic_light=0.6`, `water_pipe=0.65`, `telecom_outage=0.55`, `waste_accumulation=0.4`, `streetlight=0.45`, `sidewalk_damage=0.35`, `other=0.3`

---

### IEP-6 — Routing Engine (`services/routing_engine/`)
**Container:** `cedarfix-routing-engine` | **Port:** `8006`

**Endpoint:** `POST /route`
- Input: complaint type, severity, location info, keywords
- Output: `RoutingResult` with `primary_entity`, `secondary_entity`, confidences, rationale

**Routing table (`router.py`):**

| Complaint Type | Primary Entity | Secondary Entity | Confidence |
|---|---|---|---|
| pothole | Ministry of Public Works | Beirut Municipality | 0.88 |
| road_damage | Ministry of Public Works | Beirut Municipality | 0.88 |
| flooding | Ministry of Environment | Ministry of Public Works | 0.82 |
| water_pipe | Beirut Water Authority | Beirut Municipality | 0.90 |
| electricity_outage | Electricité Du Liban | — | 0.95 |
| telecom_outage | Ogero | — | 0.95 |
| streetlight | Electricité Du Liban | Beirut Municipality | 0.80 |
| traffic_light | Internal Security Forces | Beirut Municipality | 0.85 |
| traffic_incident | Internal Security Forces | Ministry of Public Works | 0.88 |
| waste_accumulation | Beirut Municipality | Ministry of Environment | 0.87 |
| sidewalk_damage | Beirut Municipality | Ministry of Public Works | 0.83 |
| public_safety | Internal Security Forces | Beirut Municipality | 0.82 |
| other | Human Review Queue | — | 0.40 |

**District override:** If the complaint location is outside Beirut (e.g. Tripoli, Sidon, Jounieh), the router replaces `Beirut Municipality` with the correct regional entity.

**Auto-route threshold:** `≥ 0.85` → auto-routed without human review
**Review threshold:** `< 0.65` → forced to Human Review Queue

---

### IEP-7 — Explanation Service (`services/explanation_service/`)
**Container:** `cedarfix-explanation-service` | **Port:** `8007`

**Endpoint:** `POST /explain`
- Input: complaint type, severity, assigned entity, confidence, urgency factors, is_duplicate flag
- Output: `ExplanationResult` with plain-English `explanation_text` and `key_factors`

**Modes:**
- `template` (default): fast, deterministic, no GPU required — constructs sentences from structured fields
- `llm` (stretch): routes to Qwen2.5-7B-Instruct for richer prose

**Example output:** *"This complaint has been classified as a traffic incident with HIGH severity. It has been routed to Internal Security Forces with high confidence. Priority factors: Cluster size 3 adds 0.15; High-risk district 'Tripoli'."*

---

### IEP-8 — Review Service (`services/review_service/`)
**Container:** `cedarfix-review-service` | **Port:** `8008`

**Endpoints:**
- `GET /health`
- `GET /queue?limit=20` — complaints pending routing review (low confidence)
- `POST /corrections/{complaint_id}` — admin submits a routing/severity/type correction
- `POST /human-review` — gateway queues a media validation failure
- `GET /human-review?limit=50` — admin lists pending human review items
- `POST /human-review/{id}/resolve` — admin resolves an item with notes

**Human review queue** catches:
- `NEEDS_CLARIFICATION`: image present but text doesn't describe a complaint
- `HUMAN_REVIEW`: ambiguous submission the pipeline cannot confidently process

**Admin corrections** table feeds back into retraining for IEP-5 and IEP-6 (active learning loop).

---

## 5. Shared Library

Located in `shared/cedarfix_shared/`. Installed as a Python package inside each container at `/usr/local/lib/python3.11/site-packages/cedarfix_shared/`.

> **Important:** When deploying schema changes manually, always copy to the **site-packages** path, not just the source tree path. Both containers read from site-packages at import time.

### `schemas.py` — Single Source of Truth for All Data Contracts

**Enumerations:**

| Enum | Values |
|---|---|
| `Language` | `ar`, `fr`, `en`, `arabizi`, `unknown` |
| `ComplaintType` | `pothole`, `traffic_light`, `flooding`, `waste_accumulation`, `electricity_outage`, `road_damage`, `water_pipe`, `sidewalk_damage`, `streetlight`, `telecom_outage`, `traffic_incident`, `public_safety`, `other` |
| `SeverityLevel` | `LOW`, `MEDIUM`, `HIGH`, `CRITICAL` |
| `PipelineStatus` | `pending`, `processing`, `completed`, `failed`, `review_required`, `needs_clarification`, `contradiction`, `invalid_no_complaint` |
| `AlignmentStatus` | `SUPPORTS`, `CONTRADICTS`, `UNRELATED`, `UNCERTAIN`, `NO_IMAGE` |
| `ReconciliationStatus` | `TEXT_AND_IMAGE_SUPPORT`, `IMAGE_OVERRIDES_WEAK_TEXT`, `TEXT_OVERRIDES_WEAK_IMAGE`, `MODAL_CONFLICT`, `INSUFFICIENT_EVIDENCE` |
| `RoutingEntity` | Ministry of Public Works, Beirut Municipality, Electricité Du Liban, Beirut Water Authority, Internal Security Forces, Ministry of Environment, North/South/Mount Lebanon Municipality, Ogero, Human Review Queue |

**Key output models:**
- `TextUnderstandingResult` — full NLP result from IEP-1
- `ImageUnderstandingResult` — CLIP vision result from IEP-2
- `EmbeddingServiceResult` — fused vector + alignment from IEP-3
- `MultimodalClusteringResult` — cluster assignment from IEP-4
- `PriorityResult` — priority score from IEP-5
- `RoutingResult` — routing decision from IEP-6
- `ExplanationResult` — human-readable explanation from IEP-7
- `ComplaintDecision` — the complete assembled result stored in PostgreSQL and returned to the caller
- `MediaValidationResult` — gate result after IEP-1 + IEP-2 (before IEP-3)
- `TextImageAlignment` — alignment detail from IEP-3 (embedded into `ComplaintDecision`)

### `db.py`
Async SQLAlchemy engine factory, shared by gateway and clustering service.

### `metrics.py`
Prometheus metric definitions shared across all services:
- `TEXT_ANALYSIS_DURATION`, `LANGUAGE_DISTRIBUTION`
- `PIPELINE_DURATION` (labelled by stage)
- `COMPLAINTS_TOTAL`

### `mlflow_utils.py`
Helpers for logging experiments and loading models from the MLflow model registry.

---

## 6. Frontend

**Container:** `cedarfix-frontend` | **Port:** `80`

nginx serves three static pages and proxies API calls.

### Pages

**`index.html` — Report Issue (main page)**
- Text area with character counter (10–2000 chars)
- Optional image upload with drag-and-drop preview
- Optional GPS coordinates + address hint
- Submits to `/api/complaints` (proxied to gateway)
- On success, shows a result panel including:
  - Status badge, assigned entity, severity, duplicate warning
  - **AI Analysis Details block**: image detection, confidence %, text/image alignment badge (✅ Confirms / ⚠️ Contradicts / 🔶 Partial / ❓ Unrelated), conflict reason

**`track.html` — Track Complaint**
- Lookup by complaint ID against `/api/complaints/{id}`
- Shows current status and pipeline decision

**`review.html` — Human Review Dashboard** (admin only)
- Fetches from `/review-api/human-review`
- Filters: "Needs Clarification" | "Human Review"
- Shows each item's original text, detected types (text vs image), review reason
- Resolve form: admin ID + resolution notes → `POST /review-api/human-review/{id}/resolve`

### nginx Configuration (`nginx.conf` → deployed to `/etc/nginx/conf.d/cedarfix.conf`)
```nginx
location /api/         { proxy_pass http://gateway:8000/; }
location /review-api/  { proxy_pass http://review-service:8008/; }
location /             { root /usr/share/nginx/html; try_files $uri /index.html; }
```

---

## 7. Data Flow — Step by Step

```
User submits POST /complaints (text + optional image)
  │
  ├─ Gateway saves image to /data/uploads/{id}_{filename}
  ├─ Assigns complaint_id (UUID)
  │
  ├─── Stage 1: Parallel ────────────────────────────────────────
  │     IEP-1: analyze text → issue_type, category, confidence,
  │             location, severity, signals, 768-dim embedding
  │     IEP-2: analyze image → visual_subcategory, CLIP embedding,
  │             image_relevance, image_quality, severity signal
  │
  ├─── Media Validation Gate ────────────────────────────────────
  │     • No text complaint + no image → INVALID_NO_COMPLAINT
  │     • Image present + text not complaint → NEEDS_CLARIFICATION
  │                                         → queued to IEP-8
  │     • Both low confidence → HUMAN_REVIEW → queued to IEP-8
  │     • Text/image type mismatch at category level → CONTRADICTION
  │     • All clear → continue
  │
  ├─── Stage 2: IEP-3 ───────────────────────────────────────────
  │     • Fuse text (768-dim) + image (512→768 projected) embeddings
  │     • Store fused vector in Qdrant
  │     • Retrieve top-k similar complaints
  │     • Compute text-image alignment (cosine similarity)
  │       If MODAL_CONFLICT + conflict_detected + image present → CONTRADICTION
  │
  ├─── Stage 3: IEP-4 ───────────────────────────────────────────
  │     • Duplicate detection (≥0.92 = duplicate, ≥0.78 = near-dup)
  │     • Cluster assignment (HDBSCAN)
  │     • Escalation signal if cluster growing fast
  │
  ├─── Stage 4: IEP-5 ───────────────────────────────────────────
  │     • Priority score: type base + cluster boost + visual boost
  │                        + location risk boost
  │     • Maps score → SeverityLevel
  │
  ├─── Stage 5: IEP-6 ───────────────────────────────────────────
  │     • TYPE_TO_ENTITY lookup → primary + secondary entity
  │     • District override for non-Beirut regions
  │     • Confidence < 0.65 → Human Review Queue
  │
  ├─── Stage 6: IEP-7 ───────────────────────────────────────────
  │     • Template-based explanation string + key_factors list
  │
  └─ Gateway assembles ComplaintDecision, saves to PostgreSQL,
     returns JSON response to caller
```

---

## 8. Database Schema

### `complaints` table
The primary storage table. Every field from every IEP stage is either stored as a dedicated column or rolled into `full_decision_json` (JSONB).

Key columns:
- `id` (VARCHAR 36, UUID) — primary key
- `status` — `pending | processing | completed | failed | review_required | needs_clarification | contradiction | invalid_no_complaint`
- `original_text` — raw user submission
- `complaint_type` — classified issue type
- `detected_language` — `ar / fr / en / arabizi`
- `severity`, `priority_score`, `assigned_entity`, `routing_confidence`
- `duplicate_status`, `duplicate_of`, `cluster_id`, `escalation_signal`
- `full_decision_json` (JSONB) — the complete `ComplaintDecision` object

Indexes on: `created_at`, `status`, `complaint_type`, `severity`, `assigned_entity`, `requires_review`

### `clusters` table
- Tracks active HDBSCAN clusters: `id`, `complaint_type`, `dominant_district`, `member_count`, `trend`, `last_run_at`

### `admin_corrections` table
- Stores human corrections: `complaint_id`, `admin_id`, `corrected_routing`, `corrected_severity`, `corrected_complaint_type`, `notes`, `applied_to_training`
- Used as gold-label training data for future ML models

### `human_review_queue` table
- Items flagged by the Media Validation Gate: `complaint_id`, `validation_status`, `review_reason`, `original_text`, `image_filename`, `text_detected_type`, `image_detected_type`, `resolved_at`, `resolved_by`, `resolution_notes`

---

## 9. Complaint Types & Routing Rules

### All Supported Complaint Types

| Issue Type | Category | Routed To | Confidence |
|---|---|---|---|
| `pothole` | roads | Ministry of Public Works | 0.88 |
| `road_damage` | roads | Ministry of Public Works | 0.88 |
| `flooding` | drainage | Ministry of Environment | 0.82 |
| `waste_accumulation` | sanitation | Beirut Municipality | 0.87 |
| `electricity_outage` | electricity | Electricité Du Liban | 0.95 |
| `telecom_outage` | telecom | Ogero | 0.95 |
| `traffic_light` | roads | Internal Security Forces | 0.85 |
| `streetlight` | electricity | Electricité Du Liban | 0.80 |
| `water_pipe` | water | Beirut Water Authority | 0.90 |
| `sidewalk_damage` | roads | Beirut Municipality | 0.83 |
| `traffic_incident` | roads | Internal Security Forces | 0.88 |
| `public_safety` | other | Internal Security Forces | 0.82 |
| `other` | other | Human Review Queue | 0.40 |

### Traffic Incident Keywords
"accident", "car accident", "road accident", "traffic accident", "crash", "collision", "vehicle crash", "car crash", "congestion", "traffic jam", "traffic block", "blocked road", "road blocked", "road closure", "road closed", "traffic incident", "traffic problem", "traffic issue", "heavy traffic"

### Public Safety Keywords
"unsafe", "dangerous structure", "falling debris", "risk to life", "public hazard", "structural collapse", "unsafe building", "falling wall", "dangerous building", "public safety", "safety hazard", "fire hazard", "open manhole", "exposed wire"

---

## 10. Media Validation Gate

Runs in the Gateway after IEP-1 and IEP-2 complete, before IEP-3 starts. Decides whether the submission can proceed.

**Logic (in `orchestrator.py → _validate_media`):**

| Condition | Status | Result |
|---|---|---|
| Neither text nor image describes a complaint | `INVALID_NO_COMPLAINT` | Rejected immediately |
| Image present but text does not describe complaint, image does | `NEEDS_CLARIFICATION` | Queued to human review; user asked to improve text |
| Both text and image present, but types are incompatible categories | `CONTRADICTION` | Rejected; user told the image doesn't match their text |
| Both present but both low confidence | `HUMAN_REVIEW` | Queued to human review |
| Text describes complaint, no image or image is consistent | `VALID` | Continue to IEP-3 |

---

## 11. Text-Image Alignment (MODAL_CONFLICT Detection)

A second contradiction check happens inside IEP-3 after embedding.

**In `orchestrator.py`:** After receiving `EmbeddingServiceResult`:
```
if alignment.conflict_detected
   AND alignment.reconciliation_status == "MODAL_CONFLICT"
   AND image was present
→ decision.status = CONTRADICTION
→ Return early (skip IEP-4 through IEP-7)
```

**In `alignment.py`:**
- Adjacent issue type pairs are considered tolerable (e.g. `pothole ↔ road_damage`, `flooding ↔ water_pipe`)
- Mismatches between different categories (e.g. text=pothole, image=garbage) trigger `CONTRADICTS` alignment and `MODAL_CONFLICT` reconciliation

**Contradiction message returned to the user:** *"Your text describes a {text_type} issue but your image appears to show something different ({image_type}). Please resubmit with a photo that matches your complaint."*

---

## 12. Monitoring & MLOps

### Prometheus Metrics (collected from all services)
- `text_analysis_duration_seconds` — IEP-1 latency histogram
- `language_distribution_total` — language breakdown counter
- `pipeline_duration_seconds{stage}` — per-stage latency
- `complaints_total` — total submissions

### Grafana Dashboards
1. **Pipeline Health** — p50/p95/p99 latency per stage, error rates, request throughput
2. **AI Behavior** — complaint type breakdown, routing distribution, severity histogram, confidence distribution
3. **Drift Monitor** — 7-day routing accuracy, admin correction rate, avg routing confidence, drift alert trigger (correction_rate > 15%)

### Drift Detection (`monitoring_service/app/drift.py`)
Runs periodically and reports:
- `routing_accuracy_7d` — fraction of last-7-day complaints not manually corrected
- `admin_correction_rate` — fraction corrected by admins
- `avg_routing_confidence_7d` — proxy for model health
- `drift_alert: true` if correction rate exceeds 15%

### Retraining (`monitoring_service/app/retrain.py`)
Watches for drift alerts and can trigger an MLflow training run using admin correction data as gold labels.

### MLflow Model Registry
- IEP-5 and IEP-6 check the MLflow model registry at startup
- If a trained model exists (`cedarfix-priority`, `cedarfix-routing`), it loads and uses it
- Otherwise it falls back to the rule-based implementation

---

## 13. Environment Variables

### Gateway
| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://cedarfix:cedarfix_secret@postgres:5432/cedarfix` | PostgreSQL connection |
| `TEXT_SERVICE_URL` | `http://text-understanding:8001` | IEP-1 URL |
| `IMAGE_SERVICE_URL` | `http://image-understanding:8002` | IEP-2 URL |
| `EMBEDDING_SERVICE_URL` | `http://embedding-service:8003` | IEP-3 URL |
| `CLUSTERING_SERVICE_URL` | `http://clustering-service:8004` | IEP-4 URL |
| `PRIORITY_SERVICE_URL` | `http://priority-engine:8005` | IEP-5 URL |
| `ROUTING_SERVICE_URL` | `http://routing-engine:8006` | IEP-6 URL |
| `EXPLANATION_SERVICE_URL` | `http://explanation-service:8007` | IEP-7 URL |
| `UPLOADS_DIR` | `/data/uploads` | Image upload directory |

### Text Understanding (IEP-1)
| Variable | Default | Description |
|---|---|---|
| `MODEL_NAME` | `sentence-transformers/paraphrase-multilingual-mpnet-base-v2` | HuggingFace model |
| `QWEN_BASE_URL` | RunPod endpoint | Qwen LLM base URL (OpenAI-compatible) |
| `QWEN_MODEL` | `Qwen/Qwen2.5-3B-Instruct` | Qwen model name |
| `QWEN_ENABLED` | `true` | Whether to use Qwen for classification |
| `OPENAI_API_KEY` | *(empty)* | GPT-4o key for Arabizi translation |

### Clustering (IEP-4)
| Variable | Default | Description |
|---|---|---|
| `SIMILARITY_DUPLICATE_THRESHOLD` | `0.92` | Score above which = duplicate |
| `SIMILARITY_NEAR_DUPLICATE_THRESHOLD` | `0.78` | Score above which = near-duplicate |
| `HDBSCAN_MIN_CLUSTER_SIZE` | `5` | Min cluster size for HDBSCAN |

### Routing (IEP-6)
| Variable | Default | Description |
|---|---|---|
| `AUTO_ROUTE_THRESHOLD` | `0.85` | Confidence above which = auto-routed |
| `REVIEW_THRESHOLD` | `0.65` | Confidence below which = forced to human review |

---

## 14. Running the Project

### Start all services
```bash
docker compose up -d
```

### Check all services are healthy
```bash
docker compose ps
curl http://localhost:8000/health   # Gateway
curl http://localhost:8001/health   # Text Understanding
curl http://localhost:8002/health   # Image Understanding
curl http://localhost:8003/health   # Embedding
curl http://localhost:8004/health   # Clustering
curl http://localhost:8005/health   # Priority
curl http://localhost:8006/health   # Routing
curl http://localhost:8007/health   # Explanation
curl http://localhost:8008/health   # Review
```

### Submit a complaint (text only)
```bash
curl -X POST http://localhost:8000/complaints \
  -F "text=There is a large pothole on the main road near Hamra, dangerous for cars."
```

### Submit a complaint with image
```bash
curl -X POST http://localhost:8000/complaints \
  -F "text=There is flooding on the road in Verdun" \
  -F "image=@/path/to/photo.jpg"
```

### Manually deploy a changed file to a running container
```powershell
# Always deploy schemas to BOTH locations:
docker cp shared\cedarfix_shared\schemas.py cedarfix-CONTAINER:/app/shared/cedarfix_shared/schemas.py
docker cp shared\cedarfix_shared\schemas.py cedarfix-CONTAINER:/usr/local/lib/python3.11/site-packages/cedarfix_shared/schemas.py
docker restart cedarfix-CONTAINER --timeout 5
```

### Access dashboards
- **Frontend (citizen UI):** http://localhost
- **Grafana monitoring:** http://localhost:3000 (admin / cedarfix_grafana)
- **MLflow:** http://localhost:5000
- **Prometheus:** http://localhost:9090

---

## 15. Known Constraints & TODOs

### Current Limitations
- **IEP-3 fallback alignment is mathematically unsound.** The random projection from CLIP 512-dim into sentence-transformer 768-dim space is not a semantically valid cross-model bridge. Scores from this fallback path are downscaled and capped at `UNCERTAIN`.
- **Qwen is a 3B model on RunPod.** The endpoint URL in `docker-compose.yml` is a RunPod proxy URL that changes when the RunPod instance is restarted. Update `QWEN_BASE_URL` in the environment or docker-compose when this happens.
- **IEP-1 startup latency.** The sentence-transformer model takes 5–10 seconds to load. Tests or health checks immediately after a container restart may fail.
- **IEP-4 HDBSCAN runs in-memory.** With `min_cluster_size=5`, clusters only form after at least 5 similar complaints exist. In a fresh deployment, everything will be `NEW` until enough data accumulates.
- **IEP-5 and IEP-6 are rule-based.** The MLflow model registry integration exists but the ML training pipeline has not produced trained models yet. Rule-based logic runs unconditionally until models are registered.
- **nginx config file location.** The active nginx configuration is `/etc/nginx/conf.d/cedarfix.conf`. The `default.conf` file was deleted. Always copy to `cedarfix.conf` when updating the nginx config.

### Phase 2 Roadmap
- Replace IEP-3 fallback alignment with a trained contrastive MLP projection head
- Replace IEP-4 rule-based similarity with a trained duplicate classifier
- Replace IEP-5 rule-based scoring with an ML model trained on admin correction data
- Replace IEP-6 rule-based routing with an ML classifier (same training data)
- Replace IEP-7 template explanations with Qwen2.5-7B-Instruct inference
- Replace IEP-2 CLIP zero-shot with BLIP-2 captioning + YOLO object detection
- Implement KL divergence-based embedding drift detection in the monitoring service
- Add Arabic/Arabizi support to the image description pipeline
