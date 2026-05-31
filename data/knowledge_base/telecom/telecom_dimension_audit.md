# Telecom Dimension Audit

Generated: 2026-05-31

| Dimension | Status | Evidence |
|---|---|---|
| Legal responsibility | Strong | `public_entities_extended.csv`, `boundary_conditions.csv`, `not_responsible_for.csv` |
| Primary/secondary complaint types | Strong | `complaint_taxonomy.csv`, `routing_rules.csv`, `complaint_channels.csv` |
| Not responsible for | Complete for current routing | `not_responsible_for.csv` |
| Boundary conditions | Complete for current routing | `boundary_conditions.csv` |
| Geographic coverage | Medium | Ogero is national fixed operator; mobile operator-specific coverage remains backlog |
| Emergency/non-emergency contacts | Strong for Ogero and TRA | `contact_points.csv` |
| Emails | Strong for Ogero and TRA root entity rows | `public_entities_extended.csv` |
| Website/forms | Strong channel URLs; exact Ogero form fields partial | `complaint_channels.csv`, `research_backlog.csv` |
| Required fields | Conservative | `required_fields.csv` |
| Ticket/reference number | Partial by design | Ogero ticket/reference behavior needs browser extraction |
| Official SLA | Complete as not-published policy | `sla_policy.csv` |
| HITL flags | Complete for current routing | private CPE, private ISP, missing fixed-line location/account, cable/cabinet public obstruction |

## Remaining True Gaps

- Exact Ogero public fault/contact form fields and reference-number behavior.
- TRA exact public complaint field list and deadline wording.
- Alfa/Touch official complaint channels and possible entity modeling.
- Private ISP/reseller/satellite official regulatory handling.
- Emergency handling for fallen telecom poles/cables that create road or life-safety hazards.

## Validation

- Run `scripts/validate_telecom_kb.py` after changes.