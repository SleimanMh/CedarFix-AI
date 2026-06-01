# Roads and Public Works Dimension Audit

## Dimensions Covered

- Entity contacts: MUN, MPWT, CDR, CD, ISF.
- Channels: municipality dynamic contacts, MPWT phone/form, CDR phone/form, emergency 125/112.
- Required fields: location, municipality, road class, asset type, danger status, project owner, optional evidence.
- Boundaries: local vs national road, bridge, sidewalk, blocked road, snow/storm, CDR project/worksite owner ambiguity.
- Ownership/context seeds: local-road and national-road guardrails plus named MPWT/CDR/MUN road, bridge, drainage, snow, and project signals in `road_class_ownership_index.csv`.
- CDR project/service seeds: explicit project/worksite guardrail, CDR Roads and Employment GRM, road ESMP timeline evidence, Lake Qaraoun GRM, Jounieh road expansion, and Dbayeh coordination boundary in `cdr_project_service_areas.csv`.
- SLA policy: no invented response times; emergency dispatch separated from repair SLAs.

## Production Decision

The pack is production-usable for conservative routing because it routes only source-backed responsibilities automatically and sends ownership ambiguity to HITL. The ownership and CDR project indexes improve named-road and project grounding, but they are still seed layers and do not replace official classified-road GIS, active CDR project inventory, or project-boundary geometry.
