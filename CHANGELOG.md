# CedarFix Project — What's New (May 2026)

A human-readable summary of all major additions on the `feature/general-data` branch.
Committed range: `1db057ed` → `0b9e6dd9` · Untracked additions listed separately at the bottom.

---

## 1 · Training Data (Finetuning-Ready)

### 1.1 Main Training Corpus — Batch 8
- **`data/training/cidarfix_v29_batch8_train.jsonl`** — 75,555 training examples  
- **`data/training/cidarfix_v29_batch8_val.jsonl`** — 8,997 validation examples  
- Built from v14 Arabizi vocabulary; covers all sectors for `iep1` sector/issue fine-tuning.

### 1.2 Hard-Negative Sets
- **Senzi hard negatives** (train / val / test) — contrastive learning boundary examples  
- **Senzi real-world** (train / val) — live Lebanese complaint reports for domain adaptation  
- **Telecom batch 2** (train / val) — CDR / OGERO edge-case routing examples

### 1.3 Locked Evaluation Sets
- **`data/training/cidarfix_v29_batch7_model_final_test_locked.jsonl`** — 7,940 locked test rows (hold-out; do not train on)  
- **`data/training/cidarfix_telecom_eval_locked.jsonl`** — 150 TELECOM eval rows, seed=42, 0 train overlap  
- **`data/training/finetuning_manifest_v1.json`** — canonical split manifest: train=91,169 / val=10,562 / test=7,940 / telecom_eval=150

### 1.4 Hard Benchmark
- **`data/eval/arabizi_master_hard_negative_eval_cases.jsonl`** — 304 adversarial cases across 9 sectors (boundary/ambiguity probing)

---

## 2 · Arabizi Vocabulary

- **`data/knowledge_base/arabizi_vocabulary.json`** — v14.0.0, **6,340 term_metadata entries**, promoted to production  
- Covers SAFETY, WATER, ELECTRICITY, TELECOM, MUNICIPALITY, and 4 other sectors  
- Gate P-01 (vocab coverage) confirmed PASS

---

## 3 · Readiness Gates

- **`data/eval/arabizi_excellence_gates_v1.json`** — model gates G-01 … G-10  
- **`data/eval/cedarfix_next_phase_gates_v1.json`** — system gates P-01 … P-10; all 8 required gates are **PASSING**

---

## 4 · Knowledge Base — Municipalities

### 4.1 National Municipality Registry (enriched)
- **`data/knowledge_base/municipalities/national_municipality_registry.csv`** — 1,107 municipalities, 83 columns  
- **New columns added from Municipalities.xlsx:**
  - `phone` — 588 official phone numbers  
  - `address` — 532 official addresses  
  - `name_en` — 130 English name entries  
  - `xlsx_uom` — 436 Union of Municipalities names  
- **GPS coordinates fixed:** 333 rows had placeholder fallback coordinates; **227 corrected** via three passes:
  1. Direct coordinates from Municipalities.xlsx → **122 fixed**  
  2. OSM Nominatim geocoding (Arabic + English name queries) → **58 fixed**  
  3. Compound-name component splitting + centroid averaging → **47 fixed**  
  - 106 small rural localities remain at placeholder (absent from OSM; best-effort complete)

### 4.2 Towns Registry (new)
- **`data/knowledge_base/municipalities/towns_registry.csv`** — **2,730 rows**  
  All Lebanese towns/localities from Towns.xlsx including:  
  - 557 overlap with municipality registry  
  - 2,173 locality-only entries (sub-municipal level towns not in registry)  
  - Columns: `name_ar`, `name_en`, `caza_ar`, `is_municipality`, `source`

### 4.3 Municipality Unions (new, untracked)
- **`data/knowledge_base/municipalities/municipality_unions.csv`** — **59 union records**  
  Columns: `union_id`, `name_en`, `name_ar`, `governorate_en`, `district_en`, `member_municipality_ids`

### 4.4 DGLAC Federations (new, untracked)
- **`data/knowledge_base/municipalities/dglac_federation_members_raw.json`** — Raw federation membership data from DGLAC

### 4.5 Geocode Cache
- **`data/knowledge_base/municipalities/geocode_cache.json`** — OSM Nominatim cache (prevents re-querying; includes component-level entries)

---

## 5 · Knowledge Base — Water Establishments (new domain, untracked)

Full dossier for Lebanon's 4 regional water establishments: **BMLWE, NLWE, SLWE, BWE** + Ministry of Energy & Water + Litani River Authority.

