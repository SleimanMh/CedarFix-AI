# Electricity Dimension Audit

Generated: 2026-05-31

| Dimension | Status | Evidence |
|---|---|---|
| Legal responsibility | Strong | `public_entities_extended.csv`, `boundary_conditions.csv`, `not_responsible_for.csv` |
| Primary/secondary complaint types | Strong | `complaint_taxonomy.csv`, `routing_rules.csv`, `complaint_channels.csv` |
| Not responsible for | Complete for current routing | `not_responsible_for.csv` |
| Boundary conditions | Complete for current routing | `boundary_conditions.csv`, main `entity_boundary_conditions.csv` |
| Geographic coverage | Good at EDL/EDZ level | `municipality_service_mappings.csv`, `entity_service_area_mapping.csv` |
| EDZ exact concession list | Partial | Current service map handles Zahle district; exact 15 surrounding regions remain backlog |
| Emergency/non-emergency contacts | Strong for CD and EDZ; medium for EDL | `contact_points.csv`; EDL page extraction blocked by certificate/static issues |
| Emails | Partial | MEW verified; EDZ/EDL public email handling not fully extracted in shard |
| Website/forms | Strong for EDZ; partial for EDL | `complaint_channels.csv` |
| Online/phone/walk-in modes | Strong for EDZ and CD; medium for EDL/MUN | `complaint_channels.csv` |
| Required fields | Strong for EDZ form; conservative for EDL | `required_fields.csv` |
| Ticket/reference number | Partial by design | No public EDL/EDZ reference policy captured after EDZ validation gate |
| Official SLA | Complete as not-published policy | `sla_policy.csv` |
| HITL flags | Complete for current routing | generator, internal wiring, missing location, sparking/exposed wire, transformer fire |

## Remaining True Gaps

- EDL current official fault/contact form fields and reference-number policy.
- EDZ post-validation complaint fields and reference behavior.
- Exact EDZ concession municipality list beyond the current Zahle-district service-map exception.
- Private-generator official regulatory/local handling path.
- Municipality-specific streetlight channels.

## Validation

- Run `scripts/validate_electricity_kb.py` after changes.