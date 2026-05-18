# CedarFix AI - Final Source Of Truth

EECE503N / EECE798N final project plan  
Last updated: 2026-05-15  
Status: final active idea, replacing prior scout documents

## Executive Decision

**Build CedarFix AI.**

CedarFix is the best current project choice if the team commits to a focused, demonstrable version of the system. It has a higher rubric ceiling than the older procurement / Hybrid v2 idea because it can score extremely well on the two largest categories:

- AI Technical Complexity and Execution: 30%
- Presentation / Demo / Wow: 20%

The older procurement / Hybrid v2 idea remains the lowest-risk option because its Lebanese public procurement data is already local and structured. CedarFix is the better final choice only if the team delivers a credible labeled evaluation set and a polished end-to-end demo.

**Final verdict:** CedarFix is a high-ceiling idea conditional on execution discipline. It is not the safest idea. The project wins by protecting a tight spine:

```text
submission -> validated signal -> duplicate/cluster -> calibrated route -> explanation/HITL -> logged feedback -> retraining candidate
```

Do not build anything that does not strengthen that spine.

## One-Sentence Positioning

> CedarFix converts fragmented multilingual citizen reports into deduplicated, clustered, prioritized, explainable infrastructure incidents for Lebanese municipal operations.

## What CedarFix Is

CedarFix is a multi-signal municipal incident triage platform. It treats citizen smartphone submissions as a distributed urban sensor network and fuses text, image, GPS, and time signals into operational incident intelligence via late-fusion combination.

It is not a complaint ticketing app. It is not a CRUD system. It is not an LLM wrapper.

The system answers five operational questions:

1. Is this report valid enough to process?
2. Is it a duplicate of an existing report?
3. Which active infrastructure incident does it belong to?
4. Which public-sector entity should handle it?
5. Should the system auto-route it or send it to human review?

## Differentiation vs Prior Art

CedarFix is not novel because civic complaint platforms are novel. It is novel because the *combination* of multilingual + adaptive Arabizi handling, calibrated routing with confidence-gated HITL, incident lifecycle with REOPENED-as-signal, and late-fusion multi-signal duplicate detection has not been demonstrated together in an open civic platform for Lebanese context.

| System | Year | What it does | Where CedarFix differs |
|---|---|---|---|
| Open311 | 2010 | Open API standard for citizen complaints | CedarFix uses it as design inspiration; adds calibration, lifecycle, multilingual AI |
| SeeClickFix | 2009 | Citizen reporting, map, agency routing | No multilingual, no calibrated confidence, no SHAP, no incident lifecycle, no HITL queue |
| FixMyStreet | 2007 | UK citizen reporting platform | Same gaps as SeeClickFix; English-only |
| Baladi Map (Lebanon) | 2020 | Citizen reporting in Lebanon | No AI routing, no dedup, no calibration, no lifecycle |
| CedarGov | — | Lebanese gov digital initiative | Unrelated scope |
| Academic AI civic classifiers | 2018+ | Routing classifier papers | Generally English-only, no calibration, no lifecycle state machine |

**Novel combination** — the five elements not found together in prior systems:

1. Multilingual + adaptive Arabizi handling on Lebanese context
2. Calibrated routing with confidence-gated HITL (auto-route only when confident)
3. Incident lifecycle state machine with REOPENED state as retraining signal
4. Late-fusion multi-signal duplicate detection (text + image label + GPS + time)
5. OOV language-drift loop where unknown meaningful Arabizi is logged, reviewed, and promoted to vocabulary/model retraining candidates

**C1 scoring rule**: without this differentiation explicitly referenced in the submitted writeup and demo, C1 = 0–1 with a hostile grader. With the prior-art table and the combination framing delivered during the demo, C1 = 2 is defensible.

## Positioning And Baseline Block

This is the fast-reference section for P1-P4 demo questions.

| Rubric item | CedarFix answer |
|---|---|
| P1 - Problem clarity | Lebanese municipalities receive fragmented infrastructure complaints through WhatsApp, phone calls, forms, and informal channels. The concrete decision is: given a new report, detect duplicate status, assign an incident cluster, prioritize it, and route it to the correct public-sector entity. |
| P2 - Baseline rigor | Baseline B1: keyword router with issue keywords mapped to sectors/agencies. Baseline B2: exact or near-exact text duplicate matching plus GPS radius. CedarFix must beat B1 on routing accuracy and B2 on duplicate recall / false merge balance. |
| P3 - AI justification | Rules fail because multilingual and Arabizi reports use different words for the same issue, semantic duplicates cross languages, image/GPS signals must be fused with text, and confidence-calibrated routing/HITL cannot be reduced to keyword matching. |
| P4 - Value / deployer | Representative deployer profile: a Lebanese municipal public works workflow (Beirut Municipality used as canonical example pending verified sourcing). Secondary representative deployer: OMSAR or a governorate/municipality digital services pilot. Value: fewer duplicate dispatches, faster routing, geolocated incident intelligence, and audit-ready public-sector decisions. |

Non-AI baseline framing:

```text
Keyword baseline:
  complaint text -> keyword issue type -> static routing table -> agency

Exact-match duplicate baseline:
  same/near-same text + GPS radius -> duplicate

CedarFix:
  multilingual extraction + embeddings + image/GPS/time signals
  -> duplicate/cluster
  -> calibrated route with SHAP and HITL fallback
```

Three AI-necessity arguments to repeat in Q&A:

1. "Pothole on Hamra", "حفرة في الحمرا", and "fi hofra 3al Hamra" are the same operational signal, but not the same keywords.
2. Duplicate detection is semantic, multi-signal (late-fusion: text + image label + GPS + time), geospatial, and temporal; exact matching undercounts incidents and wastes response capacity.
3. A confidence-calibrated routing model can decide when not to decide and send uncertain cases to human review; a keyword router cannot produce trustworthy uncertainty.
4. Lebanese Arabizi is not closed-vocabulary. CedarFix monitors unknown meaningful terms as language drift instead of pretending the dictionary is complete.

## Hard-Stop Gates

| Gate | Requirement | CedarFix plan |
|---|---|---|
| GT1 | Demo works end-to-end | Submit complaint, process, cluster, route, explain, update dashboard |
| GT2 | Public cloud API functional | Deployed EEP endpoint returns 202 and exposes status endpoint |
| GT3 | Architecture minimum met | EEP plus at least 2 independent IEPs; final plan uses 4 IEPs |
| GT4 | Required deliverables complete | GitHub repo, cloud URL, live demo, docs, tradeoffs, tests |
| GT5 | Type-specific minimum | Application project. If rubric marks GT5 as research-only, record as N/A |

## Projected Rubric Score

This is the target if the scoped version is executed cleanly. It is not a promise; it is a build-priority guide.

| Category | Weight | Target | Rationale |
|---|---:|---:|---|
| AI Technical Complexity and Execution | 30% | 28-30 | Four distinct AI services: multilingual extraction, duplicate/cluster intelligence, calibrated routing/priority, constrained LLM explanation. Calibration and SHAP are the high-signal differentiators. |
| Software Methodology | 15% | 13-15 | Clear EEP/IEP contracts, async state machine, validation, fallbacks, Docker Compose, deployment plan. |
| Application / Research Positioning | 10% | 8-10 | Strong public-sector decision loop and named representative deployers. Risk is evidence for real Lebanese complaint data. |
| Presentation / Demo / Wow | 20% | 18-20 | Live map, cluster crystallization, HITL queue, SHAP card, Arabizi Drift Radar, reliability diagram, Grafana/MLflow. |
| Creativity and Innovation | 5% | 5 | Multilingual multi-signal municipal incident triage with calibrated confidence-gated routing and incident lifecycle — originality conditional on framing differentiation from SeeClickFix/Open311 (see Differentiation vs Prior Art section). |
| Quality Assurance | 5% | 4-5 | Golden dataset, unit/integration/E2E tests, edge-case tests, model regression gates. |
| GitHub Repository | 5% | 4-5 | Feature branches, PRs, ownership, prompt/model version traceability. |
| MLOps / Observability / Documentation | 10% | 8-10 | MLflow, model registry, calibration artifact, primary routing-confidence drift monitor, human override labels, complete docs. |
| Realistic target | 100% | 88 | All 10 build priorities complete, corpus + baselines + tradeoffs + cloud deploy delivered |
| Optimistic ceiling | 100% | 94 | Above + B3 baseline + induced-drift demo + Arabizi corpus raised to 80 + originality framing rewritten |
| Pessimistic floor | 100% | 76 | Sequential HTTP (T4=1), corpus <300, missing baselines, demo wobbles |

