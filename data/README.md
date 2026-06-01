# data - CedarFix data catalog and analysis

This folder is the non-code brain of CedarFix. The Python services in `src/`
run the pipeline, but the files here define the Lebanon-specific knowledge,
language coverage, training/evaluation sets, source evidence, and review queues
that make the pipeline behave like CedarFix instead of a generic complaint app.

This README is written for both humans and code assistants. If Copilot or
another agent needs to work in `data/`, start here before editing anything.

## Current Inventory

Counts below were taken from the local filesystem on 2026-06-02.

| Area | Files | Size | Purpose |
| --- | ---: | ---: | --- |
| `knowledge_base/` | 148 | 18.67 MB | Runtime and source-backed civic knowledge. |
| `training/` | 9 | 182.02 MB | Model train/validation/test JSONL plus manifests and backup. |
| `eval/` | 14 | 0.32 MB | Locked routing, grounding, image-fusion, and language fixtures. |
| `review_queue/` | 5 | 3.31 MB | Human review queues from legacy corpus audits. |
| `complaint_intelligence/` | 14 | 1.32 MB | Source research, normalized civic events, discovery leads, and next-data acquisition planning. |
| Total under `data/` | 191 | 205.67 MB | 106 CSV, 35 JSON, 19 JSONL, 28 Markdown, 3 `.gitkeep`. |

## The Short Version

Use this folder as five layers:

1. `knowledge_base/` is what production routing and grounded reasoning use.
2. `training/` is what model iteration uses.
3. `eval/` is what tests and audits use to prove behavior.
4. `complaint_intelligence/` is research input that may later become KB or eval data.
5. `review_queue/` is human-in-the-loop cleanup work, not production truth.

The most important rule:

```text
Do not train on `eval/` fixtures, `test_locked` files, or gold OOD cases.
Do not promote research/review rows into runtime KB without source evidence.
```

## How Data Flows Through CedarFix

```text
Citizen text/GPS/photo
  -> EEP validates GPS bounds from `knowledge_base/gps_bounds.json`
  -> IEP-1 uses Arabizi/language assets and training-derived models
  -> IEP-2 uses complaint similarity and incident context
  -> IEP-3 uses municipality aliases, service mappings, taxonomy, and routing rules
  -> IEP-4 uses entity KB facts to explain the route
  -> IEP-6 uses image-fusion eval/taxonomy contracts from code, not this folder
  -> IEP-7 reads outcomes/calibration data from the database
  -> IEP-8 retrieves entity JSON facts and sector shard facts for grounded plans
```

Key runtime code paths:

- `src/route_complaint.py` loads:
  - `knowledge_base/arabizi_vocabulary.json`
  - `knowledge_base/complaint_taxonomy.csv`
  - `knowledge_base/routing_rules.csv`
  - `knowledge_base/municipalities/municipality_aliases.csv`
  - `knowledge_base/municipalities/national_municipality_registry.csv`
  - `knowledge_base/municipalities/municipality_service_mappings.csv`
  - `knowledge_base/water_establishments/water_entity_resolution.csv`
- `src/shared/arabizi_features.py` loads Arabizi vocabulary assets.
- `src/eep/models.py` validates GPS with `knowledge_base/gps_bounds.json`.
- `src/iep1/semantic_classifier.py` uses `training/cidarfix_v29_batch8_train_v14_enriched.jsonl`.
- `src/iep4/explainer.py` reads `knowledge_base/entities/*.json`.
- `src/iep8/retriever.py` reads `knowledge_base/entities/*.json` by default.

## Safety Rules For Code Assistants

If an AI assistant edits this folder, follow these rules:

- Preserve UTF-8 encoding. Many files contain Arabic and Arabizi.
- Treat files under `eval/` as locked behavioral contracts. Add a new fixture
  version when expanding coverage instead of rewriting old expected behavior.
- Treat `training/*test_locked*.jsonl`, `eval/*.jsonl`, and manifest role
  `gold_ood_eval` as never-train data.
- Treat `review_queue/`, `research_backlog.csv`, `page_inventory.csv`,
  `source_candidate_review.csv`, and discovery backlogs as candidate or review
  material, not production truth.
