# CedarFix Command AI — Corpus Authoring Protocol
# Version: 1.0 | Batch in progress: 001
# Reference: docs/ANNOTATION_GUIDELINES.md for label definitions
# Reference: data/knowledge_base/ for all routing, severity, and district constraints

---

## 1. Why Cluster-First Matters

The most critical AI in CedarFix Command is incident fusion (IEP-2): detecting that two or more reports in different languages, from slightly different GPS coordinates, submitted at different times, refer to the **same physical incident**.

A corpus of 300 random single-language complaints proves nothing about dedup. A corpus of 75 well-designed clusters with 3–5 reports each — varying language, GPS, phrasing, and detail level — gives IEP-2 real training signal and gives IEP-3 real routing evidence.

**Rule: Never author a report outside of a planned cluster scenario.** Every report belongs to a cluster, or is explicitly labeled NOISE as a hard negative for a specific cluster.

---

## 2. Cluster Scenario Design (Before Authoring Begins)

Before writing a single report, add a row to `data/corpus/cedarfix_clusters_v1.csv` defining:
- `cluster_id`: next sequential `CLU-BNNN-NNN`
- `sector`, `issue_type`, `district_code`, `severity`, `route_entity`, `hitl_required`, `public_safety`
- `cluster_description`: one sentence describing the physical scenario
- `canonical_report_id`: leave blank; fill in after ORIGINAL report is authored
- `notes`: what specific AI behavior this cluster is designed to stress-test

**Target cluster distribution across 75 clusters (300 total reports):**

| Sector     | Clusters | Reports |
|------------|----------|---------|
| ROADS      | 18       | 72      |
| WATER      | 14       | 56      |
| ELECTRICITY| 10       | 40      |
| WASTE      | 12       | 48      |
| FLOODING   | 10       | 40      |
| SAFETY     | 7        | 28      |
| OTHER      | 4        | 16      |

**Severity distribution across all clusters:**
- CRITICAL: 12 clusters
- HIGH: 28 clusters
- MEDIUM: 25 clusters
- LOW: 10 clusters

**HITL clusters (hitl_required=true): minimum 20 of 75**
- All ELECTRICITY clusters: hitl_required=true
- All SAFETY clusters: hitl_required=true
- WATER CRITICAL with public_safety=true: hitl_required=true (reviewer discretion)

---

## 3. Five-Step Authoring Workflow

### Step 1: Define the cluster scenario
Add the cluster row to `cedarfix_clusters_v1.csv`. Assign the cluster_id. Write the physical scenario in plain language. Confirm the district_code exists in `municipality_responsibility_map.csv` and the route_entity exists in `sector_agency_map.csv`.

### Step 2: Author the ORIGINAL report
Write the ORIGINAL report as a clear, specific, first-person complaint in one language. Include:
- A specific street name, landmark, or intersection (must be real for the district)
- What the problem is
- How long it has existed (for non-emergency issues)
Set `duplicate_role=ORIGINAL`, `created_at_offset_minutes=0`.

### Step 3: Author DUPLICATE reports (2–4 per cluster)
Each DUPLICATE must be a plausible independent submission of the same incident by a different person. Vary:
- Language (target: no two DUPLICATEs in the same language)
- Phrasing (different words, different detail level)
- GPS offset (see Section 4)
- Time offset (see time jitter rules below)
- Completeness (one report can be vague; one can include extra context)

Set `duplicate_role=DUPLICATE`.

### Step 4: Optionally add RELATED and NOISE reports
**RELATED**: A report that is part of the same real-world incident chain but describes a downstream or secondary effect. May have a different `issue_type` or `district_code` from the cluster canonical. Set `duplicate_role=RELATED`.

**NOISE**: A report in the same geographic area that is NOT part of this cluster. Used as a hard negative for IEP-2 training. Assign `cluster_id` as empty, set `duplicate_role=NOISE`, set `hard_negative_for_cluster_id` to the target cluster, and explain the target in the `notes` field. NOISE reports should be plausible-looking candidates that a naive model might merge into the cluster.

### Step 5: Validate and mark for second review
Check against the quality gate (Section 8), then run:

```powershell
python scripts/validate_cedarfix_corpus.py
```

