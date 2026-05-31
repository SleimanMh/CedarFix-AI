# water_establishments/ - What's in this folder

Generated: 2026-05-31

This folder keeps water-establishment-specific knowledge-base research separate from the general source registry and channel discovery files.

## Files

### `water_establishments_dossier.md`
Source-backed dossier for BMLWE/EBML, NLWE/EELN, SLWE, BWE, MEW water oversight, and LRA irrigation boundary cases.

Use for: water routing policy, complaint-channel evidence, required fields, HITL rules, and official source URLs.

### `water_dimension_audit.md`
Screenshot-dimension audit for the water shard.

Use for: checking what is complete, what is production-synced, and which true gaps remain before expanding the next entity family.

### `source_registry.csv`
Water-establishment source registry shard.

Contains official and partner source rows for BMLWE, NLWE, SLWE, BWE, MEW water-establishment oversight, and LRA irrigation-boundary evidence.

The core router-facing rows remain in the main KB tables, especially `../public_entities_extended.csv` and `../entity_service_area_mapping.csv`.

### `page_inventory.csv`
Machine-generated inventory of official and partner pages discovered by `../../scripts/scrape_water_establishment_coverage.py`.

Use as a review queue for future source promotion, not as a production authority by itself.

### `source_candidate_review.csv`
Ranked triage output generated from `page_inventory.csv` by `../../scripts/triage_water_inventory_candidates.py`.

Use for: deciding which official pages should be promoted into `source_registry.csv`, which are already registered, and which should stay as later-review or low-signal crawl context.

### `scrape_run_report.md`
Latest crawler summary with page counts, candidate pages, and source-candidate review hints.

### `coverage_summary.csv`
High-level official and runtime coverage summary for the four water establishments plus LRA boundary context.

### `water_entity_resolution.csv`
Canonical router-facing resolver from municipality/registry key to BMLWE, NLWE, SLWE, or BWE, with branch/service-center hints, source IDs, confidence, verification status, and retrieval date.

Use for: production water routing after location extraction or GPS-to-municipality resolution.

### `contact_points.csv`
Hotlines, main offices, branch offices, distribution office phones, emails, addresses, working hours, source IDs, and confidence notes.

### `branch_service_areas.csv`
Branch-level routing hints that connect contact points to districts or service areas. Use after entity-level location routing.

### `complaint_channels.csv`
Complaint and service-request channels by entity and complaint type, including phone, online form, ticketing, walk-in, e-services, and partner payment channels.

### `required_fields.csv`
Officially published complaint fields, service-request documents, contact-form fields, and explicit `not_published` markers where pages do not disclose requirements.

### `water_service_catalog.csv`
Normalized service categories and complaint types per entity, with accepted and not-accepted boundaries.

### `not_responsible_for.csv`
Per-entity negative responsibility boundaries and alternate routing targets.

Use for: avoiding false positives such as private plumbing, private wells, storm drains, tanker/vendor disputes, LRA irrigation assets, and MEW-as-field-dispatch mistakes.

### `trusted_context.csv`
Trusted sector context from official strategy pages and institutional sources such as UNICEF and the World Bank.

Use for: policy, emergency, system-constraint, partner-support, and strategic-program context. Do not use it as a direct citizen intake table or to infer unpublished SLAs.

### `irl_complaint_patterns.csv`
Anonymized real-life complaint and incident patterns from institutional survey evidence, official/institutional stories, and public media reports.

Use for: eval generation, HITL trigger design, false-positive boundaries, and realistic citizen-language scenarios. Do not store personal names, phone numbers, account numbers, or social-media handles here.

### `boundary_conditions.csv`
Routing guardrails for private plumbing, missing location, storm drain versus sewer, emergency flooding, dirty water, pump electricity, MEW escalation, and BWE cutoff cases.

### `irrigation_boundaries.csv`
LRA, Litani, Qasimiya/Ras Al Ain, Bekaa irrigation, private wells, and source-pollution boundary cases.

### `sla_policy.csv`
Official SLA and response-time policy table. Most repair SLAs remain `not_published`; do not promise restoration times unless an official notice says so.

### `research_backlog.csv`
Remaining verification tasks for form fields, ticket/reference behavior, app workflows, official SLA gaps, LRA maps, and branch details.

### `water_production_audit_report.md`
Generated water-only production audit report.

Use for: final readiness checks across resolver coverage, contacts, channels, required fields, not-responsible rows, SLA policy, eval pass rate, and provenance enforcement.