- Runtime KB rows should have source IDs, confidence/status fields where the
  schema supports them, and enough notes to explain ambiguity.
- When changing routing-critical data, update tests or add fixtures that prove
  the intended behavior.
- Do not make data changes just to force a test to pass. First decide whether
  the bug is in code, data, or the test expectation.

## Runtime Knowledge Base

`knowledge_base/` is the production-facing civic knowledge layer. It contains
the tables that decide what a complaint means, where it belongs, which entity
should handle it, what evidence supports that route, and what boundaries should
force HITL review.

### Core Routing Tables

| File | Rows | Purpose |
| --- | ---: | --- |
| `knowledge_base/complaint_taxonomy.csv` | 64 | Complaint types, examples, default entity selectors, location precision, and HITL defaults. |
| `knowledge_base/routing_rules.csv` | 70 | Complaint-type-specific routing rules, HITL reasons, evidence requirements, and canonical entity IDs. |
| `knowledge_base/sector_agency_map.csv` | 9 | Simple sector-to-agency fallback map. |
| `knowledge_base/remediation_workflows.csv` | 59 | Intake, triage, referral, field remediation, closure, and SLA/deadline policy by complaint type. |
| `knowledge_base/public_entities_extended.csv` | 21 | Canonical public entities/categories, responsibilities, contact fields, routing roles, and production status. |
| `knowledge_base/entity_service_area_mapping.csv` | 11 | Service family and location condition mappings to entities. |
| `knowledge_base/entity_boundary_conditions.csv` | 12 | Cross-entity routing guardrails and HITL boundaries. |
| `knowledge_base/source_registry.csv` | 132 | Root source registry for official/institutional evidence IDs. |
| `knowledge_base/municipality_responsibility_map.csv` | 43 | District/governorate-level water authority and municipality responsibility hints. |

Use these files when the question is:

- "What complaint types does CedarFix understand?"
- "What entity should receive a complaint?"
- "What evidence is required before production routing?"
- "Which cases must force human review?"

### Municipality Data

Municipality data drives location resolution and local responsibility.

| File | Rows | Purpose |
| --- | ---: | --- |
| `municipalities/national_municipality_registry.csv` | 1,107 | Canonical municipality registry rows, names, districts, coordinates, source status, research priority, townhall fields, and quality flags. Every row has a unique `registry_id`; 800 rows currently have a populated `municipality_id`. |
| `municipalities/municipality_aliases.csv` | 3,870 | Name variants mapped to registry/municipality IDs for text lookup. These are alias rows, not municipality rows. |
| `municipalities/municipality_service_mappings.csv` | 1,107 | Registry-row-to-water/electricity/telecom/road entity hints used by routing. Every row has `registry_id`; rows without official `municipality_id` route through registry-ID fallback. |
| `municipalities/municipality_official_channels.csv` | 102 | Verified or candidate official municipality contact/reporting channels. |
| `municipalities/municipality_complaint_workflows.csv` | 30 | Municipality complaint workflow evidence, required fields, tracking/deadline hints. |
| `municipalities/municipality_unions.csv` | 59 | Municipality union metadata. |
| `municipalities/municipal_union_memberships.csv` | 841 | Row-level municipality-to-union memberships across all 59 union IDs; 784 rows have registry IDs, 57 are text-only source-specific rows needing manual reconciliation. |
| `municipalities/municipal_union_service_responsibilities.csv` | 6 | Seed union responsibility-signal rows: union complaint/suggestion intake, DGLAC membership guardrail, and one Baalbek service-advocacy context row. |
| `municipalities/source_registry.csv` | 44 | Municipality-specific sources. |
| `municipalities/towns_registry.csv` | 2,730 | Town-level names and references. These are town rows, not municipality rows. |
| `municipalities/geocode_cache.json` | cache | Geocoding cache for municipality/townhall lookup. |
| `municipalities/municipality_channel_discovery_queue_2026-06-01.csv` | 50 | Municipality channel discovery work queue. |
| `municipalities/municipality_townhall_contact_candidates_2026-06-01.csv` | 200 | Candidate townhall/contact rows for review. |

### Municipality Count Reconciliation