If validation passes, set `review_status=PENDING_SECOND_REVIEW` and update `canonical_report_id` in `cedarfix_clusters_v1.csv`. Only set `review_status=APPROVED` after a second human reviewer checks the row.

After each batch, regenerate or update `data/corpus/cedarfix_pairs_v1.csv` with pair labels for IEP-2 evaluation:
- `DUPLICATE`: two core reports in the same physical incident cluster
- `RELATED`: a core report paired with a RELATED report in the same incident chain
- `HARD_NEGATIVE`: a core report paired with a NOISE report targeting the same cluster (intra-cluster negative — confusing because same area and same sector; tests geographic boundary sensitivity)
- `UNRELATED`: a cross-cluster pair of two different incidents (inter-cluster negative — harder because similar language or sector can fool IEP-2; tests semantic discrimination)

**Negative pair ratio targets by batch:**

| Batch | Minimum | Target | Notes |
|-------|---------|--------|-------|
| Batch 001 | ≥20% | 20–25% | Baseline; validator warns if below 20% |
| Batch 002+ | ≥25% | 30–40% | Richer negatives required; IEP-2 must see harder cases |

**Negative subtype balance (Batch 002+):** At least 50% of negative pairs must be `UNRELATED` (cross-cluster). Both subtypes must be present in every batch — `HARD_NEGATIVE` alone is insufficient because it only tests intra-cluster boundaries.

After every batch with Arabizi or mixed-language reports, regenerate the adaptive language-drift queue:

```powershell
python scripts/analyze_arabizi_oov.py
python scripts/validate_arabizi_oov_queue.py
```

Review this file before promoting new vocabulary terms:

| OOV action | Meaning |
|------------|---------|
| `ADD_TO_VOCAB` | Confirmed Lebanese municipal term; add to a specific sector/issue_type in the next vocabulary version |
| `KEEP_MODEL_ONLY` | Meaningful context word, but not stable enough for the fixed lexicon |
| `ADD_TO_STOPLIST` | Connector, place/name artifact, acronym, or filler that should not appear in OOV drift alerts |
| `REJECT_NOISE` | Typo noise or non-meaningful token |
| `NEEDS_MORE_EXAMPLES` | Plausible but not enough evidence yet |

### Frozen Arabizi Regression Benchmark

Batch 001 establishes the first immutable Arabizi regression target:

```powershell
python scripts/build_arabizi_regression_benchmark.py
python scripts/validate_arabizi_benchmark.py
```

Frozen artifacts:

- `data/eval/arabizi_benchmark_v0_regression.csv`
- `data/eval/arabizi_benchmark_v0_regression.sha256`

This benchmark contains:

- all 14 B001 Arabizi/mixed corpus rows
- selected cross-language duplicate and hard-negative pair cases
- adversarial Arabizi cases for digit omission, repeated characters, no-space tokens, French code-switching, unknown risk modifiers, sanitation ambiguity, and near-border non-merge behavior

**Do not edit v0 in place.** If a correction is necessary, create a new benchmark version and record the reason. Every MLflow run that reports Arabizi behavior must log the benchmark SHA256.

---

## 4. GPS Jitter Protocol

All GPS coordinates in a cluster must be realistic for the district. Use the district centroid from `municipality_responsibility_map.csv` as the anchor for ORIGINAL reports, then apply jitter per role:

| duplicate_role | GPS offset from ORIGINAL | Approx distance | Intent |
|----------------|--------------------------|-----------------|--------|
| ORIGINAL | 0 | 0 m | Exact centroid |
| DUPLICATE | ±0.0003 to ±0.0010 | 30–100 m | Same block, slight variation |
| RELATED | ±0.0010 to ±0.0030 | 100–300 m | Adjacent area; may be different district |
| NOISE | ±0.0030 to ±0.0080 | 300–800 m | Same general area; different street |

**Procedure:**
1. Get district centroid from `municipality_responsibility_map.csv`
2. Add jitter independently to lat and lon
3. Jitter direction should vary (not always +/+): mix +/-, -/+, +/+, -/-
4. Round to 6 decimal places

**Example for BEI_HAMRA (centroid: 33.8897, 35.4800):**
- ORIGINAL: 33.889700, 35.480000
- DUPLICATE A: 33.889900, 35.480300 (+0.0002, +0.0003)
- DUPLICATE B: 33.889500, 35.479700 (-0.0002, -0.0003)
- DUPLICATE C: 33.890150, 35.480450 (+0.00045, +0.00045)
- NOISE: 33.892500, 35.482500 (+0.0028, +0.0025)

