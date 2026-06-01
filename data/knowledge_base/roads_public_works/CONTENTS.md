# Roads and Public Works KB Shard

This shard covers routing boundaries for Lebanese local roads, classified/national roads, bridges, sidewalks, blocked roads, snow/storm road incidents, active public-works sites, and CDR project-owner ambiguity.

Runtime scope:
- Local roads, sidewalks, and ordinary potholes route to the resolved municipality.
- Classified/national roads, highways, and bridges route to MPWT with HITL when road class is not independently verified.
- Active CDR/project-site complaints route to CDR only when the complaint explicitly names CDR or a project/worksite signal.
- Immediate public danger still routes first to Civil Defense or ISF according to emergency type.

The shard `source_registry.csv` now mirrors the relevant root source IDs from
`data/knowledge_base/source_registry.csv` so local assistants can resolve
evidence without leaving the folder. It does not introduce new scraped source
IDs.