## Current Pre-Build Rubric Score

This is the honest score for the plan before implementation evidence exists. Demo items are not awarded full credit until the team performs the demo in front of evaluators.

Current weighted score before bonus: **70.5 / 100** (strict professor pre-implementation scoring: **67/100** if T1/T2/T3/S1–S3/P3/C1/C2 are all scored at 1 as not-yet-built; the plan scored those at 2 for design quality — see dispute note in Rubric Score Audit section).

| Category | Current item score | Weighted contribution | Main missing evidence |
|---|---:|---:|---|
| AI Technical Complexity and Execution | 10 / 12 | 25.0 / 30 | T5 measured tradeoffs and T6 edge-case execution evidence |
| Software Methodology | 8 / 10 | 12.0 / 15 | Docker Compose and deployment/secrets evidence |
| Application / Research Positioning | 6 / 8 | 7.5 / 10 | Baseline results and sourced deployer/value evidence |
| Presentation / Demo / Wow | 5 / 10 | 10.0 / 20 | Demo not built yet; D2 technical clarity is also pre-build 1, not 2 |
| Creativity and Innovation | 4 / 4 | 5.0 / 5 | Already strong in concept |
| Quality Assurance | 2 / 4 | 2.5 / 5 | Tests and golden regression set not built |
| GitHub Repository | 2 / 4 | 2.5 / 5 | Commit/PR discipline and prompt traceability not yet present |
| MLOps / Observability / Documentation | 4 / 8 | 5.0 / 10 | MLflow pipeline, monitoring, and complete docs not implemented |

Disputed item correction:

- **D2 technical clarity = 1 pre-build.** The document is technically clear, but D2 is graded during presentation/demo performance. It becomes 2 only after a clear live explanation, ownership handoff, and Q&A response.

Fragile item warning:

- **T4 EEP orchestration = 2 only if real async orchestration is implemented.** If the final code is sequential HTTP forwarding, T4 drops to 1 or 0. The implementation must show Redis Streams or equivalent queued events, status transitions, and dependency signaling between IEP outputs.

Last-two-weeks priority rule:

1. Protect GT1/GT2 first: end-to-end demo and public cloud EEP.
2. Protect T1/T4/D1/D3/D5 next: AI story, orchestration, evidence, visual wow.
3. Protect M2/M3 with the minimum real lifecycle loop: MLflow, calibration, routing-confidence drift.
4. Cut stretch features before cutting tests, calibration, SHAP, or HITL.

## Three-Layer Architecture

Every service must belong to one of these layers.

```text
Layer 1 - Trust / Ingestion
Synchronous validation, schema checks, PII scrubbing, abuse controls, initial persistence.

Layer 2 - Intelligence
Asynchronous ML/LLM processing: extraction, embeddings, duplicate detection, clustering, routing, explanation.

Layer 3 - Operations
Incident state, dashboard, routing queue, human review, audit log, retraining labels.
```

This separation is the first architecture diagram. It prevents the project from looking like a script or linear notebook pipeline.

## Correct Async Flow

The original plan had an async contradiction. The corrected contract is:

```text
POST /complaints
  -> validate/store complaint
  -> enqueue processing jobs
  -> return 202 Accepted with complaint_id

GET /complaints/{complaint_id}/status
  -> return current state, partial results, final decision if ready

Background flow:
  EEP -> IEP-1 text extraction
      -> IEP-2 duplicate/cluster assignment
      -> IEP-3 calibrated routing/priority
      -> IEP-4 explanation or HITL queue
      -> dashboard and audit log update
```

The citizen never waits synchronously for CLIP, vector search, SHAP, or LLM explanation.

T4 implementation requirement:

- The EEP must enqueue work and update state; it must not synchronously chain model HTTP calls.
- IEP-1 emits a `text_extracted` event with the text embedding.
- IEP-2 can begin image labeling and GPS candidate search immediately, but its text-fusion duplicate scoring waits for the `text_extracted` event.
- IEP-3 runs after incident assignment/update, including duplicate cases that update parent incident priority.
- IEP-4 runs after the decision record exists or sends the case to HITL.

Acceptable implementation: Redis Streams consumer groups, task queue events, or an equivalent event-driven mechanism with persisted state transitions. Sequential forwarding is not enough for a 2/2 on T4.

## Complaint State Machine

Complaint states:

- RECEIVED
- PROCESSING
- PARTIALLY_PROCESSED
- FULLY_PROCESSED
- ROUTED
- HITL_REQUIRED
- RESOLVED
- ARCHIVED

Incident states:

- EMERGING: 2-3 complaints, not yet confirmed
- ACTIVE: confirmed incident
- ESCALATING: growth rate exceeds threshold
- STABLE: growth rate declining
- RESOLVED: no new reports for configured period after routing
- REOPENED: resolved cluster receives new reports

`REOPENED` is a valuable training and policy signal because it suggests failed repair, recurring infrastructure weakness, or premature closure.

## Services

### EEP - Complaint Gateway

Layer: Trust / Ingestion and Operations

Responsibilities:

- Accept citizen complaint text, optional image, optional GPS.
- Validate text length, image format, image size, GPS bounding box, and request shape.
- Scrub PII from free text.
- Rate-limit submissions by IP or user.
- Store complaint with state `RECEIVED`.
- Enqueue background jobs.
- Expose status endpoint and dashboard APIs.
- Own the complaint state machine and audit log.
- Apply graceful degradation when an IEP fails.

Important behavior:

- `POST /complaints` returns `202 Accepted`.
- It does not block on downstream model calls.
- If downstream services fail, the complaint remains visible with partial status and fallback flags.

### IEP-1 - Text Intelligence Service

Layer: Intelligence

Core task: multilingual complaint understanding and structured extraction.

Inputs:

- complaint_id
- complaint text

Outputs:

- language
- language_confidence
- issue_type
- issue_type_confidence
- location_entity
- severity_cues
- normalized_text
- text_embedding

Supported language variants:

- Arabic
- Lebanese Arabic
- French
- English
- Arabizi

Models:

- Lightweight language detector such as fastText or equivalent.
- Multilingual embedding model such as paraphrase-multilingual-mpnet-base-v2.
- Structured extraction classifier or constrained LLM extraction for issue type and severity cues.

Arabizi handling:

- Use transliteration / normalization as a mitigation.
- Do not claim Arabizi fine-tuning unless it is actually done.
- Report Arabizi separately in evaluation because it will likely underperform.

Fallback:

- If extraction confidence is low, return issue_type OTHER and route to HITL downstream.

IEP-1 must be independently testable with per-language F1 scores.

### IEP-2 - Late-Fusion Multi-Signal Duplicate And Incident Intelligence Service

Layer: Intelligence

Core tasks:

