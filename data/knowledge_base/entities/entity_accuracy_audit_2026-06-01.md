# Entity Accuracy Audit

Generated: 2026-06-01

## Verdict

The entity dossier layer is source-registered: every entity JSON has the required core fact types and no legacy or unregistered source IDs. Remaining weak operational fields are intentionally surfaced as review flags instead of being treated as verified facts.

## Summary

- Public entity rows: 18
- Entity JSON dossiers: 18
- Registered source IDs: 182
- `source_registered`: 18
- Registry warning: exact duplicate source IDs de-duplicated across registries: 86

## Entity Dossier Coverage

| Entity | Status | Facts | Missing fact types | Unregistered sources | Weak operational fields |
|---|---:|---:|---|---|---|
| BMLWE | source_registered | 7 | - | - | - |
| BWE | source_registered | 7 | - | - | ticket_reference_policy |
| CD | source_registered | 8 | - | - | ticket_reference_policy |
| CDR | source_registered | 7 | - | - | ticket_reference_policy |
| CENTRAL_INSPECTION | source_registered | 7 | - | - | non_emergency_phone, official_email |
| DGLAC | source_registered | 7 | - | - | - |
| EDL | source_registered | 7 | - | - | ticket_reference_policy |
| EDZ | source_registered | 8 | - | - | - |
| ISF | source_registered | 8 | - | - | - |
| MEW | source_registered | 7 | - | - | ticket_reference_policy |
| MOE | source_registered | 8 | - | - | - |
| MOIM | source_registered | 6 | - | - | official_email, ticket_reference_policy |
| MPWT | source_registered | 7 | - | - | ticket_reference_policy |
| MUN | source_registered | 7 | - | - | emergency_hotline, non_emergency_phone, official_email, hq_address, complaint_channel_types, ticket_reference_policy |
| NLWE | source_registered | 6 | - | - | ticket_reference_policy |
| OGERO | source_registered | 8 | - | - | - |
| SLWE | source_registered | 6 | - | - | ticket_reference_policy |
| TRA | source_registered | 6 | - | - | - |

## Blocking Accuracy Issues

- No blocking accuracy issues found in entity JSON source registration.

## Root CD.json Template Check

- Status: `source_registered`
- Facts: 9
- Unregistered source IDs: -
- Legacy source IDs: -
- Accuracy note: the Civil Defense template now uses registered current-registry source IDs for the official homepage, contact page, centers page, historical station map, hotline evidence, and UNDP context source.

## Recommended Accuracy Gate

1. Keep all entity JSON source IDs in the registered `SRC-ENTITY-DESCRIPTOR` scheme; do not reintroduce legacy `SRC-###` IDs.
2. Register any newly verified official pages before using them in high-confidence facts.
3. Keep unavailable, account-gated, not-applicable, or unpublished operational fields as low/medium confidence with `human_review_required: true`.
4. Expand weak operational fields only when a source-backed official channel or SLA is verified.
5. Re-run this audit after every entity-dossier update.

