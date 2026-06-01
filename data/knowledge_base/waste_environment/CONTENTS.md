# Waste and Environment KB Shard

This shard covers routing for municipal solid-waste complaints, illegal dumping, hazardous/medical/chemical waste, landfill/dump fires, industrial pollution, river pollution, air/smoke complaints, and quarry/crusher complaints.

Runtime scope:
- Routine collection, overflowing bins, and street sweeping route to the resolved municipality.
- Hazardous, medical, chemical, industrial, river, quarry, and crusher cases route to MOE with HITL and municipal context where useful.
- Landfill/dump/trash fires and immediate danger route first to Civil Defense.
- Criminal/security context routes to ISF through the safety layer.

The shard `source_registry.csv` now mirrors the relevant root source IDs from
`data/knowledge_base/source_registry.csv` so local assistants can resolve
evidence without leaving the folder. It avoids invented service-level
agreements.