- image understanding
- duplicate detection
- cluster assignment
- incident lifecycle update

Important dependency correction:

IEP-2 has immediate and dependent branches.

Immediate branches:

- image validation and image issue labeling
- GPS/geohash candidate search

Dependent branch:

- text fusion and duplicate scoring after IEP-1 produces text embedding

Do not claim full parallel execution between IEP-1 and IEP-2. The real design is partial parallelism plus dependency-aware orchestration.

Image understanding:

- Use CLIP zero-shot classification or simple image labels for issue category.
- Do not claim learned projection between multilingual text embeddings and CLIP image embeddings.
- Cross-modal consistency in V1 should compare image-derived issue label against IEP-1 issue_type.

Duplicate detection:

Candidate matching should combine:

- text similarity
- image issue category when available
- GPS distance
- timestamp window

Recommended V1 logic:

```text
candidate_duplicate if:
  geographic_distance <= 200m
  and timestamp_delta <= 72h
  and (
    text_similarity >= threshold_text
    or image_issue_type == text_issue_type with sufficient confidence
  )
```

Cluster assignment:

- Assign to nearest active incident centroid if within configured radius.
- Create potential new incident if no cluster matches.
- Use HDBSCAN offline or periodically if feasible, but do not make nightly HDBSCAN mandatory for the MVP.
- A deterministic centroid assignment strategy is enough for the demo.

Duplicate correction:

- Duplicate does not mean skip IEP-3.
- Duplicate means do not create a new incident.
- IEP-3 still updates the parent incident's priority, escalation status, and routing state.

Outputs:

- is_duplicate
- matched_ids
- incident_id
- incident_state
- cluster_size
- growth_rate
- image_issue_type
- cross_modal_consistency_flag
- escalation_flag

### IEP-3 - Calibrated Decision Engine

Layer: Intelligence

Core tasks:

- routing classifier
- calibrated confidence
- priority scoring
- SHAP explanation features
- HITL trigger decision

Routing:

- Level 1: sector classification: WATER, ELECTRICITY, ROADS, WASTE, FLOODING, SAFETY, OTHER.
- Level 2: entity routing based on sector plus GPS district / municipal responsibility lookup.

Why hierarchical routing matters:

- Wrong sector is high risk.
- Wrong department inside correct municipality is lower risk.
- Confidence thresholds should be stricter at Level 1.

Calibration:

- Use Platt scaling or isotonic regression on routing model outputs.
- Show reliability diagram / calibration curve in demo.
- Treat calibrated confidence as operational, not cosmetic.

HITL threshold:

- If calibrated routing confidence < 0.65, route to human review.
- If public safety terms appear, route to human review regardless of confidence.
- If cross-modal consistency is poor, route to human review.
- If issue_type is OTHER, route to human review.

Priority score:

Continuous 0.0 to 1.0 score using:

- severity cues
- incident_state
- cluster_size
- growth_rate
- issue type base severity
- time since first report

SHAP:

- Compute top contributing features for routing/priority decisions.
- Display top three in admin dashboard.
- Store with decision record for audit.

Outputs:

- routing_sector
- routing_entity
- routing_confidence
- priority_score
- shap_top3
- hitl_required
- hitl_reason

### IEP-4 - Explanation And Human Review Service

Layer: Intelligence and Operations

Core LLM task:

- constrained explanation synthesis from the structured decision record.

Critical rule:

- ML decides.
- LLM explains.
- The LLM must not make the routing decision.

Inputs:

- decision_record
- SHAP top features
- incident state
- RAG context from municipal responsibility knowledge base

RAG knowledge base content:

Keep the V1 knowledge base small, structured, and auditable. It should live under `iep-explain/data/` or equivalent and contain:

| File | Purpose |
|---|---|
| `sector_agency_map.csv` | Maps issue sectors to responsible public-sector entities, for example WATER, ROADS, ELECTRICITY, WASTE, FLOODING, SAFETY. |
| `municipality_responsibility_map.csv` | Maps municipality/district/service area to department or representative contact target used in the demo. |
| `issue_severity_reference.yaml` | Defines issue-type severity priors and public-safety escalation notes used in explanations. |

The RAG service retrieves from these records; it does not invent jurisdiction.

Outputs:

- citizen explanation
- admin explanation
- audit explanation
- RAG sources used

Explanation levels:

- Citizen-facing: short, plain language, no ML jargon.
- Admin-facing: cites cluster size, route, confidence, and top features.
- Audit-facing: includes model version, prompt version, input hash, decision record, and override history.

Fallback:

- If LLM times out or fails, use template explanation.
- Routing must never be blocked by LLM availability.

Prompt version tracking:

- Store prompts in a repo-root `prompts/` directory.
- Minimum files: `iep4_citizen_v1.txt`, `iep4_admin_v1.txt`, `iep4_audit_v1.txt`.
- Every decision record stores `prompt_version` and `prompt_hash`.
- Every MLflow/evaluation run logs the prompt versions used.
- Every prompt change gets a changelog entry with before/after factual-grounding scores.

Because CedarFix uses an LLM, prompt traceability is required for G2.

Human review:

- reviewer confirms routing
- reviewer corrects routing
- reviewer confirms/rejects duplicate
- reviewer splits or merges incident cluster

Every review action becomes a training label.

## Minimal Real MLOps Scope

Do not overbuild MLOps. The project should show one real lifecycle loop done correctly.

Required:

- MLflow experiment tracking for the routing classifier.
- Model registry with champion/challenger versions.
- Calibration curve artifact.
- Promotion thresholds.
- Human override labels stored for retraining.
- One demonstrated drift signal via induced dataset shift: routing confidence distribution shift (artificially induced for demo via class-proportion shift script; real production drift requires an extended operation window that a 5-week project cannot produce).

Supporting metrics:

- HITL rate
- duplicate detection rate
- IEP-1 extraction confidence mean
- service latency and error rates

The supporting metrics are useful operational indicators. The primary drift story should remain routing confidence distribution drift.

## Retraining Pipeline

Keep retraining limited to IEP-3 routing classifier in V1.

Pipeline:

1. Load human-reviewed labels.
2. Train routing model.
3. Calibrate confidence.
4. Evaluate on golden dataset.
5. Log metrics and artifacts in MLflow.
6. Register challenger if minimum thresholds pass.
7. Promote only if challenger beats champion.
8. Keep champion if challenger fails.

Promotion thresholds:

- routing_accuracy >= target threshold
- Expected Calibration Error <= target threshold
- no critical class recall regression
- fallback/HITL rate does not worsen beyond allowed threshold

## Monitoring

System monitoring:

- request latency
- error rate
- queue depth
- per-service timeout count
- model inference latency

AI monitoring:

- routing confidence mean
- routing confidence distribution drift
- HITL rate
- duplicate detection rate
- extraction confidence mean

Grafana panels for demo:

1. Request latency by service.
2. Routing confidence over time.
3. HITL rate.
4. Error rate / fallback rate.

## Evaluation Strategy

The data story is the main risk. The system must not rely on synthetic evaluation.

### Corpus

Use a human-authored, human-labeled multilingual complaint corpus.

Target:

- 500 human-authored complaints (raised from 400 to ensure credible per-sector and per-language evaluation; 400 yields only ~46 training / ~11 eval per sector).
- 200 augmented training examples (back-translation or paraphrase of human-authored examples only — see augmentation warning below).
- Evaluation set must be human-labeled only.

Labeling:

- Two annotators per complaint.
- Measure Cohen's Kappa.
- Resolve disagreements and log final labels.

Do not call human-authored examples "real complaints" unless they came from actual users or public records.

### Component Metrics

IEP-1 text extraction:

- issue_type F1
- per-language F1
- Arabizi F1 reported separately
- location_entity extraction precision/recall if labeled

