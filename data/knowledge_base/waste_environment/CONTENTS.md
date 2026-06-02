# Waste and Environment KB Shard

This shard covers routing for municipal solid-waste complaints, illegal dumping, hazardous/medical/chemical waste, landfill/dump fires, industrial pollution, river pollution, air/smoke complaints, and quarry/crusher complaints.

Runtime scope:
- Routine collection, overflowing bins, and street sweeping route to the resolved municipality.
- Hazardous, medical, chemical, industrial, river, quarry, and crusher cases route to MOE with HITL and municipal context where useful.
- Landfill/dump/trash fires and immediate danger route first to Civil Defense.
- Criminal/security context routes to ISF through the safety layer.
- `waste_operator_coverage.csv` is a seed operator/context layer. It contains
  municipality-first guardrails plus event-backed contractor or multi-actor
  signals for Tripoli/Lavajet, Saida/IBC, Beirut-Metn/Jdeideh, and
  Dbayeh/Ramco-City Blue.
- `waste_site_registry.csv` is a seed public-site layer. It contains
  source-backed landfill, dump, open-burning, and river-dumping cleanup cases
  where the local evidence names a public site or generalized public asset.

The shard `source_registry.csv` mirrors the relevant root source IDs from
`data/knowledge_base/source_registry.csv` and adds shard-local event sources for
operator and site seeds. It avoids invented service-level agreements.

Known gap:
- This folder still does not contain a complete national waste contract map,
  operator coverage table, landfill permit registry, or exact site geometry.
  Treat the seed rows as routing evidence and ask HITL when a complaint depends
  on current contract status, operator exclusivity, or exact site boundaries.
