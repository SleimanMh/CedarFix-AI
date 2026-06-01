# channel_discovery/ — What's in this folder

Generated: 2026-05-30  
Source: `cedarfix_three_reports_full_extraction_csvs.zip` (3 deep-research reports, Phases 1 & 2)

---

## Files

### `complaint_source_universe.csv` — 52 rows
All complaint-related sources and platforms identified across the three reports, deduplicated.  
Columns: `source_id, source_name, source_url, source_family, can_prove, cannot_prove`

Includes: official municipality websites, Al Fayhaa Union portal, Baladi Map, Baldati app, national-level bodies (Central Inspection, NACC), WhatsApp-based channels, and aggregator platforms.  
Use for: source prioritisation, scraping strategy, routing rule drafting.

---

### `municipality_channel_discovery_backlog.csv` — 24 rows
Open research tasks for high-priority municipalities where **no verified official complaint channel was found** in Phase 1/2.  
Columns: `task_id, municipality_id_if_known, municipality_name_ar, municipality_name_en, governorate, district, target_url_or_query, reason, status, priority, last_checked, notes`

Priority breakdown:
- `high` — Beirut, Saida, Tyre, Baalbek, Byblos (Jbail), Jounieh, Bsharri, and more (no channel verified at all)
- `manual_review` — Byblos (official domain currently serving default forum content)

**This is the Phase 3 research queue.** Work through `status=open, priority=high` first.

---

### `municipality_do_not_scrape.csv` — 9 rows
URLs and platforms that must NOT be scraped aggressively or need manual review before any automated access.  
Columns: `source_url, handling_rule_or_reason, status`

Flagged sources: Aley complaint form (bot wall), Nabay complaint/suggestion forms (406), El-Beddawi forms (406), Moukhtara (bot verification), Byblos official domain (appears compromised), Jounieh (502), Bsharri (503), all Facebook page URLs (rate-limited), Baldati.app (JS-only).

---

## What was merged into existing KB files (same commit)

| File | Change |
|---|---|
| `municipalities/municipality_official_channels.csv` | +8 rows: Aley (website, contact page, complaint form), Nabatieh (website, generic contact), Zouk Mikael (website, contact page, app) |
| `municipalities/municipality_complaint_workflows.csv` | +1 row: Aley complaint form (`blocked_needs_manual_review`, official route confirmed via homepage nav) |

Municipalities already in the KB were not duplicated (Tripoli, Zahle, Ras El-Matn, El-Beddawi, Nabay, Al Fayhaa Union).

---

## Related Entity Shards

- `../water_establishments/` holds the structured water-establishment routing shard.
- `../electricity/` holds the structured electricity routing shard for EDL, EDZ, Civil Defense electrical emergencies, municipal streetlights, and private-generator boundaries.
- `../telecom/` holds the structured telecom routing shard for Ogero, TRA, mobile-operator boundaries, private CPE, and private ISP cases.
- `../roads_public_works/` holds the structured roads/public-works routing shard for local roads, MPWT national/classified road boundaries, CDR project ambiguity, and road-safety escalation.
- `../waste_environment/` holds the structured waste/environment routing shard for municipal waste, MOE environmental complaints, hazardous waste, river/quarry pollution, and emergency fire/hazard boundaries.
- `../public_safety_enforcement/` holds the structured public-safety/enforcement shard for Civil Defense, ISF, municipal police, municipal enforcement, DGLAC, MOIM, and Central Inspection boundaries.