IEP-2 duplicate/cluster:

- duplicate precision
- duplicate recall
- false merge rate
- cluster purity
- adjusted Rand index if enough ground truth exists

IEP-3 routing:

- sector accuracy
- entity accuracy
- confusion matrix
- Expected Calibration Error
- reliability diagram
- HITL trigger rate

IEP-4 explanation:

- factual grounding check
- explanation contains correct routing entity
- explanation contains correct priority/confidence if required
- template fallback test

### Baselines

Baseline B1: keyword router.

- 50 to 100 keyword rules mapped to sectors.
- Evaluate routing accuracy.

Baseline B2: exact-match duplicate detection.

- Same or near-identical text only.
- Evaluate duplicate recall.

Baseline B3: zero-shot multilingual classifier (off-the-shelf XLM-R or equivalent, no CedarFix-specific training).

- Purpose: answer the "why not just use a foundation model?" professor objection with a measured result.
- Measure: routing accuracy and HITL trigger rate on the same held-out evaluation set as B1/B2.
- CedarFix must beat B3 on at least sector accuracy or calibration ECE.
- Without B3, P2/P3 evidence is incomplete and the professor will ask "why not just call XLM-R?" without a numeric answer.

CedarFix must beat all three baselines or document failures honestly and explain why.

## Rubric Map

### T1 - AI Depth And Non-Triviality

Earn 2/2 by showing multiple distinct AI components:

- multilingual extraction
- vector embeddings
- duplicate detection
- clustering / incident assignment
- calibrated routing classifier
- SHAP attributions
- constrained LLM explanations

### T2 - IEP-1 Independence And Value

IEP-1 is valuable because it turns unstructured multilingual complaints into structured fields used by every downstream service.

Evidence:

- independent service
- documented API contract
- per-language evaluation
- fallback for low confidence

### T3 - IEP-2 Independence And Value

IEP-2 is different from IEP-1 because it owns vector search, image signal, GPS matching, duplicate detection, and incident state.

Evidence:

- duplicate evaluation
- cluster evaluation
- lifecycle transition log
- graceful handling of missing image/GPS

### T4 - EEP Orchestration Logic

Earn 2/2 by showing:

- async job enqueueing
- partial parallelism
- dependency-aware flow
- conditional fallbacks
- complaint state machine
- no blocking on LLM

### T5 - Tradeoff Evidence

Required measured tradeoffs:

1. Embedding model size vs duplicate recall and latency.
2. CLIP zero-shot image labeling vs fine-tuned detector.
3. Auto-routing threshold vs HITL workload and routing error.
4. LLM API vs self-hosted quantized model for cost, latency, and data control.

Measurements can be small, but they must be real.

### T6 - Execution Quality And Edge Cases

Test and document:

- GPS outside Lebanon rejected.
- missing image handled.
- image-only complaint handled if allowed.
- Arabizi complaint lowers confidence but does not crash.
- Qdrant unavailable triggers no-dedup fallback.
- LLM timeout triggers template fallback.
- duplicate burst updates incident rather than creating many incidents.
- large cluster triggers escalation path.

## Software Methodology Map

### S1 - Service Boundaries And Contracts

- FastAPI services.
- Pydantic request/response models.
- OpenAPI docs.
- No direct imports between services.

### S2 - Validation And Request Constraints

EEP validates:

- text length
- image size and MIME type
- GPS within Lebanon bounding box
- rate limits
- required fields

IEPs also validate inputs independently.

### S3 - Errors, Timeouts, Retries, Fallbacks

Every cross-service call must have:

- timeout
- retry rule
- fallback behavior
- logged error type

### S4 - Containerization And Orchestration

Minimum:

- Docker image for EEP.
- Docker image for each IEP.
- Docker Compose for local demo.
- Qdrant, PostgreSQL, Redis, MLflow, Prometheus, Grafana in local stack or managed equivalents.

Kubernetes YAML is useful but should not make the demo fragile.

### S5 - Deployment Architecture And Secrets

- No secrets in code.
- `.env.example` only.
- cloud secret manager documented.
- cloud deployment diagram.
- public EEP URL.
- cost estimate.
- Middle East region preference documented if applicable.

## Demo Plan

Duration: 8 to 10 minutes.

### Act 1 - Citizen Signal

Show map with existing incidents. Submit a multilingual complaint.

Show:

- 202 response with complaint_id.
- status polling.
- validation and state update.

### Act 2 - Intelligence

Show the complaint flowing through:

- IEP-1 structured extraction.
- IEP-2 duplicate/cluster assignment.
- IEP-3 calibrated routing and SHAP.
- IEP-4 explanation or HITL.

Hero visuals:

- map cluster update
- SHAP waterfall/bar chart
- calibration reliability diagram

### Act 3 - Operations And Lifecycle

Show:

- human review queue
- admin decision card
- audit record
- Grafana routing confidence panel
- MLflow model/version page with calibration artifact

MLflow champion/challenger moment: show one additional MLflow run where a deliberately worse challenger was trained (lower accuracy on a held-out partition). Navigate to the run, show the promotion threshold comparison, show the gate rejecting it. Navigate to the champion model page. This is the single highest-rubric-efficiency moment in the demo — it proves the full retraining lifecycle is real, not cosmetic.

Close with:

```text
complaints -> incidents -> routing -> review -> labels -> retraining
```

## What Not To Build

Do not build these for V1:

| Cut item | Why it is cut from V1 |
|---|---|
| Full GNN topology model | Interesting, but it needs real infrastructure topology and enough historical co-failure labels. NetworkX-style co-occurrence analysis can be a stretch note instead. |
| Predictive maintenance scheduling | Requires maintenance action/outcome history. Without it, recommendations become speculative planning theater. |
| Resolution-time forecasting | Needs real historical resolution timestamps by entity/issue/district. Without those labels, confidence intervals would be fake precision. |
| Full mobile PWA | Useful for production, but frontend offline sync does not improve the core AI/rubric spine enough for V1. |
| Full real-time streaming ingestion | Complaint volume does not require true streaming. Durable async queue plus polling is enough and easier to demo reliably. |
| Cross-attention multimodal fusion | Requires a large labeled multimodal training set. Late fusion is more defensible for the available data. |
| Learned CLIP/text projection model | Needs paired image/text training data. V1 should compare image-derived issue label against text issue_type instead. |
| Full Airflow/Prefect orchestration | Adds operational complexity. A queue plus simple retraining script is enough for the rubric. |
| Full LLM hallucination monitoring | Good LLMOps stretch, but V1 only needs deterministic factual-grounding checks on decision-record fields. |
| Arabizi fine-tuning | Valuable, but requires a dedicated labeled Arabizi set. V1 uses transliteration/normalization and reports Arabizi performance separately. |
| Multi-agency performance league tables | Politically sensitive and not needed for the AI spine. Keep agency workload/queue view, not public ranking. |

These are good stretch ideas but bad MVP requirements.

## Professor Critiques And Defenses

### "Your data is small or synthetic."

Defense:

The evaluation set is human-authored and human-labeled, with two annotators and Cohen's Kappa. Synthetic data is used only for training augmentation, never for final evaluation.

### "Why not use a simple keyword system?"

Defense:

The keyword router is our baseline. CedarFix is evaluated against it on routing accuracy and duplicate recall. The AI contribution is semantic multilingual matching, multi-signal (late-fusion) duplicate detection, calibrated routing, and incident-level clustering.

### "Why do you need an LLM?"

Defense:

The LLM does not route. ML routes and scores. The LLM only generates constrained explanations from the decision record and RAG context. This improves citizen/admin communication without letting the LLM make operational decisions.

### "Why microservices for a small student project?"