---

## 5. Time Jitter Rules

`created_at_offset_minutes` is the number of minutes after the cluster's `created_at_reference` that this report was submitted.

| duplicate_role | Offset range | Notes |
|----------------|-------------|-------|
| ORIGINAL | 0 | Always 0 |
| DUPLICATE 1st | 10–30 min | Fast second reporter |
| DUPLICATE 2nd | 40–120 min | Delayed second reporter |
| DUPLICATE 3rd | 90–360 min | Late reporter (same day) |
| DUPLICATE 4th | 300–1440 min | Very late reporter (up to 24h) |
| RELATED | 90–720 min | Downstream effect reported later |
| NOISE | 0 (independent) | NOISE reports are not time-linked to cluster |

Design at least 3 clusters where the temporal gap between first and last DUPLICATE exceeds 6 hours. IEP-2's time window is 72 hours; test edge cases at 60+ hours for Batches 002–003.

---

## 6. Language Targets Per Batch

Each batch of 50 reports (12 clusters) should hit these targets:

| Language | Target per 50 reports |
|----------|-----------------------|
| Arabic (MSA + Lebanese dialect) | 14–16 |
| Arabizi (Lebanese Latin-script) | 12–14 |
| English | 10–12 |
| French | 8–10 |
| Mixed-language | 2–4 |

**Mixed-language reports**: A single report that code-switches (e.g., Arabic sentence + French word, or Arabizi + English brand name). Label `language=mixed`. No Arabizi normalization needed if the primary language is Arabic.

**Total 300-report targets:**
- Arabic: 75 (25%)
- Arabizi: 70 (23%)
- English: 55 (18%)
- French: 45 (15%)
- Mixed: 25 (8%)
- Noise/ambiguous: 30 (10%)

---

## 7. Arabizi Authoring Guide

Reference `data/knowledge_base/arabizi_vocabulary.json` for vocabulary seeds. Do NOT copy seeds verbatim into the corpus — use them as starting points and write natural variations.

**Key transliteration conventions:**
- `3` = ع (ayin) — most important character
- `7` = ح (ha)
- `5` or `kh` = خ (kha)
- `2` = ء / أ / إ (glottal stop or hamza)
- `9` or `2` = ق (qaf) — varies by speaker
- `gh` = غ (ghayn)
- `sh` = ش
- `j` = ج

**Common Lebanese Arabizi patterns:**
- `l-` prefix for definite article: `l-tari2`, `l-may`, `l-kahraba`
- `bi` = في/بـ (in/at)
- `3al` = على (on/at)
- `men` = من (from/since)
- `w` = و (and)
- `ma fi` = ما في (there is no / not available)
- `2ata3et` = قطعت / انقطعت (cut off)

**Quality check for Arabizi reports:**
1. Would a Lebanese person recognize this as natural?
2. Does it contain at least one Arabizi-specific character (3, 7, 2, 5)?
3. Is the normalized_text a faithful Arabic translation (not word-for-word, but meaning-equivalent)?
4. Does it mention a real Lebanese place name or landmark?

---

## 8. Quality Gates

A report can leave draft status only if ALL of the following pass:

| Gate | Check |
|------|-------|
| G1 | `district_code` exists in `municipality_responsibility_map.csv` |
| G2 | GPS coordinates are within Lebanon bounds (see `gps_bounds.json`) |
| G3 | GPS offset from district centroid is consistent with `duplicate_role` (Section 4) |
| G4 | `sector` and `issue_type` are consistent (e.g., POTHOLE cannot be in WATER sector) |
| G5 | `route_entity` matches `sector_agency_map.csv` for this sector and district |
| G6 | `hitl_required=true` for all ELECTRICITY and SAFETY reports (non-negotiable) |
| G7 | `priority_label` is consistent with severity and public_safety (see ANNOTATION_GUIDELINES) |
| G8 | `normalized_text` is never empty and never `SAME`; for Arabizi reports it must be a real Arabic translation |
| G9 | No two DUPLICATE reports in the same cluster use the same language |
| G10 | `raw_text` mentions at least one geographic reference (street, neighborhood, landmark, district) |
| G11 | NOISE rows have empty `cluster_id` and non-empty `hard_negative_for_cluster_id` |
| G12 | `python scripts/validate_cedarfix_corpus.py` exits with zero errors |
| G13 | `python scripts/analyze_arabizi_oov.py` and `python scripts/validate_arabizi_oov_queue.py` run after every batch with Arabizi/mixed rows |
| G14 | `python scripts/validate_arabizi_benchmark.py` passes before any normalizer, vocabulary, or IEP-1 change is promoted |
| G15 | `python scripts/tests/test_arabizi_adversarial.py` passes before any language normalization, OOV, or IEP-1 contract change is promoted |