The project has several municipality-related counts because different files
count different concepts. Use the precise label instead of saying only
"municipalities":

| Count | What it means | Do not interpret it as |
| ---: | --- | --- |
| 1,107 | Complete registry-row coverage in the master registry, service mappings, aliases, water resolver, electricity resolver, and Civil Defense resolver. | Unique populated official `municipality_id` values. |
| 800 | Unique non-empty official `municipality_id` values currently present in the municipality registry, service mapping file, aliases, and research tracker. | The full routable registry size. |
| 307 | Registry rows without official `municipality_id`; these route through `registry_id` fallback. | Missing operational coverage. |
| 3,870 | Alias rows in `municipality_aliases.csv`, covering all 1,107 unique `registry_id` values. | Number of municipalities. |
| 2,730 | Town rows in `towns_registry.csv`. | Number of municipalities. |
| 102 / 30 | Official-channel rows and complaint-workflow rows. These currently cover a much smaller set of municipalities. | Registry coverage. |

For joins, prefer `registry_id` when working inside the municipality registry and
municipality support files because it is populated for all 1,107 registry rows.
Use `municipality_id` only when the target file actually requires it. The
project-wide operational municipality count is now 1,107 registry rows; the 800
number is official-ID coverage, not routing coverage.

### Arabizi and Language Assets

These assets help IEP-1 understand Lebanese Arabizi and mixed-language reports.

| File | Rows/shape | Purpose |
| --- | ---: | --- |
| `knowledge_base/arabizi_vocabulary.json` | JSON: `version`, `description`, `sectors`, `term_metadata` | Runtime Arabizi vocabulary used by routing/classification. |
| `knowledge_base/cedarfix_language_bank.csv` | 5,772 | Approved terms, variants, Arabic/English meanings, sector/issue hints, constraints, and review status. |
| `knowledge_base/cedarfix_language_bank_review_queue.csv` | 7,298 | Candidate language-bank rows pending review. |
| `knowledge_base/cedarfix_complaint_scenario_inventory.csv` | 165 | Scenario inventory with sectors, assets, failure modes, triggers, evidence, and examples. |
| `knowledge_base/arabizi/lebanese_arabizi_master_index.csv` | 31,032 | Large master index of Arabizi variants and meanings. |
| `knowledge_base/arabizi/arabizi_master_classification_hard_negatives.csv` | 134 | Hard negatives that should not trigger wrong complaint classes. |
| `knowledge_base/arabizi/arabizi_master_classification_context_guards.csv` | 50 | Context guards for ambiguous tokens. |
| `knowledge_base/arabizi/arabizi_master_hard_negative_candidates.csv` | 71 | Candidate hard negatives for review. |
| `knowledge_base/arabizi/arabizi_oov_review_queue_v1.csv` | 53 | Out-of-vocabulary review queue from language drift/OOV analysis. |
| `knowledge_base/arabizi/arabizi_stoplist.csv` | 77 | Terms that should not auto-promote. |
| `knowledge_base/arabizi/vocab_cleanup_targets.csv` | 1,587 | Cleanup targets and expected rewrites/notes. |

Analysis:

- The project has unusually deep Arabizi coverage: 31,032 master-index rows and
  5,772 approved language-bank rows.
- The review queue is larger than the approved bank, which means the vocabulary
  pipeline still has a substantial backlog.
- Stoplists, hard negatives, and context guards are as important as positive
  vocabulary. They prevent false positives such as treating filler words or
  political statements as municipal infrastructure complaints.

### Entity JSON Knowledge Base

`knowledge_base/entities/` contains 21 canonical entity JSON files plus schema,
index, and audit Markdown.

Canonical entity files:

```text
BMLWE, BWE, CD, CDR, CENTRAL_INSPECTION, DGLAC, EDL, EDZ, ISF,
LRA, MEW, MOBILE_OPERATOR, MOE, MOIM, MPWT, MUN, MUNICIPAL_POLICE,
NLWE, OGERO, SLWE, TRA
```

Important support files:

- `entities/_schema_definition.json` defines the entity JSON shape.
- `entities/_entity_index.json` lists canonical entity files and maps many
  sector/issue families to primary/secondary entities and HITL flags.
