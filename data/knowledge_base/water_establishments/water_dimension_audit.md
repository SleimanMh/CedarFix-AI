# Water Establishments Dimension Audit

Generated: 2026-05-31

Scope: BMLWE, NLWE, SLWE, BWE, MEW oversight, and LRA boundary cases.

## Status

| Dimension | Status | Evidence |
|---|---|---|
| Legal responsibility | Complete | `water_service_catalog.csv`, `not_responsible_for.csv`, `boundary_conditions.csv` |
| Primary/secondary complaint types | Complete | `water_service_catalog.csv`, `complaint_channels.csv`, router subtype rules |
| Not responsible for | Complete for water scope | `not_responsible_for.csv` has 12 per-entity/authority boundary rows |
| Boundary conditions | Complete for current routing | `boundary_conditions.csv`, `irrigation_boundaries.csv`, `irl_complaint_patterns.csv` |
| Geographic coverage | Complete at runtime entity level | `coverage_summary.csv`, `branch_service_areas.csv`, `water_entity_resolution.csv` |
| Municipality to WE mapping | Complete in canonical resolver | `water_entity_resolution.csv` has 1,094 municipality/registry-key rows |
| Branch/service-center coverage | Strong but not perfect | BMLWE/NLWE/BWE branch addresses; SLWE district phones without addresses |
| Emergency/non-emergency contacts | Strong | `contact_points.csv`, `complaint_channels.csv`; no generic emergency hotline published for all WEs |
| Emails | Strong where published | BMLWE, NLWE, BWE, MEW, SLWE e-payment page; gaps marked not_published/needs verification |
| Website/forms | Strong | `source_registry.csv`, `complaint_channels.csv`, `required_fields.csv` |
| Online/phone/walk-in modes | Complete for known channels | `complaint_channels.csv` |
| Required fields | Strong | 94 rows in `required_fields.csv`; EBML in-app ticket fields still not visible |
| Ticket/reference behavior | Partial by design | Public ticket/reference policies mostly not published; EBML ticketing exists but reference behavior needs browser/app verification |
| Official SLA | Complete as not-published policy | `sla_policy.csv`; do not promise restoration times |
| Operational SLA numbers | Not promoted | Trusted sources do not publish entity-level restoration deadlines |
| HITL flags | Complete for current routing | Router guardrails plus `boundary_conditions.csv` |
| IRL complaint patterns | Added | `irl_complaint_patterns.csv` has 15 anonymized source-backed patterns |
| Trusted sector context | Added | `trusted_context.csv` has 26 official/institutional context rows |

## Production Sync

- `src/route_complaint.py` now resolves `WATER_ESTABLISHMENT_BY_LOCATION` through `water_entity_resolution.csv` and distinguishes water outage, dirty water, pipe leak, low pressure, billing/subscription, sewage, irrigation, private plumbing, private well, tanker dispute, and LRA irrigation boundary cases.
- Missing water location now returns `HITL` with `WATER_ESTABLISHMENT_BY_LOCATION` as the secondary selector instead of choosing a regional WE blindly.
- HITL reason codes are emitted for water boundaries, including `missing_location`, `dirty_water_public_health`, `sewage_public_health`, `irrigation_lra_overlap`, `irrigation_asset_unclear`, `private_well_unclear_authority`, `private_well_license`, and `water_emergency_first`.
- `data/knowledge_base/public_entities_extended.csv` was synced for NLWE and SLWE verified contacts/channels.
- `data/eval/water_establishments_routing_eval_v1.jsonl` and `scripts/evaluate_water_routing.py` cover 355 targeted water-routing cases.
- `scripts/audit_water_production_pack.py` writes `water_production_audit_report.md` with resolver, channel, SLA, eval, and provenance checks.

## Remaining True Gaps

- EBML app/browser ticket fields and public reference-number behavior need interactive verification.
- BWE official site still fails static TLS crawl; official facts are registered, but fresh crawl snapshots should be reattempted separately.
- SLWE official headquarters address remains unverified from the contact page.
- SLWE individual transaction pages and exact document requirements need deeper extraction from customer-service listings.
- LRA municipality-level project overlap remains a research task, especially for Qasimiya/Ras Al Ain irrigation assets.
- Official generic restoration SLAs remain unpublished; keep `do_not_promise_restoration_time`.

## Validation

- `scripts/evaluate_water_routing.py`: 355/355 passed.
- `scripts/validate_water_establishments_kb.py`: passed.
- `scripts/validate_routing_kb.py`: passed.
- `scripts/audit_water_production_pack.py`: passed with 0 provenance issues.