Reports that fail any gate should be set to `review_status=NEEDS_FIX` with a note explaining which gate failed.

---

## 9. Report ID and Batch Naming Convention

**Report IDs:** `RPT-BNNN-NNN`
- `B001` = Batch 001 (first 50 reports, 12 clusters)
- `B002` = Batch 002 (next 50 reports, 12–13 clusters)
- Sequential NNN within batch: 001–050, 001–050, etc.

**Cluster IDs:** `CLU-BNNN-NNN`
- Batch where cluster was first defined
- Sequential within batch

**File versioning:**
- `cedarfix_reports_v1.csv` = Batches 001–002 (first 100 reports)
- `cedarfix_reports_v2.csv` = Batches 003–006 (next 200 reports, total 300)
- Append new batches to the appropriate version file

---

## 10. Files and Paths

| File | Purpose |
|------|---------|
| `data/corpus/cedarfix_reports_v1.csv` | All labeled reports |
| `data/corpus/cedarfix_clusters_v1.csv` | Cluster metadata and scenario registry |
| `data/corpus/cedarfix_pairs_v1.csv` | Pairwise duplicate / related / hard-negative labels for IEP-2 evaluation |
| `data/corpus/arabizi_oov_review_queue_v1.csv` | Unknown Arabizi token review queue for language drift and active learning |
| `data/eval/arabizi_benchmark_v0_regression.csv` | Frozen B001 Arabizi regression benchmark; not a final F1 evaluation set |
| `data/eval/arabizi_benchmark_v0_regression.sha256` | SHA256 hash for benchmark immutability and MLflow lineage |
| `data/knowledge_base/sector_agency_map.csv` | Route entity and HITL policy lookup |
| `data/knowledge_base/municipality_responsibility_map.csv` | District codes, GPS centroids, water authorities |
| `data/knowledge_base/issue_severity_reference.yaml` | Severity keywords, SLA, safety flags |
| `data/knowledge_base/gps_bounds.json` | Lebanon GPS validation bounds |
| `data/knowledge_base/arabizi_vocabulary.json` | Arabizi vocabulary seeds per sector |
| `docs/ANNOTATION_GUIDELINES.md` | Label definitions and decision rules |
| `docs/IEP1_LANGUAGE_SIGNAL_CONTRACT.md` | Required IEP-1 language reliability output contract |
| `src/shared/schemas.py` | Pydantic contracts for IEP-1 language signals and IEP-2 pair fusion gates |
| `src/shared/arabizi_features.py` | Lightweight Arabizi regression probe used before trained IEP-1 exists |
| `src/shared/arabizi_lexical_policy.py` | Shared stopword/entity/high-risk lexical policy for the OOV queue and regression probe |
| `scripts/validate_cedarfix_corpus.py` | Corpus consistency validator; must pass before scaling a batch |
| `scripts/analyze_arabizi_oov.py` | Generates the Arabizi OOV/drift review queue from corpus reports |
| `scripts/evaluate_arabizi_coverage.py` | C-phase offline Arabizi coverage, drift, and recall smoke-test evaluator |
| `scripts/validate_arabizi_oov_queue.py` | Validates the OOV review queue and accepted vocabulary decisions |
| `scripts/build_arabizi_regression_benchmark.py` | Creates the immutable B001 Arabizi regression benchmark |
| `scripts/validate_arabizi_benchmark.py` | Validates benchmark schema, source consistency, counts, and SHA256 |
| `scripts/tests/test_arabizi_adversarial.py` | Permanent regression tests for the frozen adversarial Arabizi cases |