- `entities/_non_entity_selectors.json` documents routing sentinels such as
  `ALL` and `HITL`, plus dynamic selector expressions that are not dispatchable
  entities.
- `entities/entity_accuracy_audit_*.md`,
  `entities/entity_reliability_audit_*.md`, and
  `entities/entity_human_review_hard_check_2026-05-31.md` document trust
  gaps and source reliability.

Analysis:

- Entity JSON is the key evidence layer for explanations and grounded
  resolution planning.
- The entity catalog is internally complete: 21 rows in
  `public_entities_extended.csv`, 21 JSON files, and 21 index entries.
- Most entity files still have `overall_confidence: medium` and at least one
  open human-review item in `_entity_index.json`; `TRA` is marked high with no
  open human-review item.
- Do not assume an entity JSON is perfect just because it exists. Check
  confidence, human-review notes, fact IDs, and source IDs.

## Sector Knowledge Shards

Sector shards organize routing evidence by domain. They separate production
rows, source evidence, boundary conditions, required fields, SLAs, and research
backlogs.

### Water Establishments

Folder: `knowledge_base/water_establishments/`

This is the richest sector shard and the main model for how future shards
should mature.

| File | Rows | Meaning |
| --- | ---: | --- |
| `water_entity_resolution.csv` | 1,107 | Registry-row-to-water-establishment resolver for all registry rows. Runtime-critical. |
| `source_registry.csv` | 85 | Water-specific source evidence. |
| `contact_points.csv` | 48 | Offices, phones, emails, addresses, working hours. |
| `complaint_channels.csv` | 31 | Complaint/service request channels. |
| `branch_service_areas.csv` | 29 | Branch-level routing hints. |
| `water_service_catalog.csv` | 18 | Service categories and complaint types. |
| `required_fields.csv` | 118 | Officially published or explicitly missing required fields. |
| `boundary_conditions.csv` | 13 | Routing guardrails. |
| `not_responsible_for.csv` | 12 | Negative responsibility boundaries. |
| `sla_policy.csv` | 13 | Published/not-published SLA policy. |
| `coverage_summary.csv` | 5 | High-level coverage summary. |
| `trusted_context.csv` | 26 | Institutional context; not direct intake truth. |
| `irl_complaint_patterns.csv` | 15 | Anonymized real-life patterns for eval/HITL design. |
| `irrigation_boundaries.csv` | 9 | LRA/private well/irrigation boundary cases. |
| `page_inventory.csv` | 177 | Scraped inventory for review, not production truth. |
| `source_candidate_review.csv` | 177 | Ranked triage from page inventory. |
| `research_backlog.csv` | 14 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `water_establishments_dossier.md`
- `water_dimension_audit.md`
- `water_production_audit_report.md`
- `scrape_run_report.md`

### Electricity

Folder: `knowledge_base/electricity/`

| File | Rows | Meaning |
| --- | ---: | --- |
| `electricity_entity_resolution.csv` | 1,107 | Registry-row-shaped electricity resolver, including EDL/EDZ boundaries; all rows have non-empty resolver IDs. |
| `source_registry.csv` | 8 | Electricity-specific evidence. |
| `contact_points.csv` | 8 | EDL/EDZ/MEW/CD contact points. |
| `complaint_channels.csv` | 7 | Complaint and service channels. |
| `required_fields.csv` | 8 | Required fields and not-published markers. |
| `boundary_conditions.csv` | 9 | EDL vs EDZ, generator, internal wiring, streetlight, sparking wire, transformer/fire boundaries. |
| `not_responsible_for.csv` | 7 | Negative responsibility boundaries. |
| `sla_policy.csv` | 5 | SLA policy and not-published restoration cautions. |
| `research_backlog.csv` | 7 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `electricity_dossier.md`
- `electricity_dimension_audit.md`

### Telecom

Folder: `knowledge_base/telecom/`

