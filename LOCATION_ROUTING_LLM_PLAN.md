# Location, Routing, and LLM Operations Plan

## Goals

- Let users report either at their current device location or at another typed location.
- Use user-provided/resolved location as the authority for routing.
- Keep LLM-extracted location as an evaluation signal, not the routing authority.
- Prepare for multi-complaint submissions, response-time monitoring, LLM response evaluation, and LLM version rollout.

## Location Support

1. Dashboard asks:
   - Complaint is at my current location: use device coordinates.
   - Complaint is somewhere else: user enters the complaint location as text.
2. Gateway resolves submitted location before the pipeline:
   - Coordinates: reverse geocode with Google Maps when `GOOGLE_MAPS_API_KEY` is configured.
   - Manual text: geocode with Google Maps when configured, otherwise use the local Lebanon location lookup.
   - Fallback: keep the raw manual text/district so routing still has location context.
3. Routing receives:
   - `location_municipality`
   - `location_district`
   - `location_governorate`
   - `location_mentions`
   - source/confidence metadata for audit
4. Routing must prefer submitted/resolved location over LLM-extracted text location.
5. LLM location output is compared against submitted/resolved location:
   - exact/admin match: useful positive eval sample
   - mismatch: useful correction sample
   - LLM null: no location fine-tuning sample unless other labels exist

## Multiple Complaints

1. Add a pre-routing complaint splitter.
2. Ask the LLM to return a JSON array only when the text contains multiple independent complaints.
3. Treat each extracted complaint as a separate case linked to the original submission.
4. Reconcile image detections with each text complaint:
   - image supports one complaint
   - text-only complaints remain text-only
   - contradictions or unclear mapping go to review

## LLM Evaluation

1. Validate every LLM response against a strict schema.
2. Store model name/version, prompt version, temperature, latency, and raw validated JSON.
3. Maintain golden datasets for:
   - issue classification
   - location extraction
   - multi-complaint splitting
   - text-image contradiction detection
   - routing candidate selection
4. Use submitted/resolved location as ground truth for evaluating LLM location extraction.
5. Use admin corrections to build fine-tuning examples only when the corrected label is reliable.

## LLM Versioning and Deployment

Use versioned model and prompt identifiers:

- `QWEN_MODEL`
- `QWEN_MODEL_VERSION`
- `TEXT_PROMPT_VERSION`
- `ROUTING_PROMPT_VERSION`
- `VLM_MODEL`
- `VLM_MODEL_VERSION`

Recommended rollout:

1. Shadow mode:
   - Current model makes production decisions.
   - New model runs in parallel and logs outputs only.
2. Offline evaluation:
   - Compare against golden datasets and admin-reviewed cases.
3. Canary:
   - Route 5% of eligible low-risk complaints to the new model.
   - Keep high-risk/low-confidence cases on the stable model or human review.
4. Progressive rollout:
   - 5% -> 25% -> 50% -> 100% if quality and latency hold.
5. Automatic rollback:
   - rollback on schema failures, latency regression, route accuracy drop, contradiction increase, or review volume spike.

## Service Monitoring

Track per service and end-to-end:

- p50/p95/p99 latency
- timeout count
- error count
- LLM schema failure count
- Qdrant retrieval latency
- routing no-candidate count
- human-review rate

Services to monitor:

- gateway
- text understanding
- image understanding
- embedding
- clustering
- priority
- routing
- explanation/review
- Qdrant/Postgres

