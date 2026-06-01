# Roads and Public Works KB Shard

This shard covers routing boundaries for Lebanese local roads, classified/national roads, bridges, sidewalks, blocked roads, snow/storm road incidents, active public-works sites, and CDR project-owner ambiguity.

Runtime scope:
- Local roads, sidewalks, and ordinary potholes route to the resolved municipality.
- Classified/national roads, highways, and bridges route to MPWT with HITL when road class is not independently verified.
- Active CDR/project-site complaints route to CDR only when the complaint explicitly names CDR or a project/worksite signal.
- Immediate public danger still routes first to Civil Defense or ISF according to emergency type.
- `road_class_ownership_index.csv` is a seed ownership/context index. It contains
  local-vs-national guardrails plus named MPWT/CDR/MUN evidence for selected
  road, drainage, snow, and bridge cases already extracted in
  `complaint_intelligence/source_targets.csv`.
- `cdr_project_service_areas.csv` is a seed CDR project/service-area index. It
  includes official CDR GRM/process evidence, the Jounieh road-expansion CDR
  owner signal, and a Dbayeh CDR coordination boundary. It should narrow CDR
  routing only when a complaint names a project, worksite, or listed service
  area.

The shard `source_registry.csv` mirrors the relevant root source IDs from
`data/knowledge_base/source_registry.csv` and adds shard-local `SRC-NNA-*`
article evidence where a named road/project event is used directly in the road
ownership index. Do not merge these IDs with the legacy `SRC-NNN`
complaint-intelligence IDs.

Known gap:
- This folder still does not contain an official classified-road GIS layer or a
  complete national road-segment inventory. If a complaint names a road not in
  the seed index, keep using `boundary_conditions.csv` and HITL for ambiguous
  class/owner decisions.
- This folder still does not contain a complete active CDR project inventory,
  contractor list, or project polygon/road-package geometry. If a complaint says
  only "construction on the road" without a CDR/project clue, keep HITL.