| File | Rows | Meaning |
| --- | ---: | --- |
| `contact_points.csv` | 6 | OGERO/TRA contacts and handoffs. |
| `complaint_channels.csv` | 7 | Fixed telecom and regulatory channels. |
| `source_registry.csv` | 5 | Telecom shard source evidence copied from root source IDs for local Copilot/agent lookup. |
| `required_fields.csv` | 8 | OGERO fixed-fault and TRA escalation fields. |
| `boundary_conditions.csv` | 8 | OGERO vs mobile/TRA/private device/ISP boundaries. |
| `not_responsible_for.csv` | 6 | Negative responsibility boundaries. |
| `sla_policy.csv` | 4 | SLA policy; do not invent repair times. |
| `research_backlog.csv` | 6 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `telecom_dossier.md`
- `telecom_dimension_audit.md`

### Roads and Public Works

Folder: `knowledge_base/roads_public_works/`

| File | Rows | Meaning |
| --- | ---: | --- |
| `contact_points.csv` | 6 | MPWT/MUN/CDR-style contacts and handoffs. |
| `complaint_channels.csv` | 5 | Complaint/service channels. |
| `source_registry.csv` | 22 | Roads/public works source evidence copied from root source IDs plus shard-local NNA evidence for named road/project events. |
| `road_class_ownership_index.csv` | 12 | Seed ownership/context index for local-road and national-road guardrails plus named MPWT/CDR/MUN road, bridge, drainage, snow, and project signals. |
| `required_fields.csv` | 7 | Required fields for road/public works complaints. |
| `boundary_conditions.csv` | 9 | Local road vs national/classified road vs CDR/project owner vs emergency boundaries. |
| `not_responsible_for.csv` | 5 | Negative boundaries. |
| `sla_policy.csv` | 4 | SLA policy; avoid unverified timelines. |
| `research_backlog.csv` | 4 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `roads_public_works_dossier.md`
- `roads_public_works_dimension_audit.md`

### Public Safety and Enforcement

Folder: `knowledge_base/public_safety_enforcement/`

| File | Rows | Meaning |
| --- | ---: | --- |
| `civil_defense_entity_resolution.csv` | 1,107 | Registry-row-shaped Civil Defense resolver; all rows have non-empty resolver IDs. |
| `source_registry.csv` | 1 | Shard-specific source evidence. |
| `contact_points.csv` | 8 | Civil Defense/ISF/municipal enforcement contacts. |
| `complaint_channels.csv` | 7 | Safety/enforcement channels. |
| `required_fields.csv` | 9 | Required fields. |
| `boundary_conditions.csv` | 10 | Emergency, crime, rescue, obstruction, corruption, and municipal enforcement boundaries. |
| `not_responsible_for.csv` | 6 | Negative boundaries. |
| `sla_policy.csv` | 5 | SLA/emergency policy. |
| `research_backlog.csv` | 5 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `public_safety_enforcement_dossier.md`
- `public_safety_enforcement_dimension_audit.md`

### Waste and Environment

Folder: `knowledge_base/waste_environment/`

| File | Rows | Meaning |
| --- | ---: | --- |
| `contact_points.csv` | 6 | Municipality/MOE/CD handoff contacts. |
| `complaint_channels.csv` | 5 | Waste/environment channels. |
| `source_registry.csv` | 16 | Waste/environment source evidence copied from root source IDs for local Copilot/agent lookup. |
| `required_fields.csv` | 7 | Required fields. |
| `boundary_conditions.csv` | 9 | Routine waste vs hazardous/industrial/river/fire/crime boundaries. |
| `not_responsible_for.csv` | 5 | Negative boundaries. |
| `sla_policy.csv` | 4 | SLA policy; avoids invented service times. |
| `research_backlog.csv` | 4 | Remaining tasks. |

Key documents:

- `CONTENTS.md`
- `waste_environment_dossier.md`
- `waste_environment_dimension_audit.md`

### Channel Discovery

Folder: `knowledge_base/channel_discovery/`

| File | Rows | Purpose |
| --- | ---: | --- |
| `complaint_source_universe.csv` | 52 | Universe of source families and what each can/cannot prove. |
| `municipality_channel_discovery_backlog.csv` | 24 | Backlog for discovering municipality complaint channels. |
| `municipality_do_not_scrape.csv` | 9 | Sources/URLs that should not be scraped and handling rules. |
| `CONTENTS.md` | doc | Folder guide. |

## Training Data

Folder: `training/`

