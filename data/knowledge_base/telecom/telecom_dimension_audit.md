# Telecom Dimension Audit

Generated: 2026-06-02

| Dimension | Status | Evidence |
|---|---|---|
| Legal responsibility | Strong | `public_entities_extended.csv`, `boundary_conditions.csv`, `not_responsible_for.csv` |
| Primary/secondary complaint types | Strong | `complaint_taxonomy.csv`, `routing_rules.csv`, `complaint_channels.csv` |
| Not responsible for | Complete for current routing | `not_responsible_for.csv` |
| Boundary conditions | Complete for current routing | `boundary_conditions.csv` |
| Geographic coverage | Medium-high | Ogero is national fixed operator; Alfa/Touch national operator-first channels are seeded; cell-site or outage-area coverage remains backlog |
| Emergency/non-emergency contacts | Strong for Ogero, TRA, Alfa, and Touch public channels | `contact_points.csv`, `mobile_operator_channels.csv` |
| Emails | Strong for Ogero and TRA root entity rows | `public_entities_extended.csv` |
| Website/forms | Strong channel URLs; exact Ogero form fields partial | `complaint_channels.csv`, `research_backlog.csv` |
| Required fields | Conservative | `required_fields.csv`, `mobile_operator_channels.csv` |
| Ticket/reference number | Partial by design | Ogero ticket/reference behavior needs browser extraction |
| Official SLA | Partial | Ogero fixed-line 3-working-day guidance and TRA 10/20-day escalation signal are captured; Alfa/Touch restoration SLAs are not captured |
| HITL flags | Complete for current routing | private CPE, private ISP, missing fixed-line location/account, cable/cabinet public obstruction |

## Remaining True Gaps

- Exact Ogero public fault/contact form fields and reference-number behavior.
- TRA exact public complaint field list and legal deadline wording.
- Alfa/Touch exact form fields, email endpoints, status histories, ticket behavior, restoration SLAs, and possible entity modeling.
- Private ISP/reseller/satellite official regulatory handling.
- Emergency handling for fallen telecom poles/cables that create road or life-safety hazards.

## Validation

- Run `scripts/validate_telecom_kb.py` after changes.