Defense:

The decomposition follows different compute and failure profiles:

- text NLP
- vector/image/geospatial matching
- fast calibrated routing
- slow LLM explanation

The boundaries are not for scale theater. They make failures isolated and make the EEP orchestration meaningful.

### "What happens if the model is wrong?"

Defense:

Low-confidence cases go to HITL. Human overrides are logged and become retraining labels. Every decision stores model version, prompt version, confidence, SHAP features, and final human action.

## Build Phases

### Phase 1 - Foundation

- repo structure
- Docker Compose
- PostgreSQL schema
- Redis queue
- Qdrant
- MLflow
- EEP validation and state machine

### Phase 2 - Core AI

- IEP-1 extraction and embeddings
- IEP-2 text/GPS duplicate detection
- IEP-3 routing classifier
- first labeled dataset
- first end-to-end async flow

### Phase 3 - Rubric Differentiators

- calibration curve
- SHAP attributions
- image issue labeling
- HITL queue
- LLM/template explanations
- Prometheus/Grafana metrics

### Phase 4 - Validation And Deployment

- golden dataset
- unit/integration/E2E tests
- cloud EEP deployment
- MLflow experiments and model registry
- tradeoff measurements

### Phase 5 - Demo Polish

- rehearsed script
- seeded incidents and complaints
- map cluster visual
- SHAP visual
- reliability diagram
- Q&A preparation

## Final Active Scope

Build exactly this:

1. EEP with async complaint intake, validation, state machine, and dashboard/status APIs.
2. IEP-1 multilingual extraction and text embeddings.
3. IEP-2 duplicate detection, cluster assignment, incident lifecycle, and simple image issue labeling.
4. IEP-3 calibrated routing, priority scoring, SHAP, and HITL trigger.
5. IEP-4 constrained explanation generation, template fallback, and human review.
6. MLflow plus one real drift story: routing confidence distribution shift.
7. A polished map-based demo with calibration and SHAP evidence.

## Rubric Score Audit

Scores reflect the plan-only state (no implementation evidence). Gate items do not add points but a score of 0 on any gate halts grading.

| Item | Weight | Score | To reach 2 |
|---|---:|---:|---|
| GT1 | gate | 1 | Build and rehearse full demo; add seeded data and backup video before grading day |
| GT2 | gate | 1 | Deploy public EEP URL with working POST /complaints and GET /status |
| GT3 | gate | 2 | Already satisfied: EEP + 4 IEPs |
| GT4 | gate | 1 | Finish repo, docs, tests, cloud URL, demo script, evaluation artifacts |
| GT5 | N/A | N/A | Application project; not a research gate |
| T1 | 5% | 1 ⚠️ | Pre-build: design only. Reaches 2 when all AI components (extraction, embeddings, dedup, cluster, calibrated routing, SHAP, explanation) run with passing tests. |
| T2 | 5% | 1 ⚠️ | Pre-build: IEP-1 not built. Reaches 2 with independent service deployed and per-language F1 table (Arabic+French+English ≥ 0.75 macro-F1). |
| T3 | 5% | 1 ⚠️ | Pre-build: IEP-2 not built. Reaches 2 with running service, cluster purity ≥ 0.7, and duplicate PR curve > B2 by ≥15pp. |
| T4 | 5% | 1 ⚠️⚠️ | **Highest risk**: partial parallelism must be real Redis Streams dependency signaling code. Pre-build = 1. Reaches 2 when IEP-2 internal wait on `iep1_complete` event is proven in integration tests. If sequential HTTP, stays at 1. |
| T5 | 5% | 1 | Run all 4 tradeoff experiments with tables of numbers. See Tradeoff Experiments section. |
| T6 | 5% | 1 | Implement and test 7 edge cases: bad GPS, missing image, Arabizi low confidence, Qdrant unavailable, LLM timeout, duplicate burst, large cluster escalation. |
| S1 | 3% | 1 ⚠️ | Pre-build: contracts designed, not documented. Reaches 2 with OpenAPI docs generated per service (FastAPI /docs endpoints running). |
| S2 | 3% | 1 ⚠️ | Pre-build: validation described, not implemented. Reaches 2 with Pydantic models enforced and boundary tests passing. |
| S3 | 3% | 1 ⚠️ | Pre-build: fallback described, no retry library wired. Reaches 2 with tenacity/httpx retry configured and chaos test for IEP container kill. |
| S4 | 3% | 1 | Build Docker image per service, Docker Compose with health checks for all infra. |
| S5 | 3% | 1 | Cloud EEP deployment, .env.example, secret manager docs, deployment diagram, cost estimate table. |
| P1 | 2.5% | 2 | — |
| P2 | 2.5% | 1 | Implement B1 keyword router and B2 exact-match dedup; run on held-out eval set; produce comparison table. |
| P3 | 2.5% | 1 ⚠️ | Pre-build: 3 arguments exist on paper. Reaches 2 only with measured evidence: B1 routing accuracy < CedarFix on held-out set by ≥10pp. Arguments alone do not harden P3. |
| P4 | 2.5% | 1 | Add sourced evidence: OMSAR digital services reference, Beirut Municipality complaint volume estimate, named workflow benefit. |
| D1 | 4% | 1 | Build full 8-minute demo with seeded incidents + live complaint submission flow. |
| D2 | 4% | 1 | Graded on demo performance. Technical clarity requires rehearsed delivery, not just documented design. |
| D3 | 4% | 1 | Show live: routing accuracy, duplicate PR, ECE / reliability diagram, per-language F1. |
| D4 | 4% | 1 | Rehearse full demo with Q&A drill, failure-mode responses, and ownership assignment. |
| D5 | 4% | 1 | Build: map cluster animation, SHAP waterfall card, reliability diagram, Grafana routing panel, MLflow model page. |
| C1 | 2.5% | 0-1 ⚠️⚠️⚠️ | **HIGH RISK**: SeeClickFix/Open311/FixMyStreet/Baladi Map all do civic routing. Without Differentiation vs Prior Art table in writeup and demo, C1 = 0 with hostile grader. Reaches 2 only when originality is explicitly framed around novel *combination* (multilingual + Arabizi + calibrated routing + HITL + incident lifecycle). |
| C2 | 2.5% | 1 ⚠️ | Pre-build: design choices are insightful but unproven. Reaches 2 when choices are visible in implementation and documented in TRADEOFFS.md. |
| Q1 | 2.5% | 1 | Write unit tests per service, integration tests per IEP API, E2E test for full async flow, LLM grounding check, edge-case tests. |
| Q2 | 2.5% | 1 | Build golden dataset; add CI step that runs routing classifier and duplicate detector against golden labels and fails on regression. |
| G1 | 2.5% | 1 | Use feature branches per service from day one, meaningful commits per owner. |
| G2 | 2.5% | 1 | PRs with review, changelog, model version traceability, prompt version tracking (see Prompt Versioning section — required because Uses LLM = Yes). |
| M1 | 2.5% | 1 | Build and run the 8-step retraining pipeline script end-to-end at least once before demo. |
| M2 | 2.5% | 1 | Log MLflow runs with metrics, ECE, calibration artifact, promotion thresholds; register champion/challenger. |
| M3 | 2.5% | 1 | Instrument Prometheus with routing_confidence_mean, hitl_rate, fallback_rate, latency per service; show in Grafana. |
| M4 | 2.5% | 1 | Complete: README, architecture diagram, evaluation report, TRADEOFFS.md, deployment guide, data spec, model cards (see Model Cards section), prompt docs. |
| B0 | +0-2 | 1 | For 2: live cluster EMERGING→ACTIVE animation with real Arabic text, reliability diagram showing ECE improvement after calibration, Grafana drift alert firing live. |