| File | Description |
|------|-------------|
| `water_entity_resolution.csv` | **1,094 rows** — maps every Lebanese municipality to its responsible water establishment |
| `water_establishments_dossier.md` | Narrative reference dossier |
| `contact_points.csv` | Official phones, emails, office addresses per establishment |
| `complaint_channels.csv` | Complaint intake channels (hotline / form / in-person / app) per establishment |
| `branch_service_areas.csv` | Branch office → governorate/district coverage map |
| `boundary_conditions.csv` | Edge-case routing rules (border areas, refugee camps, etc.) |
| `not_responsible_for.csv` | Explicit out-of-scope items per establishment |
| `required_fields.csv` | Required intake fields for water complaints |
| `sla_policy.csv` | Official SLA / response time policies |
| `irl_complaint_patterns.csv` | Real-world complaint pattern examples per establishment |
| `irrigation_boundaries.csv` | Litani River Authority irrigation-zone boundaries |
| `coverage_summary.csv` | Governorate-level coverage summary |
| `trusted_context.csv` | Trusted contextual facts used in routing decisions |
| `page_inventory.csv` | 85 scraped source pages with crawl metadata |
| `source_registry.csv` | 85 water-domain source entries |
| `water_production_audit_report.md` | Audit results: **355 / 355 evals passed**, 0 provenance issues |
| `source_candidate_review.csv` | Source credibility review records |
| `water_dimension_audit.md` | Dimensional completeness audit |
| `research_backlog.csv` | Open research questions |
| `water_service_catalog.csv` | Service type catalog (drinking water, irrigation, wastewater, tanker) |

**Routing eval:** `data/eval/water_establishments_routing_eval_v1.jsonl` — **355 eval cases** (untracked)

---

## 6 · Knowledge Base — Electricity (new domain, untracked)

Initial knowledge base for Lebanon's electricity sector: **EDL + Ministry of Energy & Water**.

| File | Description |
|------|-------------|
| `electricity_dossier.md` | Entity overview and routing context |
| `contact_points.csv` | EDL regional centers + MEW contact |
| `complaint_channels.csv` | Intake channels |
| `boundary_conditions.csv` | Edge-case routing rules |
| `not_responsible_for.csv` | Out-of-scope items |
| `required_fields.csv` | Required intake fields |
| `sla_policy.csv` | SLA policies |
| `research_backlog.csv` | Open items to investigate |
| `source_registry.csv` | 5 source entries (EDL, Civil Defense, MEW) |
| `electricity_dimension_audit.md` | Dimensional completeness audit |

**Routing eval:** `data/eval/electricity_routing_eval_v1.jsonl` — 9 cases (needs expansion)

---

## 7 · Routing Engine & KB Schema

- **Entity catalog** expanded to all **13 routing entities** (MEW, EDL, OGERO, CDR, ISF, MOE, MPWT, BMLWE, BWE, NLWE, SLWE, MUN, TRA) with service areas, contact info, and boundary conditions  
- **TRA entity** added with telecom billing routing + TELECOM sector vocabulary  
- **`data/knowledge_base/routing_rules.csv`** — 69 routing decision rules  
- **`data/knowledge_base/complaint_taxonomy.csv`** — 63 complaint types  
- **`data/knowledge_base/remediation_workflows.csv`** — 59 end-to-end resolution workflows  
- **`data/knowledge_base/source_registry.csv`** — 41 verified sources (T0/T1 reliability tiers)  
- **Contact schema columns added** to `public_entities_extended.csv`: `official_email`, `complaint_channel_types`, `ticket_reference_policy`  
- **`src/route_complaint.py`** — routing accuracy fixes: SAFETY fire vocab, WATER maye variants, mobile → TRA override (user-modified, uncommitted)

---

## 8 · Review Queue & Corpus

- **`data/review_queue/`** — Human review queues for legacy 100k complaint corpus:  
  - Abusive language queue  
  - Political-mixed infrastructure queue  
  - Political statement queue  
  - Combined HITL review queue  
- **`data/knowledge_base/cedarfix_language_bank.csv`** — 5,772 approved Arabizi terms  
- **`data/knowledge_base/cedarfix_language_bank_review_queue.csv`** — 7,298 candidate terms pending review  
- **`data/knowledge_base/cedarfix_complaint_scenario_inventory.csv`** — 165 complaint scenarios across sectors

---

## 9 · What Is Still Uncommitted

These files exist locally but are **not yet in git**:

| Item | Status |
|------|--------|
| `data/knowledge_base/water_establishments/` | Needs `source_registry.csv` merge first |
| `data/knowledge_base/electricity/` | Ready to commit |
| `data/knowledge_base/municipalities/municipality_unions.csv` | Ready to commit |
| `data/knowledge_base/municipalities/dglac_federation_members_raw.json` | Ready to commit |
| `data/eval/water_establishments_routing_eval_v1.jsonl` | Ready (`git add -f`) |
| `data/eval/electricity_routing_eval_v1.jsonl` | Needs expansion (9 cases only) |
| `src/route_complaint.py` | User changes — needs review |
| `src/iep3/worker.py` | User changes — needs review |

---

*Branch: `feature/general-data` · Remotes: `origin` (aliwaked-ai) + `cedarfix-ai` (SleimanMh)*