| File | Rows | Role | Notes |
| --- | ---: | --- | --- |
| `cidarfix_v29_batch8_train_v14_enriched.jsonl` | 91,150 | train | IEP-1 classifier training set. This is the only training file referenced by `src/iep1/semantic_classifier.py`. |
| `cidarfix_v29_batch8_val_v14_enriched.jsonl` | 10,562 | validation | Same distribution holdout for model selection; do not treat as final eval. |
| `cidarfix_v29_batch7_model_final_test_locked.jsonl` | 7,940 | locked test | Do not modify or train on this file. |
| `cidarfix_telecom_eval_locked.jsonl` | 150 | diagnostic locked eval | `_split_manifest.json` says it overlaps validation by construction; not an independent final holdout. |
| `cidarfix_v29_top_tier_generated_v1.jsonl` | 242 | reference | Curated high-quality examples for review/future few-shot prompting. |
| `_data_manifest.json` | JSON | provenance | Row counts, hashes, roles, split policy, and usage notes generated 2026-06-01. |
| `_split_manifest.json` | JSON | split audit | Overlap proof after split cleanup; warns about telecom eval/validation overlap. |
| `finetuning_manifest_v1.json` | JSON | fine-tuning metadata | Fine-tuning run metadata. |
| `_backups/cidarfix_v29_batch8_train_v14_enriched.jsonl.before_split_clean.jsonl` | backup | backup | Pre-clean backup of training data. |

Important interpretation:

- `train` is trainable.
- `validation` is for tuning/model selection.
- `locked test`, `diagnostic locked eval`, and `gold_ood_eval` are not training
  material.
- The manifest sector counts are `UNKNOWN` because the manifest script did not
  infer sector labels from the JSONL structure. Do not infer that the corpus has
  no sector labels from that field alone.

## Evaluation Fixtures

Folder: `eval/`

These are behavior contracts. They should be treated as locked benchmarks unless
you intentionally create a new version.

| File | Rows | Main use |
| --- | ---: | --- |
| `water_establishments_routing_eval_v1.jsonl` | 355 | Water routing OOD fixture. |
| `arabizi_master_hard_negative_eval_cases.jsonl` | 304 | Adversarial Arabizi hard negatives and ambiguity cases. |
| `arabic_multilingual_routing_eval_v1.jsonl` | 50 | Arabic/multilingual routing checks. |
| `electricity_routing_eval_v1.jsonl` | 50 | Electricity routing guardrails. |
| `roads_public_works_routing_eval_v1.jsonl` | 50 | Roads/public works routing guardrails. |
| `waste_environment_routing_eval_v1.jsonl` | 50 | Waste/environment routing guardrails. |
| `telecom_routing_eval_v1.jsonl` | 50 | Telecom routing guardrails. |
| `public_safety_enforcement_routing_eval_v1.jsonl` | 50 | Safety/enforcement routing guardrails. |
| `image_hazard_fusion_eval_v1.jsonl` | 45 | IEP-6 image/text fusion benchmark. |
| `resolution_grounding_eval_v1.jsonl` | 24 | IEP-8 grounded-resolution benchmark. |
| `flooding_routing_eval_v1.jsonl` | 20 | Flooding/drainage routing and safety gates. |
| `flooding_routing_known_divergences_v1.jsonl` | 6 | Known divergences for flooding behavior. |
| `arabizi_excellence_gates_v1.json` | JSON | Arabizi excellence gate artifact. |
| `cedarfix_next_phase_gates_v1.json` | JSON | Next-phase gate artifact. |

Metadata note:

- Current filesystem row counts are listed above.
- `_data_manifest.json` was generated on 2026-06-01 and is useful for provenance,
  hashes, and split policy. If eval files are changed, regenerate or refresh the
  manifest so row counts and hashes do not drift.

## Complaint Intelligence Research

Folder: `complaint_intelligence/`

This is a research and source-normalization layer. It is useful for expanding
the KB or generating future eval candidates, but it is not the same as runtime
truth.

