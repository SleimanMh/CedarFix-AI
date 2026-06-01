# Roads and Public Works Dimension Audit

## Dimensions Covered

- Entity contacts: MUN, MPWT, CDR, CD, ISF.
- Channels: municipality dynamic contacts, MPWT phone/form, CDR phone/form, emergency 125/112.
- Required fields: location, municipality, road class, asset type, danger status, project owner, optional evidence.
- Boundaries: local vs national road, bridge, sidewalk, blocked road, snow/storm, CDR project/worksite owner ambiguity.
- Ownership/context seeds: local-road and national-road guardrails plus named MPWT/CDR/MUN road, bridge, drainage, snow, and project signals in `road_class_ownership_index.csv`.
- SLA policy: no invented response times; emergency dispatch separated from repair SLAs.

## Production Decision

The pack is production-usable for conservative routing because it routes only source-backed responsibilities automatically and sends ownership ambiguity to HITL. The ownership index improves named-road grounding, but it is still a seed layer and does not replace an official classified-road GIS inventory.
