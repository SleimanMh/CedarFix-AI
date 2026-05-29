# CedarFix AI — Architecture Improvement Plan (v2)

> **Scope:** Six targeted improvements, no fine-tuning. All proposals maintain the
> existing FastAPI microservice layout, Docker Compose, PostgreSQL, Qdrant, MLflow,
> Prometheus, Grafana, and human review queue. Every section includes exact file
> paths, code patches, schema changes, DB migrations, prompts, env vars, and
> test examples.

---

## Table of Contents

1. [Location Normalization](#1-location-normalization)
2. [RAG-Based Lebanon Routing](#2-rag-based-lebanon-routing)
3. [VLM Image Understanding](#3-vlm-image-understanding)
4. [Confidence Bundle](#4-confidence-bundle)
5. [IEP-0 — Spam / Fake / Harmful Gate](#5-iep-0--spam--fake--harmful-gate)
6. [LLM Duplicate Judge (Ambiguous Only)](#6-llm-duplicate-judge-ambiguous-only)
7. [IEP-1 Unknown Complaint Type Handling](#7-iep-1-unknown-complaint-type-handling)
8. [Database Migrations](#8-database-migrations)
9. [Docker Compose & Environment Variables](#9-docker-compose--environment-variables)
10. [Testing Examples](#10-testing-examples)

---

## 1. IEP-2 — VLM-Based Image Understanding

### Problem with Current Design

CLIP zero-shot excels at embedding and rough semantic similarity but is poor at:
- Explaining *why* something is a pothole vs. road damage
- Detecting fake, AI-generated, or harmful images
- Answering nuanced alignment questions ("does this image match the text?")

### Proposed Architecture: Two-Phase IEP-2

```
Image Input
    │
    ├── Phase 1 — CLIP (always runs, fast)
    │     ├── Generate 512-dim embedding   → stored, used for retrieval
    │     ├── Quick quality check          → reject unusable images early
    │     └── Initial severity signal      → LOW/MED/HIGH rough estimate
    │
    └── Phase 2 — Qwen2.5-VL (runs if Phase 1 says image is usable)
          ├── Scene reasoning              → structured JSON output
          ├── Harmful/fake detection       → moderation flag
          └── Text-image alignment check  → when text is also available
```

CLIP stays as the embedding engine. Qwen2.5-VL becomes the reasoning engine.
The two are not interchangeable — use each for what it does best.

### Qwen2.5-VL Deployment

Self-host on RunPod alongside the existing Qwen text model, or use the same
RunPod instance if GPU memory allows. Endpoint format is identical
(OpenAI-compatible `/v1/chat/completions` with `image_url` in the message).

Environment variables to add to `image-understanding` service:
```
VLM_BASE_URL=https://<runpod-id>-8000.proxy.runpod.net/v1
VLM_MODEL=Qwen/Qwen2.5-VL-3B-Instruct
VLM_ENABLED=true
VLM_TIMEOUT=25
```

### Phase 2 — VLM Classification Prompt

```python
VLM_CLASSIFY_SYSTEM = """\
You are an AI assistant for CedarFix, a Lebanese public infrastructure complaint platform.
Analyze the image and return ONLY a valid JSON object — no explanation, no markdown.

JSON schema (all fields required):
{
  "image_type": "<infrastructure_damage | selfie | indoor_scene | nature_landscape | food | screenshot | text_document | ai_generated | other>",
  "is_valid_complaint_image": <true|false>,
  "is_harmful": <true|false>,
  "is_ai_generated": <true|false>,
  "damage_visible": <true|false>,
  "visual_category": "<roads | drainage | electricity | water | sanitation | public_safety | other | none>",
  "visual_subcategory": "<pothole | road_damage | flooding | garbage | traffic_light | sidewalk | streetlight | pipe_leak | other | none>",
  "damage_severity": "<LOW | MEDIUM | HIGH | CRITICAL | NONE>",
  "location_cues": ["<any visible location identifiers: street signs, landmarks, Lebanese text>"],
  "confidence": <0.0–1.0>,
  "reasoning": "<one sentence explanation>"
}

Rules:
- is_ai_generated: true if the image looks artificially generated or staged
- is_harmful: true for violence, nudity, political symbols, personal faces
- damage_visible: false if image is blurry, too dark, or shows no damage
- confidence reflects certainty of visual_category + visual_subcategory
"""

def vlm_classify_prompt(image_b64: str) -> list:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                },
                {
                    "type": "text",
                    "text": "Analyze this image for an infrastructure complaint."
                }
            ]
        }
    ]
```

### Phase 2 — VLM Alignment Prompt (Text + Image)

Called by IEP-3 when it needs to resolve a CLIP UNCERTAIN or CONTRADICTS result.

```python
VLM_ALIGN_SYSTEM = """\
You are a multimodal alignment judge for a Lebanese infrastructure complaint platform.
You receive a complaint text and an image. Determine whether the image actually
shows what the text describes.

Return ONLY a valid JSON object:
{
  "alignment": "<confirms | partial | contradicts | unrelated>",
  "text_issue": "<what the text describes>",
  "image_issue": "<what the image actually shows>",
  "confidence": <0.0–1.0>,
  "reason": "<one sentence>"
}

Definitions:
- confirms:    image clearly shows the same infrastructure issue the text describes
- partial:     image is from the same category but not the exact issue (e.g. text=pothole, image=cracked road)
- contradicts: image clearly shows a DIFFERENT type of issue than the text
- unrelated:   image has nothing to do with infrastructure
"""

def vlm_align_prompt(complaint_text: str, image_b64: str) -> list:
    return [
        {
            "role": "user",
            "content": [
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}
                },
                {
                    "type": "text",
                    "text": f'Complaint text: "{complaint_text}"\n\nDoes this image match the complaint?'
                }
            ]
        }
    ]
```

### Updated `ImageUnderstandingResult` Schema

Add to `schemas.py`:

```python
class VLMImageAnalysis(BaseModel):
    image_type: str = "other"
    is_valid_complaint_image: bool = False
    is_harmful: bool = False
    is_ai_generated: bool = False
    damage_visible: bool = False
    visual_category: str = "other"
    visual_subcategory: str = "other"
    damage_severity: SeverityLevel = SeverityLevel.LOW
    location_cues: List[str] = []
    confidence: float = 0.0
    reasoning: str = ""
    vlm_available: bool = False   # False = fell back to CLIP only

class ImageUnderstandingResult(BaseModel):
    # ... existing fields ...
    vlm_analysis: Optional[VLMImageAnalysis] = None
    clip_text_embedding: Optional[List[float]] = None
```

### Contradiction Logic (Updated)

Replace the current binary alignment check with a three-tier system:

```python
def decide_contradiction(
    clip_alignment: AlignmentStatus,
    clip_similarity: float,
    vlm_alignment: Optional[str],   # "confirms|partial|contradicts|unrelated"
    vlm_confidence: float,
) -> tuple[bool, str]:
    """
    Returns (is_contradiction, reason).
    """
    # Tier 1: Strong CLIP signal — trust it directly
    if clip_similarity >= 0.75:
        return False, "CLIP high similarity — aligned"
    if clip_similarity <= 0.25 and clip_alignment == AlignmentStatus.CONTRADICTS:
        return True, "CLIP strong contradiction"

    # Tier 2: Ambiguous CLIP — use VLM if available
    if vlm_alignment and vlm_confidence >= 0.7:
        if vlm_alignment == "contradicts":
            return True, f"VLM detected contradiction (confidence {vlm_confidence:.0%})"
        if vlm_alignment == "unrelated":
            return True, "VLM: image unrelated to complaint"
        return False, f"VLM: {vlm_alignment}"

    # Tier 3: Both uncertain — forward to human review rather than auto-reject
    return False, "insufficient evidence"
```

### Confidence Handling for Images

```python
def compute_image_confidence(
    clip_quality_score: float,
    clip_classification_confidence: float,
    vlm_confidence: Optional[float],
    is_ai_generated: bool,
    damage_visible: bool,
) -> float:
    if is_ai_generated:
        return 0.05   # near-zero — flag for moderation

    base = clip_classification_confidence * clip_quality_score

    if vlm_confidence is not None:
        # VLM result is more reliable — blend, weighted toward VLM
        blended = 0.3 * base + 0.7 * vlm_confidence
    else:
        blended = base

    if not damage_visible:
        blended *= 0.6   # penalize unclear images

    return round(min(blended, 1.0), 3)
```

### Latency Budget

| Step | Expected latency |
|---|---|
| CLIP embedding + zero-shot | 50–200 ms |
| Qwen2.5-VL classification | 1–4 s |
| Qwen2.5-VL alignment check | 1–3 s (only on UNCERTAIN/CONTRADICTS) |
| **Total IEP-2 (with image)** | **2–7 s** |
| **Total IEP-2 (no image)** | **< 50 ms** |

IEP-1 and IEP-2 run in parallel, so the 2–7 s IEP-2 budget is hidden behind IEP-1's Qwen text call.

---

## 2. IEP-4 — LLM-Judge Duplicate Detection

### Problem with Current Design

Pure cosine similarity treats "There's a pothole on Hamra" and "Large hole on Bliss Street" as unrelated (different wording, similar location). An LLM reading both texts would immediately recognize them as the same incident.

### Proposed Architecture: Retrieve → Filter → Judge

```
New complaint arrives
    │
    ├── Stage 1: Qdrant retrieval
    │     Query: fused_embedding (768-dim)
    │     Top-K: 10 candidates (cosine > 0.55)
    │
    ├── Stage 2: Fast filters (no LLM)
    │     ├── Geo proximity filter: keep only within 1 km
    │     ├── Type match filter: keep same complaint_type
    │     └── Time filter: prefer last 30 days
    │     Result: 0–5 strong candidates
    │
    ├── Stage 3: Composite score (no LLM)
    │     Score each candidate (see formula below)
    │     If top_score >= 0.92 AND type matches → auto DUPLICATE (skip LLM)
    │     If top_score < 0.60 → auto NEW (skip LLM)
    │
    └── Stage 4: LLM Judge (only for 0.60 ≤ score < 0.92)
          → DUPLICATE | RELATED | NEW + confidence + reason
```

### Stage 3 — Composite Scoring Formula

```python
def composite_score(
    cosine_sim: float,       # 0–1 from Qdrant
    type_match: bool,        # same complaint_type?
    geo_dist_km: float,      # haversine distance
    days_ago: int,           # how old is the candidate?
) -> float:
    score = cosine_sim

    # Type match bonus
    if type_match:
        score = min(score + 0.08, 1.0)

    # Geo proximity bonus (only if GPS available)
    if geo_dist_km < 0.1:      # < 100m
        score = min(score + 0.15, 1.0)
    elif geo_dist_km < 0.5:    # < 500m
        score = min(score + 0.08, 1.0)
    elif geo_dist_km > 2.0:    # > 2 km
        score = max(score - 0.10, 0.0)

    # Time recency factor
    if days_ago > 90:
        score *= 0.85   # old reports less likely to be same active issue
    elif days_ago > 30:
        score *= 0.92

    return round(score, 3)
```

### Stage 4 — LLM Judge Prompt

```python
DUPLICATE_JUDGE_SYSTEM = """\
You are a deduplication judge for CedarFix, a Lebanese public infrastructure platform.
You receive two infrastructure complaint texts and must decide if they report the same physical issue.

Return ONLY a valid JSON object:
{
  "decision": "<DUPLICATE | RELATED | NEW>",
  "confidence": <0.0–1.0>,
  "reason": "<one sentence>"
}

Definitions:
- DUPLICATE: both complaints almost certainly describe the same physical defect at the same location
- RELATED:   both describe issues in the same general area or of the same type, but are likely different occurrences
- NEW:       the new complaint describes a different issue than the candidate

Important:
- Different wording does NOT mean different incident — focus on location and damage type
- If GPS coordinates are provided and are close (< 200m), weight that heavily
- "pothole on Hamra near the pharmacy" and "big hole in Hamra street" are likely DUPLICATE
- "pothole on Hamra" and "pothole in Verdun" are likely NEW (different districts)
"""

def duplicate_judge_prompt(
    new_text: str,
    new_location: str,
    new_type: str,
    candidate_text: str,
    candidate_location: str,
    candidate_type: str,
    cosine_score: float,
    geo_dist_km: Optional[float],
) -> str:
    geo_note = f"GPS distance: {geo_dist_km*1000:.0f}m apart." if geo_dist_km is not None else "No GPS data."
    return f"""New complaint [{new_type}] at {new_location}:
"{new_text}"

Candidate complaint [{candidate_type}] at {candidate_location}:
"{candidate_text}"

Embedding similarity: {cosine_score:.2f}. {geo_note}
Are these the same incident?"""
```

### Updated Scoring Pipeline

```python
class DuplicateScore(BaseModel):
    candidate_id: str
    cosine_similarity: float
    composite_score: float
    geo_dist_km: Optional[float]
    type_match: bool
    llm_decision: Optional[str]   # "DUPLICATE|RELATED|NEW"
    llm_confidence: Optional[float]
    final_decision: DuplicateDecisionEnum
    final_confidence: float

def final_duplicate_decision(score: DuplicateScore) -> DuplicateDecisionEnum:
    # LLM result takes precedence if high confidence
    if score.llm_decision and score.llm_confidence >= 0.80:
        if score.llm_decision == "DUPLICATE":
            return DuplicateDecisionEnum.DUPLICATE
        if score.llm_decision == "RELATED":
            return DuplicateDecisionEnum.RELATED_SAME_CLUSTER
        return DuplicateDecisionEnum.NEW_INCIDENT

    # Fall back to composite score
    if score.composite_score >= 0.92:
        return DuplicateDecisionEnum.DUPLICATE
    if score.composite_score >= 0.72:
        return DuplicateDecisionEnum.RELATED_SAME_CLUSTER
    return DuplicateDecisionEnum.NEW_INCIDENT
```

### Latency-Aware Design

The LLM judge is the most expensive step. Keep it bounded:

```python
LLM_JUDGE_TIMEOUT = 8.0   # seconds

# Only judge the top-1 candidate to minimize latency
# If top-1 is already auto-DUPLICATE (≥0.92) or auto-NEW (<0.60),
# skip the LLM entirely — most requests take this path

# For the ambiguous middle range (0.60–0.92):
# send only the top-1 candidate to LLM, not all K
# this caps latency at one LLM call per complaint
```

Expected IEP-4 latency:
- Auto-DUPLICATE/NEW path: **20–80 ms** (Qdrant only)
- LLM judge path: **2–10 s** (one Qwen call)
- ~70% of real-world submissions hit the auto path

---

## 3. IEP-6 — RAG-Based Lebanon Routing

### Problem with Current Design

The static routing table cannot:
- Distinguish Beirut Municipality roads from CDR (Council for Development and Reconstruction) highways
- Route to district-level entities (Aley, Baabda, Jbeil municipalities)
- Explain *why* it chose an entity beyond a simple rule match
- Adapt when new entities are added or responsibilities shift

### Proposed Architecture

```
Routing Knowledge Base
    ├── Qdrant collection: "routing_knowledge"
    │     One document per (entity, responsibility_area) pair
    │     Metadata: entity, jurisdiction, complaint_types, districts
    │
    ├── PostgreSQL table: routing_entities
    │     Full entity registry with contact info, geographic scope
    │
    └── Static fallback table (current logic — always available)

Routing Flow:
    1. Build retrieval query from complaint
    2. Qdrant ANN search → top-5 routing documents
    3. LLM reads documents + complaint → routing decision JSON
    4. Confidence check → auto-route or human review
    5. Store routing_rationale with sources cited
```

### Routing Knowledge Base — Document Schema

Each document in Qdrant's `routing_knowledge` collection:

```python
class RoutingKnowledgeDoc(BaseModel):
    doc_id: str
    entity_name: str           # "Ministry of Public Works"
    entity_type: str           # "ministry | municipality | utility | security | other"
    short_name: str            # "MoPW"
    
    # Geographic scope
    governs_nationally: bool = False
    governorates: List[str] = []   # ["Beirut", "Mount Lebanon"]
    districts: List[str] = []      # ["Metn", "Aley", "Baabda"]
    municipalities: List[str] = [] # ["Beirut", "Jdeideh"]
    
    # Responsibility
    complaint_types: List[str]
    keywords: List[str]
    NOT_responsible_for: List[str] = []  # important to include
    
    # Description for LLM context
    description: str   # 2–4 sentence plain text
    
    # Contact
    hotline: Optional[str] = None
    email: Optional[str] = None
    
    # Embedding (built from description + keywords + complaint_types)
    embedding: List[float]  # 768-dim, stored separately in Qdrant payload
```

### Sample Knowledge Documents

```python
ROUTING_DOCS = [
    {
        "entity_name": "Ministry of Public Works and Transport",
        "entity_type": "ministry",
        "short_name": "MoPW",
        "governs_nationally": True,
        "complaint_types": ["pothole", "road_damage", "flooding", "sidewalk_damage"],
        "keywords": ["highway", "national road", "autoroute", "bridge", "tunnel", "CDR", "asphalt"],
        "NOT_responsible_for": ["electricity", "water", "internet", "garbage"],
        "description": (
            "The Ministry of Public Works is responsible for all national and "
            "inter-city roads, highways, bridges, and tunnels across Lebanon. "
            "In practice, the Council for Development and Reconstruction (CDR) "
            "executes many of their road projects. Municipal streets within "
            "Beirut proper fall under Beirut Municipality, not this Ministry."
        ),
    },
    {
        "entity_name": "Beirut Municipality",
        "entity_type": "municipality",
        "short_name": "BM",
        "governs_nationally": False,
        "governorates": ["Beirut"],
        "districts": ["Beirut"],
        "complaint_types": ["pothole", "road_damage", "waste_accumulation", "sidewalk_damage", "flooding"],
        "keywords": ["Beirut", "Hamra", "Verdun", "Ashrafieh", "Gemmayzeh", "Mar Mikhael", "Cola",
                     "Corniche", "Rue", "street", "Beirut city", "downtown"],
        "NOT_responsible_for": ["electricity", "internet", "national highway"],
        "description": (
            "Beirut Municipality manages all streets, sidewalks, waste collection, "
            "and local infrastructure within the Beirut administrative boundary. "
            "It handles Hamra, Verdun, Ashrafieh, Gemmayzeh, Corniche, Downtown, "
            "and all neighborhoods within Beirut city limits."
        ),
    },
    {
        "entity_name": "Electricite Du Liban",
        "entity_type": "utility",
        "short_name": "EDL",
        "governs_nationally": True,
        "complaint_types": ["electricity_outage", "streetlight"],
        "keywords": ["electricity", "power", "blackout", "EDL", "كهرباء", "street light", "lamp post"],
        "NOT_responsible_for": ["roads", "water", "internet"],
        "description": (
            "Electricite Du Liban is the state electricity utility responsible for "
            "power distribution across Lebanon. They handle outages, faulty street "
            "lights, and electrical infrastructure issues nationwide. "
            "Private generators are not their responsibility."
        ),
    },
    {
        "entity_name": "Internal Security Forces",
        "entity_type": "security",
        "short_name": "ISF",
        "governs_nationally": True,
        "complaint_types": ["traffic_incident", "traffic_light", "public_safety"],
        "keywords": ["accident", "crash", "ISF", "police", "traffic", "road block",
                     "dangerous", "safety", "قوى الأمن"],
        "NOT_responsible_for": ["electricity", "water", "garbage", "road repair"],
        "description": (
            "The Internal Security Forces (ISF) handle road accidents, traffic "
            "management, broken traffic signals that pose immediate safety risks, "
            "and any public safety emergency. They coordinate with municipalities "
            "for traffic light repairs but respond first."
        ),
    },
    # ... add all entities similarly
]
```

### Retrieval Query Construction

```python
def build_routing_query(
    complaint_type: str,
    category: str,
    location_district: Optional[str],
    location_governorate: Optional[str],
    keywords: List[str],
    original_text: str,
) -> str:
    """Build a semantic query for the routing knowledge base."""
    parts = [
        f"complaint type: {complaint_type}",
        f"category: {category}",
    ]
    if location_district:
        parts.append(f"district: {location_district}")
    if location_governorate:
        parts.append(f"governorate: {location_governorate}")
    if keywords:
        parts.append(f"keywords: {', '.join(keywords[:5])}")
    # Append a trimmed version of the original text for semantic richness
    parts.append(f"complaint: {original_text[:200]}")
    return " | ".join(parts)
```

### LLM Routing Prompt

```python
ROUTING_SYSTEM = """\
You are a routing expert for CedarFix, a Lebanese public infrastructure complaint platform.
You will receive a complaint and a list of potential responsible entities retrieved from
a Lebanese public sector knowledge base.

Return ONLY a valid JSON object:
{
  "primary_entity": "<exact entity name from the options>",
  "secondary_entity": "<optional second entity, or null>",
  "confidence": <0.0–1.0>,
  "rationale": "<2–3 sentence explanation citing specific responsibilities>",
  "requires_human_review": <true|false>,
  "review_reason": "<why human review is needed, or null>"
}

Rules:
- Choose from the provided entity options only. Do not invent entities.
- If the location is outside Beirut, prefer the correct regional municipality.
- If two entities share responsibility, name both (primary + secondary).
- confidence < 0.65 → set requires_human_review: true
- If the complaint is ambiguous between entities, explain in review_reason.
"""

def routing_prompt(complaint, retrieved_docs: List[RoutingKnowledgeDoc]) -> str:
    docs_text = "\n\n".join([
        f"Entity: {d.entity_name}\n"
        f"Type: {d.entity_type}\n"
        f"Geographic scope: {d.governorates or 'nationwide'}\n"
        f"Handles: {', '.join(d.complaint_types)}\n"
        f"Does NOT handle: {', '.join(d.NOT_responsible_for)}\n"
        f"Details: {d.description}"
        for d in retrieved_docs
    ])
    
    return f"""Complaint type: {complaint.complaint_type}
Location: {complaint.location_district or 'unknown'}, {complaint.location_governorate or 'Lebanon'}
Text: "{complaint.original_text}"

Routing options retrieved from the Lebanese public sector database:
{docs_text}

Which entity should handle this complaint?"""
```

### Routing Confidence Logic

```python
ROUTING_AUTO_THRESHOLD = 0.82   # was 0.85 — RAG rationale earns slightly lower bar
ROUTING_REVIEW_THRESHOLD = 0.60

def decide_routing(
    llm_confidence: float,
    llm_entity: str,
    static_fallback_entity: str,
    static_fallback_confidence: float,
) -> RoutingResult:
    if llm_confidence >= ROUTING_AUTO_THRESHOLD:
        return RoutingResult(primary_entity=llm_entity, confidence=llm_confidence,
                             auto_routed=True, source="rag")
    
    if llm_confidence >= ROUTING_REVIEW_THRESHOLD:
        # LLM uncertain — compare with static fallback
        if llm_entity == static_fallback_entity:
            # Both agree → boost confidence slightly
            return RoutingResult(primary_entity=llm_entity,
                                 confidence=min(llm_confidence + 0.08, 0.90),
                                 auto_routed=True, source="rag+static")
        else:
            # Disagreement → human review
            return RoutingResult(primary_entity=RoutingEntity.HUMAN_REVIEW,
                                 confidence=llm_confidence, auto_routed=False,
                                 requires_review=True, source="conflict")
    
    # Low confidence — human review
    return RoutingResult(primary_entity=RoutingEntity.HUMAN_REVIEW,
                         confidence=llm_confidence, auto_routed=False,
                         requires_review=True, source="low_confidence")
```

### Chunking Strategy for the Knowledge Base

```
Each entity gets multiple documents (one per major responsibility area):

  "Beirut Municipality — Roads & Sidewalks"
  "Beirut Municipality — Waste & Sanitation"
  "Ministry of Public Works — Highways & Bridges"
  "Ministry of Public Works — Urban Roads"
  "EDL — Power Outages"
  "EDL — Street Lighting"
  ...

Each document: ~200–400 words
Embedding: built from (description + keywords + complaint_types + district_list)
Qdrant metadata filter: entity_type, governorate, complaint_type
```

### Database Schema — routing_knowledge

```sql
CREATE TABLE IF NOT EXISTS routing_knowledge (
    id              VARCHAR(36) PRIMARY KEY,
    entity_name     VARCHAR(100) NOT NULL,
    entity_type     VARCHAR(30),
    short_name      VARCHAR(20),
    governs_nat     BOOLEAN DEFAULT FALSE,
    governorates    JSONB DEFAULT '[]',
    districts       JSONB DEFAULT '[]',
    complaint_types JSONB DEFAULT '[]',
    keywords        JSONB DEFAULT '[]',
    description     TEXT,
    hotline         VARCHAR(50),
    email           VARCHAR(100),
    qdrant_point_id VARCHAR(50),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

---

## 4. Cross-Pipeline Confidence System

### Problem with Current Design

Single per-stage confidence numbers cannot answer: "how confident is the *overall* pipeline in this decision?" — which is what determines whether to auto-route or send to human review.

### Proposed ConfidenceBundle Schema

Add to `schemas.py`:

```python
class StageConfidence(BaseModel):
    """Confidence for a single pipeline stage."""
    score: float = 0.0              # 0–1
    method: str = "unknown"         # "llm" | "rule_based" | "clip" | "qdrant"
    reliable: bool = True           # False = fell back to less reliable method

class ConfidenceBundle(BaseModel):
    """Assembled confidence scores across the entire pipeline."""
    # Stage-level
    text_type: StageConfidence = StageConfidence()
    text_location: StageConfidence = StageConfidence()
    image_classification: StageConfidence = StageConfidence()
    image_alignment: StageConfidence = StageConfidence()
    duplicate: StageConfidence = StageConfidence()
    routing: StageConfidence = StageConfidence()
    
    # Aggregate
    final: float = 0.0
    weakest_stage: str = ""         # name of the lowest-confidence stage
    review_triggered_by: str = ""   # which stage caused review, if any
```

Add `confidence_bundle: Optional[ConfidenceBundle] = None` to `ComplaintDecision`.

### Final Confidence Aggregation

```python
def aggregate_confidence(bundle: ConfidenceBundle, has_image: bool) -> float:
    """
    Weighted geometric mean. Geometric mean penalizes any single weak stage
    harder than arithmetic mean — appropriate for a pipeline where one bad
    stage should pull the whole result down.
    """
    import math

    stages = [
        (bundle.text_type.score,          0.30),  # text classification weight
        (bundle.text_location.score,       0.10),
        (bundle.routing.score,             0.40),  # routing is the final decision
        (bundle.duplicate.score,           0.20),
    ]

    if has_image:
        # Image adds weight, redistributed from text and routing
        stages = [
            (bundle.text_type.score,          0.25),
            (bundle.text_location.score,       0.08),
            (bundle.image_classification.score, 0.17),
            (bundle.image_alignment.score,      0.10),
            (bundle.routing.score,             0.30),
            (bundle.duplicate.score,           0.10),
        ]

    # Weighted geometric mean
    log_sum = sum(w * math.log(max(s, 0.01)) for s, w in stages)
    weight_sum = sum(w for _, w in stages)
    final = math.exp(log_sum / weight_sum)

    # Penalty for rule-based fallbacks (less reliable than LLM)
    rule_based_stages = sum(
        1 for stage in [bundle.text_type, bundle.routing, bundle.image_classification]
        if not stage.reliable
    )
    if rule_based_stages >= 2:
        final *= 0.90   # 10% penalty for multiple rule-based fallbacks

    return round(min(final, 1.0), 3)
```

### Review Thresholds

```python
REVIEW_RULES = [
    # (condition, status, reason)
    (lambda b: b.routing.score < 0.60,           "HUMAN_REVIEW",        "Low routing confidence"),
    (lambda b: b.text_type.score < 0.40,         "NEEDS_CLARIFICATION", "Text classification uncertain"),
    (lambda b: b.image_alignment.score < 0.45,   "HUMAN_REVIEW",        "Text-image alignment weak"),
    (lambda b: b.final < 0.50,                   "HUMAN_REVIEW",        "Overall pipeline confidence low"),
    (lambda b: not b.text_type.reliable 
               and not b.routing.reliable,        "HUMAN_REVIEW",        "Both LLMs unavailable — rule-based only"),
]

def should_human_review(bundle: ConfidenceBundle) -> tuple[bool, str]:
    for condition, status, reason in REVIEW_RULES:
        if condition(bundle):
            return True, reason
    return False, ""
```

### Confidence Calibration Without Fine-tuning

Track per-complaint-type accuracy using admin corrections:

```sql
-- Materialized view refreshed daily
CREATE MATERIALIZED VIEW type_correction_rates AS
SELECT 
    complaint_type,
    COUNT(*) AS total,
    SUM(CASE WHEN ac.id IS NOT NULL THEN 1 ELSE 0 END) AS corrected,
    ROUND(1.0 - SUM(CASE WHEN ac.id IS NOT NULL THEN 1 ELSE 0 END)::numeric / COUNT(*), 3) AS accuracy
FROM complaints c
LEFT JOIN admin_corrections ac ON c.id = ac.complaint_id
WHERE c.created_at >= NOW() - INTERVAL '30 days'
GROUP BY complaint_type;
```

Apply as a calibration multiplier at routing time:

```python
async def calibrated_routing_confidence(
    raw_confidence: float,
    complaint_type: str,
    db_session
) -> float:
    row = await db_session.execute(
        "SELECT accuracy FROM type_correction_rates WHERE complaint_type = :t",
        {"t": complaint_type}
    )
    type_accuracy = row.scalar() or 1.0
    # Shrink confidence toward the historical accuracy for this type
    # Formula: calibrated = raw * (0.7 + 0.3 * type_accuracy)
    return round(raw_confidence * (0.7 + 0.3 * type_accuracy), 3)
```

---

## 5. IEP-0 — Spam / Fake / Harmful Complaint Detection

### New Service: `moderation_service` (IEP-0)

This runs **before** IEP-1/IEP-2, as the very first gate after the Gateway
receives the complaint. It is intentionally fast and uses heuristics first,
escalating to LLM only when needed.

```
Gateway receives complaint
    │
    ├── IEP-0: Moderation Gate ──────────────────────────────
    │     ├── Layer 1: Fast heuristics (< 5 ms)
    │     ├── Layer 2: Reputation check (DB lookup, < 10 ms)
    │     ├── Layer 3: LLM text moderation (1–3 s, only if flagged)
    │     └── Layer 4: VLM image moderation (2–5 s, only if image + flagged)
    │
    │     Decision: PASS | FLAG_FOR_REVIEW | REJECT
    │
    └── If PASS → IEP-1/IEP-2 (normal pipeline)
        If FLAG → IEP-1/IEP-2 + human review queue
        If REJECT → immediate response, do not store
```

### Layer 1 — Fast Heuristics

```python
class HeuristicsResult(NamedTuple):
    flagged: bool
    flags: List[str]   # human-readable reasons

def run_heuristics(text: str, user_id: Optional[str], db) -> HeuristicsResult:
    flags = []

    # 1. Text quality
    if len(text.strip()) < 15:
        flags.append("text_too_short")
    if text.upper() == text and len(text) > 20:
        flags.append("all_caps")
    if sum(1 for c in text if c in "!?") > 5:
        flags.append("excessive_punctuation")

    # 2. Repetition (exact duplicate from same session)
    text_hash = hashlib.sha256(text.strip().lower().encode()).hexdigest()
    if db.exists("text_hash_cache", text_hash, ttl_hours=24):
        flags.append("exact_duplicate_text")

    # 3. Keyword blocklist (political, personal harassment)
    BLOCKED_TERMS = [
        "hezbollah", "kataeb", "amal", "lbci", "vote for", "انتخب",
        # add more as needed — keep this minimal and carefully curated
    ]
    text_lower = text.lower()
    for term in BLOCKED_TERMS:
        if term in text_lower:
            flags.append(f"blocked_term:{term}")
            break

    return HeuristicsResult(flagged=len(flags) > 0, flags=flags)
```

### Layer 2 — Reputation Check

```sql
CREATE TABLE IF NOT EXISTS user_reputation (
    user_id             VARCHAR(100) PRIMARY KEY,
    first_seen          TIMESTAMP DEFAULT NOW(),
    total_submissions   INTEGER DEFAULT 0,
    valid_submissions   INTEGER DEFAULT 0,
    spam_count          INTEGER DEFAULT 0,
    moderation_flags    INTEGER DEFAULT 0,
    banned_until        TIMESTAMP,
    reputation_score    FLOAT GENERATED ALWAYS AS (
        CASE WHEN total_submissions = 0 THEN 1.0
             ELSE ROUND(valid_submissions::numeric / total_submissions, 3)
        END
    ) STORED
);

CREATE INDEX ON user_reputation(banned_until);
```

```python
def check_reputation(user_id: Optional[str], db) -> tuple[bool, str]:
    """Returns (should_block, reason). Anonymous users get neutral score."""
    if not user_id:
        return False, ""
    
    rep = db.get_reputation(user_id)
    if rep is None:
        return False, ""
    
    # Banned user
    if rep.banned_until and rep.banned_until > datetime.utcnow():
        return True, f"User banned until {rep.banned_until.isoformat()}"
    
    # Very low reputation
    if rep.total_submissions >= 5 and rep.reputation_score < 0.25:
        return False, "low_reputation_flag"   # flag, don't block outright
    
    # High spam count
    if rep.spam_count >= 10:
        return True, "repeated_spam"
    
    return False, ""
```

### Layer 3 — LLM Text Moderation Prompt

Only called when heuristics OR reputation checks raise a flag.

```python
MODERATION_SYSTEM = """\
You are a content moderator for CedarFix, a Lebanese public infrastructure platform.
Citizens submit complaints about roads, electricity, water, and other public services.

Analyze the text and return ONLY a valid JSON object:
{
  "is_valid_complaint": <true|false>,
  "is_spam": <true|false>,
  "is_abusive": <true|false>,
  "is_political": <true|false>,
  "is_ai_generated_text": <true|false>,
  "confidence": <0.0–1.0>,
  "reason": "<one sentence>"
}

Definitions:
- is_valid_complaint: describes a real physical infrastructure issue (road, electricity, water, garbage)
- is_spam: repeats itself, is nonsensical, or is clearly a test/bot submission
- is_abusive: contains personal attacks, threats, or harassment
- is_political: promotes a party, candidate, or political agenda unrelated to infrastructure
- is_ai_generated_text: robotic language, suspiciously perfect, or very generic

Important: a complaint can be poorly written AND still be valid. Judge on content, not grammar.
"""

MODERATION_THRESHOLD = 0.75   # confidence required to act on LLM decision
```

### Layer 4 — VLM Image Moderation Prompt

```python
VLM_MODERATION_SYSTEM = """\
You are an image moderator for a public Lebanese infrastructure platform.
Check if the image is appropriate for submission.

Return ONLY a valid JSON object:
{
  "is_appropriate": <true|false>,
  "issues": ["<nudity|violence|political_symbol|unrelated|ai_generated|personal_face>"],
  "confidence": <0.0–1.0>
}

An image is APPROPRIATE if it shows:
  - roads, sidewalks, potholes, cracks, damage
  - flooding, standing water
  - garbage piles, overflowing bins
  - broken traffic lights, street lamps
  - exposed pipes, water leaks
  - any public infrastructure

An image is NOT appropriate if it shows:
  - People's faces (privacy violation)
  - Violence or graphic content
  - Political banners or symbols
  - Food, interiors, selfies, or completely unrelated scenes
  - Clearly AI-generated fake damage images
"""
```

### Moderation Decision Logic

```python
class ModerationDecision(str, Enum):
    PASS = "pass"
    FLAG = "flag_for_review"
    REJECT = "reject"

def moderation_decision(
    heuristic_flags: List[str],
    reputation_block: bool,
    llm_result: Optional[dict],
    vlm_result: Optional[dict],
) -> tuple[ModerationDecision, str]:
    
    # Hard blocks
    if reputation_block:
        return ModerationDecision.REJECT, "user_banned"
    
    if llm_result and llm_result.get("confidence", 0) >= MODERATION_THRESHOLD:
        if llm_result.get("is_abusive"):
            return ModerationDecision.REJECT, "abusive_content"
        if llm_result.get("is_spam") and not llm_result.get("is_valid_complaint"):
            return ModerationDecision.REJECT, "spam_no_valid_complaint"
    
    if vlm_result and vlm_result.get("confidence", 0) >= 0.80:
        if not vlm_result.get("is_appropriate"):
            issues = vlm_result.get("issues", [])
            if "nudity" in issues or "violence" in issues:
                return ModerationDecision.REJECT, f"inappropriate_image: {issues}"
    
    # Soft flags → forward to pipeline but also queue for human review
    if heuristic_flags or (llm_result and llm_result.get("is_political")):
        return ModerationDecision.FLAG, f"flagged: {heuristic_flags}"
    
    return ModerationDecision.PASS, ""
```

### Reputation Update (async, after pipeline completes)

```python
async def update_reputation(user_id: str, was_valid: bool, was_spam: bool, db):
    """Call after admin review or pipeline completion."""
    await db.execute("""
        INSERT INTO user_reputation (user_id, total_submissions, valid_submissions, spam_count)
        VALUES (:uid, 1, :valid, :spam)
        ON CONFLICT (user_id) DO UPDATE SET
            total_submissions = user_reputation.total_submissions + 1,
            valid_submissions  = user_reputation.valid_submissions + :valid,
            spam_count         = user_reputation.spam_count + :spam
    """, {"uid": user_id, "valid": int(was_valid), "spam": int(was_spam)})
    
    # Auto-ban if spam_count crosses threshold
    await db.execute("""
        UPDATE user_reputation
        SET banned_until = NOW() + INTERVAL '7 days'
        WHERE user_id = :uid AND spam_count >= 10
    """, {"uid": user_id})
```

---

## 6. Location-Aware Intelligence

### Goals

1. Normalize free-text location mentions → district + governorate
2. Support GPS coordinates with reverse geocoding
3. Geo-aware duplicate detection (nearby = same issue candidate)
4. Municipality-aware routing (correct entity per district)

### Reverse Geocoding

Use **Nominatim** (OpenStreetMap). Self-hosted with a Lebanon extract is free, fast (< 100 ms), and privacy-preserving.

```python
class GeoService:
    """Lightweight wrapper around a self-hosted Nominatim instance."""
    
    NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://nominatim:8080")
    
    async def reverse_geocode(self, lat: float, lng: float) -> dict:
        """Returns district, municipality, governorate from GPS coords."""
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.NOMINATIM_URL}/reverse",
                params={"lat": lat, "lon": lng, "format": "jsonv2", "accept-language": "en"},
                timeout=3.0
            )
        data = r.json()
        addr = data.get("address", {})
        return {
            "municipality": addr.get("city") or addr.get("town") or addr.get("village"),
            "district":     addr.get("county"),
            "governorate":  addr.get("state"),
            "display_name": data.get("display_name", ""),
            "source":       "reverse_geocode"
        }
```

docker-compose addition:
```yaml
  nominatim:
    image: mediagis/nominatim:4.3
    container_name: cedarfix-nominatim
    environment:
      PBF_URL: https://download.geofabrik.de/asia/lebanon-latest.osm.pbf
      REPLICATION_URL: https://download.geofabrik.de/asia/lebanon-updates/
    ports:
      - "8080:8080"
    volumes:
      - nominatim_data:/var/lib/postgresql/14/main
    networks:
      - cedarfix-net
```

### Lebanese Administrative Normalization Table

```sql
CREATE TABLE IF NOT EXISTS lb_locations (
    id              SERIAL PRIMARY KEY,
    name_en         VARCHAR(100) NOT NULL,   -- "Hamra"
    name_ar         VARCHAR(100),            -- "حمرا"
    aliases         JSONB DEFAULT '[]',      -- ["hamra", "el hamra", "al hamra"]
    municipality    VARCHAR(100),            -- "Beirut"
    district        VARCHAR(100),            -- "Beirut"
    governorate     VARCHAR(100),            -- "Beirut Governorate"
    lat             FLOAT,
    lng             FLOAT,
    UNIQUE(name_en, municipality)
);

-- Index for fast fuzzy text matching
CREATE INDEX lb_loc_name_trgm ON lb_locations USING GIN (name_en gin_trgm_ops);
```

Seeded with ~500 Lebanese neighborhoods, streets, villages. Query:
```sql
SELECT * FROM lb_locations
WHERE name_en % :query OR aliases @> :query_json
ORDER BY similarity(name_en, :query) DESC
LIMIT 3;
```

### Enhanced Location Schema

```python
class LocationJSON(BaseModel):
    # Input
    raw: str = ""               # original extracted text
    lat: Optional[float] = None
    lng: Optional[float] = None
    
    # Resolved
    normalized: str = ""        # canonical neighborhood name
    municipality: Optional[str] = None
    district: Optional[str] = None
    governorate: Optional[str] = None
    
    # Confidence
    confidence: float = 0.0
    source: str = "none"        # "gps" | "reverse_geocode" | "text_lookup" | "llm_extracted" | "none"
    
    # Geo (added by IEP-1 or geo service)
    resolved_lat: Optional[float] = None
    resolved_lng: Optional[float] = None
```

### Geo-Aware Duplicate Detection

Add a geospatial column to PostgreSQL (no PostGIS required for small datasets):

```sql
ALTER TABLE complaints ADD COLUMN location_lat FLOAT;
ALTER TABLE complaints ADD COLUMN location_lng FLOAT;

CREATE INDEX idx_complaints_geo ON complaints (location_lat, location_lng)
WHERE location_lat IS NOT NULL;
```

Haversine distance in Python (fast, no PostGIS):

```python
import math

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

async def find_geo_candidates(lat: float, lng: float, radius_km: float, complaint_type: str, db) -> List[str]:
    """Return complaint IDs within radius_km of (lat, lng) with matching type."""
    # Bounding box pre-filter (cheap)
    deg_offset = radius_km / 111.0
    rows = await db.fetch_all("""
        SELECT id, location_lat, location_lng
        FROM complaints
        WHERE complaint_type = :ctype
          AND location_lat BETWEEN :lat_min AND :lat_max
          AND location_lng BETWEEN :lng_min AND :lng_max
          AND created_at >= NOW() - INTERVAL '60 days'
    """, {
        "ctype": complaint_type,
        "lat_min": lat - deg_offset, "lat_max": lat + deg_offset,
        "lng_min": lng - deg_offset, "lng_max": lng + deg_offset,
    })
    # Precise Haversine filter
    return [
        r["id"] for r in rows
        if haversine_km(lat, lng, r["location_lat"], r["location_lng"]) <= radius_km
    ]
```

### Municipality-Aware Routing Enhancement

Add `location_to_entity` resolver that maps resolved location to the correct entity:

```python
MUNICIPALITY_ENTITY_MAP = {
    # Beirut
    "Beirut":         RoutingEntity.BEIRUT_MUNICIPALITY,
    
    # North Lebanon
    "Tripoli":        RoutingEntity.NORTH_MUNICIPALITY,
    "Zgharta":        RoutingEntity.NORTH_MUNICIPALITY,
    "Batroun":        RoutingEntity.NORTH_MUNICIPALITY,
    "Byblos":         RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Jbeil":          RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    
    # Mount Lebanon
    "Jounieh":        RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Baabda":         RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Jdeideh":        RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Metn":           RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    "Aley":           RoutingEntity.MOUNT_LEBANON_MUNICIPALITY,
    
    # South Lebanon
    "Sidon":          RoutingEntity.SOUTH_MUNICIPALITY,
    "Tyre":           RoutingEntity.SOUTH_MUNICIPALITY,
    "Nabatieh":       RoutingEntity.SOUTH_MUNICIPALITY,
    
    # Bekaa
    "Zahle":          RoutingEntity.HUMAN_REVIEW,   # no regional entity yet
    "Baalbek":        RoutingEntity.HUMAN_REVIEW,
    "Chtaura":        RoutingEntity.HUMAN_REVIEW,
}

def location_entity_override(
    primary_entity: RoutingEntity,
    municipality: Optional[str],
) -> RoutingEntity:
    """
    If the complaint is in a non-Beirut municipality, and the primary entity
    is Beirut Municipality (wrong jurisdiction), replace with the correct one.
    """
    if primary_entity != RoutingEntity.BEIRUT_MUNICIPALITY:
        return primary_entity   # no change needed

    if municipality and municipality in MUNICIPALITY_ENTITY_MAP:
        return MUNICIPALITY_ENTITY_MAP[municipality]
    
    return primary_entity
```

---

## Implementation Priority Order

| Priority | Component | Effort | Impact |
|---|---|---|---|
| 1 | **IEP-2 VLM reasoning** (Qwen2.5-VL classification) | Medium | High — better image decisions |
| 2 | **IEP-0 Spam gate** (heuristics + LLM mod) | Low–Medium | High — data quality |
| 3 | **Location normalization** (lb_locations table + geo dedup) | Low | High — routing accuracy |
| 4 | **RAG routing knowledge base** (populate docs + Qdrant) | Medium | High — Lebanon-specific routing |
| 5 | **Confidence bundle** (schema + aggregation) | Low | Medium — better review routing |
| 6 | **LLM duplicate judge** (IEP-4) | Medium | Medium — fewer false near-dups |

---

## Shared Environment Variables to Add

```yaml
# docker-compose.yml additions

# IEP-0 Moderation
MODERATION_ENABLED: "true"
MODERATION_LLM_THRESHOLD: "0.75"
AUTO_BAN_SPAM_THRESHOLD: "10"

# IEP-2 VLM
VLM_BASE_URL: ${VLM_BASE_URL:-https://YOUR_RUNPOD_ID-8000.proxy.runpod.net/v1}
VLM_MODEL: "Qwen/Qwen2.5-VL-3B-Instruct"
VLM_ENABLED: "true"
VLM_TIMEOUT: "25"

# Location
NOMINATIM_URL: "http://nominatim:8080"
GEO_DEDUP_RADIUS_KM: "0.5"
GEO_DEDUP_ENABLED: "true"

# RAG Routing
ROUTING_QDRANT_COLLECTION: "routing_knowledge"
ROUTING_RAG_ENABLED: "true"
ROUTING_RAG_TOP_K: "5"

# Confidence
ROUTING_AUTO_THRESHOLD: "0.82"
ROUTING_REVIEW_THRESHOLD: "0.60"
FINAL_CONFIDENCE_REVIEW_THRESHOLD: "0.50"
```