**Current plan score: 70.5 / 100 (professor-strict pre-implementation: 67/100 if T1/T2/T3/S1–S3/P3/C1/C2 are all scored as 1).** Realistic recoverable: **88**. Optimistic ceiling: **94** with B3 + induced-drift demo + Arabizi raised to 80 + originality reframed. See Score Scenarios section.

Scoring note: D2 is graded on demo performance, not planning quality. GPT's earlier audit scored it 2 from the plan document — that overcount inflated the estimate to 72.5. The correct pre-implementation score is 70.5.

## Critical Implementation Risks

These are design claims in the plan that a grader can verify as false and that would each drop a rubric item:

### Risk 1 — T4 Partial Parallelism Must Be Real Code

The plan correctly states IEP-2 image+GPS branches launch before IEP-1 text embedding finishes. This is partial parallelism and earns T4 = 2/2. If implementation uses sequential HTTP calls (call IEP-1, wait, then call IEP-2), T4 drops to 1.

Implementation requirement: When EEP enqueues a complaint, it publishes to two Redis Streams consumers simultaneously: `iep1_queue` and `iep2_immediate_queue`. IEP-2's immediate branches (image labeling and GPS candidate search) start from `iep2_immediate_queue`. IEP-2's dependent branch (text fusion + duplicate scoring) starts only after it receives a `iep1_complete:{complaint_id}` event from IEP-1. EEP does not orchestrate this wait; IEP-2 does internally.

### Risk 2 — Prompt Version Tracking Is Required for G2

Rubric conditional: "G2: if Uses LLM? = No, ignore the prompt-version clause." CedarFix uses an LLM → prompt version tracking is mandatory.

Implementation requirement: see Prompt Versioning section below.

### Risk 3 — IEP-4 RAG Knowledge Base Must Have Defined Content

The plan says "RAG context from municipal responsibility knowledge base" but never specifies what documents are indexed. A professor will ask what is in the knowledge base. Without an answer, the RAG claim is a hand-wave and IEP-4's independence value is weakened.

Required content (total <5KB, can be static files): `data/kb/sector_agency_map.json` mapping WATER→CDR, ELECTRICITY→EDL, ROADS→Ministry of Public Works, WASTE→municipality, FLOODING→Civil Defense, SAFETY→ISF+Civil Defense; `data/kb/district_municipality_map.json` mapping Beirut districts to responsible departments; `data/kb/issue_severity_guide.json` mapping issue types to base severity and escalation thresholds.

## Tradeoff Experiments

Four experiments required for T5 = 2/2. Each must produce a table with actual numbers, not just a description.

### Experiment 1 — Embedding Model Comparison (1 day)

Test two multilingual embedding models on the duplicate detection task:

- `paraphrase-multilingual-mpnet-base-v2` (768-dim, planned)
- `multilingual-e5-small` (384-dim, faster, lighter)

Measure on labeled duplicate pairs: recall@10, precision@10, inference latency per complaint. Present in a table with model size (MB), latency (ms), recall@10.

### Experiment 2 — Confidence Threshold Ablation (half day)

Test IEP-3 routing classifier at three confidence thresholds: 0.50, 0.65, 0.80.

Measure on dev set: routing accuracy on auto-routed cases, HITL trigger rate. This is the most demo-visible tradeoff: show the curve from "route everything" (low HITL, high error) to "flag everything" (low error, high HITL). The threshold choice of 0.65 should be justified by this curve.

### Experiment 3 — Image Labeling Method (2 hours)

Compare CLIP zero-shot classification vs 5-rule image label heuristics (rule: if image is mostly gray and has crack patterns → ROADS; if image has brown water → WATER or WASTE; etc.).

Measure on 50 labeled images: per-class accuracy, false positive rate, inference latency.

### Experiment 4 — IEP-4 Explanation Quality (half day)

Compare three explanation generation paths:

- LLM API (GPT-4o-mini or equivalent)
- Self-hosted quantized model (Qwen2.5-7B INT4)
- Template-based fallback (no model)

Measure on 30 test decision records: factual grounding check (explanation contains correct routing entity and correct priority level), latency, cost per call. Present in a 3-row table.

## Prompt Versioning System

Required for G2 = 2/2 because CedarFix uses an LLM.

### Directory Structure

```text
prompts/
  iep4_citizen_v1.0.txt     — citizen-facing explanation prompt
  iep4_admin_v1.0.txt       — admin-facing explanation prompt
  iep4_audit_v1.0.txt       — audit-facing explanation prompt
  CHANGELOG.md              — log of every prompt change with version, date, reason
```

### Usage Requirements

- Every IEP-4 call passes the prompt file path (not inline string) to the LLM client.
- Every MLflow run logs `prompt_version` and `prompt_hash` (SHA256 of prompt file).
- Every decision record stored in the database includes `prompt_version`.
- When a prompt is changed, create a new version file (v1.1, v2.0) and add a CHANGELOG entry. Do not edit v1.0 in-place.

### Why This Matters

If a routing explanation is challenged months later, the audit record must show which exact prompt produced it, what model version it used, and what inputs it received. This is what "full decision traceability" means in a production municipal system.

## Model Cards

Required for M4 = 2/2. One card per trained model.

### IEP-1 Issue Type Classifier Card

```text
Model: [name, e.g., fine-tuned mBERT or LightGBM on multilingual embeddings]
Training data: [N] labeled complaints, [date range], [languages]
Evaluation data: [N] held-out complaints, human-labeled
Performance:
  - issue_type macro-F1: [value]
  - per-language F1 table
  - Arabizi F1 (separate stratum): [value]
Known limitations: Arabizi underperforms; OTHER class recall is lower
Intended use: Internal IEP-1 extraction only
Fallback: Returns issue_type=OTHER with low confidence flag
```

### IEP-3 Routing Classifier Card

```text
Model: LightGBM + Platt scaling calibration
Training data: [N] labeled complaints with routing labels, [date range]
Evaluation data: [N] held-out, human-labeled
Performance:
  - sector accuracy: [value]
  - entity accuracy: [value]
  - confusion matrix: [link or inline]
  - Expected Calibration Error (ECE): [value]
  - reliability diagram: [link]
Calibration: Platt scaling applied post-training; see calibration artifact in MLflow
Known limitations: OTHER sector class has lowest recall; rural districts underrepresented
Intended use: IEP-3 routing only; not for policy decisions without HITL review
Retraining: see retraining pipeline section
```

## Demo Safety Protocol

GT1 = 0 if demo fails. These steps must be completed before grading day.

1. **Night before: full local stack rehearsal.** Run `docker compose up`, submit 3 complaints, confirm all 5 services respond, confirm routing and SHAP appear in dashboard. Fix anything that breaks.

2. **Seeded database state.** Before demo, pre-load 4-5 incidents with different states (EMERGING, ACTIVE, ESCALATING, one RESOLVED). Demo starts from a rich state, not empty. This ensures map cluster and routing queue visuals are immediately visible.

3. **Live submission demo complaint.** Prepare one authored complaint per sector for the live submit moment: Arabic text about a pothole in Hamra with GPS. The complaint's extracted language and routing result must be predictable for demo narration.

4. **Backup: pre-recorded video.** Record an 8-minute demo video before grading. Upload to the GitHub repo as `docs/demo_backup.mp4`. If cloud is unreachable during grading, play the video. A recorded demo is always acceptable if announced; it just slightly hurts D5 polish perception.

5. **Fallback: local mode.** EEP must work with `CLOUD_MODE=false` targeting localhost. If the cloud URL is unreachable, fall back to local in under 2 minutes. Document the switch in the README.

## Corpus Stratum Specification

