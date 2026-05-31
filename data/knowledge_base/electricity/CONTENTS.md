# electricity/ - What's in this folder

Generated: 2026-05-31

This folder keeps electricity-specific routing research separate from the general entity registry.

## Files

### `electricity_dossier.md`
Source-backed dossier for EDL, EDZ, MEW electricity oversight, Civil Defense emergency boundary cases, municipal streetlights, and private-generator boundaries.

### `source_registry.csv`
Electricity-specific source registry shard. It adds fresh browser/fetch evidence for EDL, Civil Defense, and MEW pages while reusing core source IDs from the main registry where appropriate.

### `contact_points.csv`
Hotlines, contact forms, office contacts, and emergency contacts for EDL, EDZ, MEW, Civil Defense, and municipality streetlight handoff.

### `complaint_channels.csv`
Complaint and service channels by entity and electricity complaint type.

### `required_fields.csv`
Officially published required fields plus conservative `not_published` markers.

### `boundary_conditions.csv`
Routing guardrails for EDL versus EDZ, private generators, internal wiring, streetlights, sparking wires, transformer/fire hazards, meter/billing issues, and MEW escalation.

### `not_responsible_for.csv`
Negative responsibility boundaries used to prevent false routing to EDL or EDZ.

### `sla_policy.csv`
Official SLA and response-time policy table. Generic restoration SLAs remain not published.

### `research_backlog.csv`
Remaining verification tasks.

### `electricity_dimension_audit.md`
Screenshot-dimension audit and production-readiness notes for the electricity shard.