| File | Rows/shape | Purpose |
| --- | ---: | --- |
| `NEXT_DATA.md` | doc | Prioritized next-data acquisition plan for humans and code assistants. |
| `next_data_acquisition_queue.csv` | 20 | Machine-readable P0/P1/P2 acquisition queue for channels, unions, roads, waste, telecom, outcomes, evals, and privacy. |
| `source_targets.csv` | 169 | Source targets and search/discovery planning. |
| `discovered_complaint_leads.csv` | 156 | Leads discovered from public/official sources. |
| `municipality_research_tracker.csv` | 800 | Municipality research status rows. This is research coverage, not the full registry count. |
| `municipality_source_research.csv` | 12 | Candidate source research rows. |
| `scaleout_research_tasks.csv` | 12 | Research task list. |
| `scaleout_research_findings.csv` | 44 | Findings from scaleout research. |
| `normalized/municipal_official_process_seed.jsonl` | 78 | Normalized civic/official process events. |
| `complaint_resolution_event.schema.json` | JSON schema | Schema for normalized complaint-resolution events. |
| `news_followup_promotion_policy.json` | JSON policy | Policy for when news/source followups can be promoted. |

Use this area when:

- collecting real-world civic process examples;
- finding future municipality complaint channels;
- generating source-backed eval ideas;
- tracking which sources are promising but not yet production-ready.

Do not directly route production complaints from this folder.

## Review Queues

Folder: `review_queue/`

These files hold human-review work items from legacy corpus audits. They are
useful for improving training data and moderation boundaries, but should not be
treated as clean labels until reviewed.

| File | Rows | Purpose |
| --- | ---: | --- |
| `cedarfix_legacy_100k_review_queue.csv` | 2,215 | General review queue. |
| `cedarfix_legacy_100k_abusive_language_queue.csv` | 1,163 | Abusive-language queue. |
| `cedarfix_legacy_100k_political_statement_queue.csv` | 688 | Political-statement queue. |
| `cedarfix_legacy_100k_political_mixed_infra_queue.csv` | 20 | Mixed political/infrastructure queue. |
| `cedarfix_legacy_100k_political_mixed_infra_decisions.csv` | 32 | Human/auto decisions already made for mixed cases. |

## Data Health Analysis

Strengths:

- Strong municipality backbone: 1,107 unique `registry_id` registry rows, 3,870
  alias rows, and 1,107 service-mapping rows.
- Strong water routing depth: 1,107 water resolver rows plus contacts, channels,
  required fields, boundary conditions, source registry, audit report, and eval.
- Strong language depth: 31,032 Arabizi master-index rows, 5,772 approved
  language-bank rows, 7,298 review candidates, hard negatives, context guards,
  and stoplists.
- Multi-sector eval coverage exists for water, electricity, roads/public works,
  waste/environment, telecom, public safety/enforcement, flooding, image fusion,
  grounding, Arabic multilingual routing, and Arabizi hard negatives.
- Entity JSON files exist for 21 canonical public entities/categories and are connected to
  source-backed dossiers/audits.
- Roads/public works, telecom, and waste/environment now have shard-level
  source registries so code assistants do not need to jump to the root source
  registry to understand local evidence.

Known gaps and cautions:

- Municipality official channel/workflow coverage is much smaller than the full
  municipality registry. This is expected but important.
- Municipal union membership is now row-level across all 59 union IDs, but 57
  source-specific text rows still need manual registry reconciliation.
- Municipal union service responsibility is only seeded. The current service
  responsibility file proves intake/advocacy signals, not full operator or
  field-service ownership for every union.
- Municipality identity columns are not fully normalized: 307 registry rows do
  not have official `municipality_id`, so runtime joins must keep using
  `registry_id` fallback.
- Roads/public works, telecom, and waste/environment still need deeper
  operational datasets: road-class ownership, CDR project areas, waste
  operators/sites, mobile-operator channels, and outcome evidence.
- Several canonical entity JSON files still carry medium confidence and open
  human-review items.
- Candidate/research files are intentionally noisy. Promote them only after
  source-backed review.
- The telecom locked eval is diagnostic because it overlaps validation by
  construction, according to `_split_manifest.json`.
- Many SLA tables explicitly say restoration timelines are not published. Do
  not generate promised repair deadlines unless a source-backed row supports it.

## Next Data Acquisition