The 400-complaint labeled corpus must include explicit language strata or the per-language evaluation will be incomplete and Arabizi F1 will be undefendable.

Minimum stratum sizes (total: 500):

- Arabic (Lebanese formal + informal): 200 complaints
- French: 80 complaints
- English: 80 complaints
- Arabizi (Latin-script Lebanese Arabic): 80 complaints (raised from 40; minimum for credible per-language F1 with bootstrap CI; 40 gives ±15pp confidence bands)
- Mixed language (code-switching): 60 complaints

Label each complaint with: `language`, `issue_type` (7 classes), `severity_cue` (low/medium/high/critical), `is_duplicate` (boolean with matched_id if true), `routing_sector`, `routing_entity`.

Duplicate pairs: ensure at least 100 labeled duplicate pairs (60 within-cluster + 40 across-cluster as negative pairs). PR curves with 60 pairs have wide confidence intervals; 100 is the minimum for defensible evaluation.

Augmentation warning: if synthetic augmentation is used for training (never for evaluation), use back-translation (Arabic→English→Arabic) or paraphrase of human-authored examples. Do **not** use GPT to generate complaints from scratch — the routing classifier may learn to recognize GPT writing style rather than complaint semantics.

## Corrected Top 10 Build Priorities

Ranked by total rubric points recovered. Points recovered = sum of half-weights of all items moved from 1 to 2 by this work item.

| Priority | Build Item | Points Recovered | Gates Served |
|---|---|---|---|
| 1 | Docker Compose full stack with health checks | S4 +1.5; enables all demo items | GT1, GT2 enabling |
| 2 | E2E demo path: seeded incidents, live submit, SHAP/map visual, backup video | D1 +2, D5 +2 | GT1 |
| 3 | Human-authored corpus (stratum spec above) + B1/B2/B3 baselines implemented and measured | P2 +1.25, P3 +1.25, D3 +2, Q2 +1.25 = **5.75 pts** | — |
| 4 | T5: run all 4 tradeoff experiments, produce number tables | T5 +2.5 | — |
| 5 | T6 + Q1: edge case tests for all 7 scenarios | T6 +2.5, Q1 +1.25 = **3.75 pts** | — |
| 6 | Cloud EEP deployment + .env.example + cost table + deployment diagram | S5 +1.5 | GT2 |
| 7 | MLflow lifecycle: experiments, calibration artifact, model registry, champion/challenger promote | M1 +1.25, M2 +1.25 = **2.5 pts** | — |
| 8 | Grafana: routing_confidence_mean drift panel, HITL rate, latency, fallback rate | M3 +1.25 | — |
| 9 | Git discipline from day 1 + `prompts/` versioning system | G1 +1.25, G2 +1.25 = **2.5 free pts** | — |
| 10 | Full demo rehearsal + Q&A drill + failure-mode answers | D4 +2 | GT1 confidence |

**Total recoverable with all 10 complete: 88 realistic / 94 optimistic / 97 theoretical max with bonus.**

Priority 9 (git + prompt versioning) costs zero additional engineering. It is pure behavior and setup. Start it on day 1 and never fall behind.

## Feasibility Audit

Semester reality check: 4 team members, 5 weeks remaining, 15–20 hours per person per week ≈ 320–400 person-hours available.

| Component | Est. hours | Feasible? | Risk |
|---|---:|:---:|---|
| Docker Compose + Redis Streams skeleton | 25 | Yes | Low |
| EEP service + state machine | 30 | Yes | Low |
| IEP-1 multilingual extraction + embeddings | 35 | Yes | Medium — depends on model choice |
| IEP-2 image labels + GPS + dedup + cluster | 50 | Tight | High — most complex service |
| IEP-3 routing + calibration + SHAP | 25 | Yes | Low |
| IEP-4 LLM + RAG + HITL queue | 30 | Yes | Medium |
| 500-complaint corpus labeling | 60 | Tight | **Highest risk** — cannot be compressed; must start Week 1 |
| 4 tradeoff experiments | 15 | Yes | Low |
| Edge case test suite + CI | 20 | Yes | Low |
| Cloud deployment + Grafana + MLflow | 25 | Yes | Medium |
| Demo polish + rehearsal | 20 | Yes | Low |
| **Total** | **335** | Borderline | — |

**Verdict**: tight but feasible. The corpus labeling (60 hours of human work, two annotators) is the single largest risk. Starting it in Week 2 instead of Week 1 loses parallel runway that cannot be recovered.

## Feature Effectiveness Audit

Survival rule: a feature must strengthen ≥2 of {AI complexity, Demo/Wow, MLOps/Obs, Baseline/Eval, Prior-art defense, Public-sector realism}.

| Feature | Decision | Rubric items | Survives? |
|---|:---:|---|:---:|
| EEP async + state machine | **KEEP** | GT1, T4, S1-S3 | ✓ |
| IEP-1 multilingual + embeddings | **KEEP** | T1, T2, P3, D3 | ✓ |
| IEP-2 late-fusion dedup + cluster | **KEEP** | T1, T3, D3 | ✓ |
| IEP-2 image labeling (CLIP zero-shot) | **SIMPLIFY** | T3, T5 | ✓ — zero-shot only, no fine-tune |
| IEP-2 cross-modal consistency flag | **KEEP** | T3, T6 | ✓ |
| IEP-2 incident lifecycle state machine | **KEEP** | C1, C2, T3 | ✓ — strongest originality element |
| IEP-3 routing classifier | **KEEP** | T1, P2, M2 | ✓ |
| IEP-3 calibration (Platt scaling) | **KEEP** | T1, T5, M2, D3 | ✓ |
| IEP-3 SHAP attributions | **KEEP** | T1, C2, D5 | ✓ |
| IEP-3 priority score | **SIMPLIFY** | T1, C2 | ✓ — weighted sum, not learned |
| IEP-4 LLM explanation | **KEEP** | T1, M4, D5 | ✓ |
| IEP-4 RAG KB | **SIMPLIFY** | T1, M4 | ✓ — 3 static JSON files only |
| IEP-4 template fallback | **KEEP** | T6, S3 | ✓ |
| HITL review queue | **KEEP** | C2, M2, D5 | ✓ |
| Override-as-label retraining loop | **KEEP** | M1, M2, C2 | ✓ |
| MLflow + model registry | **KEEP** | M1, M2, M4 | ✓ |
| Champion/challenger promotion gate | **KEEP** | M1, M2 | ✓ — demo with worse-challenger rejection |
| Calibration artifact in MLflow | **KEEP** | M2, D3, T5 | ✓ |
| Prompt versioning system | **KEEP** | G2, M4 | ✓ — required for G2 |
| Grafana drift panel (induced) | **KEEP** | M3, D5 | ✓ — induced drift demo |
| Edge case test suite | **KEEP** | T6, Q1 | ✓ |
| Golden regression CI gate | **KEEP** | Q2, M4 | ✓ |
| Backup demo video | **KEEP** | GT1 safety | ✓ |
| Live cloud deployment | **KEEP** | GT2, S5 | ✓ |
| HDBSCAN nightly recomputation | **STRETCH** | C2 | ✗ — centroid assignment is enough |
| Self-hosted quantized LLM in production | **STRETCH** | T5 | ✗ — inside Experiment 4 only |
| Full Kubernetes deployment | **CUT** | — | ✗ |
| Full PWA frontend | **CUT** | — | ✗ |
| Cross-attention multimodal fusion | **CUT** | — | ✗ |
| Arabizi fine-tuning | **CUT** | — | ✗ |
| LLM hallucination monitoring | **CUT** | — | ✗ — grounding check is sufficient |

## Execution Backlog (15 Tasks)

