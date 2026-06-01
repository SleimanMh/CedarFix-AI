# telecom/ - What's in this folder

Generated: 2026-05-31

This folder keeps telecom-specific routing research separate from the general entity registry.

## Files

### `telecom_dossier.md`
Source-backed routing dossier for Ogero fixed telecom faults, TRA consumer escalation, mobile-network boundaries, private CPE/router boundaries, and private ISP/satellite boundaries.

### `source_registry.csv`
Telecom shard source registry. It mirrors the relevant root source IDs
(`SRC-OGERO-*`, `SRC-TRA-*`) to avoid duplicate IDs while still making local
source evidence visible inside the telecom folder.

### `contact_points.csv`
Ogero and TRA contact points plus boundary handoffs.

### `complaint_channels.csv`
Complaint and service channels by entity and telecom complaint type.

### `required_fields.csv`
Fields needed for Ogero fixed faults and TRA escalation.

### `boundary_conditions.csv`
Routing guardrails for Ogero versus mobile operators/TRA, private router/device issues, private ISP/satellite service, public cable/cabinet damage, and missing location/line details.

### `not_responsible_for.csv`
Negative responsibility boundaries used to prevent false routing to Ogero or TRA.

### `sla_policy.csv`
Official SLA and response-time policy table. Generic repair SLAs remain not promised unless source-backed.

### `research_backlog.csv`
Remaining verification tasks.

### `telecom_dimension_audit.md`
Screenshot-dimension audit and production-readiness notes for the telecom shard.