The next data priority is operational evidence, not more raw municipality names.
The full plan lives in `complaint_intelligence/NEXT_DATA.md`, and the executable
queue lives in `complaint_intelligence/next_data_acquisition_queue.csv`.

Start with these P0 lanes:

1. Verify and promote the first 200 municipality contact candidates into
   official channel/workflow rows.
2. Complete municipal union memberships and create a shared-service
   responsibility table for union-level waste, roads, drainage, lighting, and
   public-space handling.
3. Continue roads/public-works ownership data: the seed
   `road_class_ownership_index.csv` now covers 12 guardrail/named-event rows,
   but official classified-road geometry, MPWT operational contacts, and CDR
   project service areas still need expansion.
4. Build waste/environment operations data: waste operators, union coverage,
   landfill/dump/transfer/sorting sites, and MoE category-specific fields.
5. Deepen telecom data: OGERO form/app/1515 fields, Alfa/Touch official
   channels, TRA escalation field/deadline wording, and private-device/private
   ISP exclusions.
6. Start outcome and human-override capture using
   `complaint_resolution_event.schema.json` so real accepted/rejected/resolved
   routes can calibrate IEP-7 and future evals.

Do not bulk collect private channels, citizen comments with PII, unverified
directory contacts, or generic examples that do not target a routing failure.

## Common Lookup Recipes

Use these recipes when writing code or asking Copilot to reason over data.

### Find a municipality from text

1. Normalize the location phrase.
2. Search `knowledge_base/municipalities/municipality_aliases.csv`.
3. Join to `national_municipality_registry.csv` for canonical names, district,
   governorate, coordinates, and quality fields.
4. If GPS exists, use registry/townhall coordinates or router GPS logic.

### Route a water complaint

1. Use IEP-1/route logic to classify the issue as water.
2. Resolve municipality from alias or GPS.
3. Use `municipality_service_mappings.csv` and
   `water_establishments/water_entity_resolution.csv`.
4. Check `water_establishments/boundary_conditions.csv` and
   `not_responsible_for.csv`.
5. Use `complaint_channels.csv`, `required_fields.csv`, and `sla_policy.csv`
   only for supported explanation/resolution details.

### Add a new production routing fact

1. Put candidate evidence in a review/backlog file first if unsure.
2. Add or reuse a source ID in the appropriate source registry.
3. Add the production row to the runtime table.
4. Add/update a routing or grounding eval fixture.
5. Run the relevant validation/evaluation scripts.
6. Update this README if row counts or file roles changed.

### Add a new eval case

1. Add the case to the relevant `data/eval/*_vN.jsonl` file only if the expected
   behavior is stable and source-backed.
2. If behavior intentionally changes, prefer a new fixture version.
3. Do not reuse train/validation rows as gold OOD eval examples.
4. Update `_data_manifest.json` or a successor manifest if hashes/counts matter.

## Validation Commands

Run from the repository root.

```powershell
python scripts/validate_water_establishments_kb.py
python scripts/validate_electricity_kb.py
python scripts/audit_water_production_pack.py
python scripts/evaluate_water_routing.py
python scripts/evaluate_electricity_routing.py
python scripts/evaluate_flooding_routing.py
python scripts/evaluate_telecom_routing.py
python scripts/evaluate_roads_public_works_routing.py
python scripts/evaluate_public_safety_enforcement_routing.py
python scripts/evaluate_waste_environment_routing.py
python -m pytest scripts/tests -q
```

Use focused tests when editing one area:

```powershell
python -m pytest scripts/tests/test_iep1_*.py -q
python -m pytest scripts/tests/test_iep3_*.py -q
python -m pytest scripts/tests/test_iep6_*.py -q
python -m pytest scripts/tests/test_iep8_*.py -q
```

## Maintenance Checklist

Before committing data changes:

- Confirm whether the file is runtime, training, eval, research, or review.
- Preserve IDs and stable schemas.
- Recount rows if this README lists the file.
- Update manifests when hashes/roles/counts are used for leakage prevention.
- Run the smallest relevant validator/evaluator.
- Add a note to a dossier/audit report when the change affects source-backed
  civic responsibility, contact channels, SLAs, or HITL boundaries.