Ranked by rubric recovery. Owner roles, artifacts, acceptance criteria, and rubric items unlocked for each task.

| Rank | Task | Owner | Artifact | Acceptance | Rubric |
|---|---|---|---|---|---|
| 1 | Async skeleton: Docker Compose + Redis Streams + POST/202 + GET/status + IEP stubs | Backend lead | `docker-compose.yml`, `eep/main.py`, `iep*/worker.py` | POST /complaints returns 202; status polling works; 4 IEP stubs consume from streams | GT1, GT2, S4, T4 |
| 2 | Corpus labeling sprint (500 complaints, stratified) | Data lead + all | `data/corpus_v1.jsonl` + label guide + Kappa report | 500 labeled; 2 annotators on 100-sample subset; Kappa ≥ 0.7 | P2, Q2, M4 |
| 3 | IEP-3 routing classifier + calibration + threshold ablation | ML lead | `iep3/model.pkl`, `mlruns/`, `reports/threshold_ablation.csv` | Sector accuracy > B1 by ≥10pp; reliability diagram; ECE < 0.1 with 1000-iter bootstrap CI | T5, M2, P2, P3, D3 |
| 4 | IEP-1 multilingual extraction with per-language F1 | NLP lead | `iep1/`, `reports/per_language_f1.csv` | Macro-F1 ≥ 0.75 on Arabic+French+English; Arabizi reported separately with bootstrap CI | T2, P2, D3 |
| 5 | IEP-2 late-fusion dedup + cluster + image labels | ML lead | `iep2/`, `reports/duplicate_pr.png` | Duplicate F1 > B2 by ≥15pp; cluster purity ≥ 0.7 | T3, P2, D3 |
| 6 | B1 + B2 + B3 baselines measured on held-out set | ML lead | `reports/baselines.md` | 3-row comparison table; CedarFix beats all 3 on ≥1 metric per baseline | P2, P3, D3 |
| 7 | Cloud EEP deployment | DevOps lead | Public URL + `infra/` + cost table | External POST works; HTTPS; cost estimate documented | GT2, S5 |
| 8 | T5 experiments 1, 3, 4 (threshold ablation = task 3) | ML lead | `reports/tradeoffs.md` | 4 numeric tables, each with ≥2 metrics | T5 |
| 9 | Edge case tests + Q1 test suite | QA owner | `tests/` + CI green | All 7 edge cases pass; CI gate fails on regression | T6, Q1 |
| 10 | IEP-4 + RAG KB files + prompt versioning | LLM lead | `iep4/`, `prompts/v1.0/`, `data/kb/*.json` | Factual grounding 100% on test set; prompt hash logged in every decision record | T1, G2, M4 |
| 11 | Grafana + Prometheus + induced drift demo | DevOps lead | 4 panels live + `scripts/induce_drift.py` | All 4 panels render; drift alert fires on demand from script | M3 |
| 12 | MLflow worse-challenger demo + model cards | ML lead | 2 model card files + MLflow run with rejected challenger | Promotion gate rejects worse model live during demo | M1, M2, M4 |
| 13 | Demo rehearsal + Q&A drill + backup video | All | 8-min video + demo script + role assignments | 3 full rehearsal runs; 10 professor objection answers practiced | D1, D2, D4, D5 |
| 14 | README + architecture diagram + TRADEOFFS.md + deployment guide | All | 4 documents complete | Professor can read and understand full system in 15 min | M4, GT4 |
| 15 | Git discipline: branches, PRs, CHANGELOG, prompt files | All | Branch graph + PR history + `prompts/` dir | Per-service owner branches; ≥10 reviewed PRs; prompt files committed from day 1 | G1, G2 |

## Professor Defense Script (Expanded)

The original 5 defenses are in "Professor Critiques And Defenses." These 5 additional objections are the highest-probability attacks not covered there.

**Objection 6: "Why not just use GPT-4 for everything?"**

Answer: "That is our B3 baseline — we measured it. ML routes because it produces calibrated confidence and SHAP attribution evidence. LLM explains because it produces fluent multilingual text. Mixing those roles risks unbounded hallucinated routing decisions with untrackable confidence. The separation is enforced by schema: routing fields are set before IEP-4 is ever called."

**Objection 7: "Is your drift detection real or theater?"**

Answer: "Theater, honestly disclosed. With 500 complaints over 5 weeks no real production drift exists. We demonstrate the mechanism by inducing dataset shift: a script artificially shifts class proportions and shows the routing confidence distribution alarm fires. The mechanism is real; the trigger is induced. This is consistent with how academic MLOps courses demonstrate drift detection — the record says induced, not live production."

**Objection 8: "How do I know the LLM didn't make the routing decision?"**

Answer: "Every decision record stores: routing_sector, routing_confidence, prompt_version, prompt_hash, llm_model_version, decision_record_hash, final_human_action. The LLM input is the decision record — routing is already determined before IEP-4 is called. The LLM output populates explanation fields only, never routing fields. The schema enforces this. The DB is live and queryable at demo time."

**Objection 9: "Show me the calibration is real."**

Answer: "Reliability diagram is shown in Act 2. Pre-calibration ECE was [MLflow run value]. Post Platt scaling ECE is [value]. Both with 1000-iteration bootstrap CI. MLflow run [run_id] has the calibration artifact. We show the before/after diagram and the ECE delta."

**Objection 10: "What is the value of the multimodal claim if you have no learned fusion?"**

Answer: "We do not claim learned multimodal fusion. We claim late-fusion multi-signal duplicate detection: text similarity, image issue label match, GPS radius, and time proximity are combined with rule-weighted scoring plus a cross-modal consistency penalty when text issue type and image label disagree. The four-signal combination is what is novel for Lebanese context, not the fusion method. Learned cross-attention fusion is in our future-work section — it requires a paired labeled multimodal training set we do not have."

## Score Scenarios

| Scenario | Score | Conditions |
|---|---:|---|
| Pessimistic | **76** | Sequential HTTP (T4=1), corpus <300, B3 not built, originality not reframed, demo wobbles |
| Realistic | **88** | All 10 build priorities done; corpus at 500; B1+B2+B3 measured; T5 experiments done; demo solid |
| Optimistic | **94** | Above + induced-drift demo + worse-challenger MLflow rejection + Arabizi raised to 80 + bootstrap CIs |
| Theoretical max | **97** | Above + bonus B0=2 from exceptional demo polish |

The plan's original "92–97" range corresponds to the **optimistic** and **theoretical-max** bands only. The **realistic** target is 88.

## Go / No-Go Decision

**Recommendation: GO, conditional on 5 pre-implementation fixes.**

| Fix | Action | Deadline |
|---|---|---|
| 1 | Score targets and overclaiming language updated in plan (done) | Before any code |
| 2 | Differentiation vs Prior Art framing referenced in demo script | Before demo rehearsal |
| 3 | Commit async skeleton (Docker Compose + Redis Streams) in Week 1 | End of Week 1 — T4 lives or dies here |
| 4 | Start corpus labeling in Week 1 | Week 1 — 60 person-hours cannot be compressed |
| 5 | Add B3 baseline measurement to evaluation plan (done) | Before evaluation runs begin |

**If async skeleton is not committed by end of Week 1: reduce scope.** Drop IEP-4 LLM and replace with template-only explanation. That protects the AI spine (T1, T3, T4) and targets ~85 / 100.

**If corpus labeling does not start Week 1: reduce corpus to 300 and document the ECE confidence band widening honestly.**

Realistic score without any fixes (plan as-written, no implementation): **76 / 100**.
Realistic score with fixes + 10 build priorities executed: **88 / 100**.
Optimistic ceiling with all above + worse-challenger + induced-drift + bootstrap CIs: **94 / 100**.
