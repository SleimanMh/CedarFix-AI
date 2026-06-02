# Waste and Environment Dossier

## Routing Summary

- Routine household waste collection, overflowing bins, and street sweeping route to the resolved municipality.
- Illegal dumping starts as municipal when no hazardous or industrial signal exists; MOE becomes primary when environmental enforcement or hazardous material is indicated.
- Hazardous, medical, chemical, industrial, river, quarry, and crusher complaints route to MOE with HITL for evidence, source, and exact location.
- Active fire or immediate danger routes first to Civil Defense. Crime, threats, or public-order danger routes through ISF.

## Evidence Position

The shard uses registered source IDs for MOE mandate/contact/complaint process, municipal waste-governance references, Civil Defense 125, ISF mission/FAQ evidence, and MOIM municipal escalation context.

`waste_operator_coverage.csv` adds a first seed layer for operator and shared-responsibility context. It has:

- a municipality-first routine-waste guardrail;
- Tripoli/Lavajet event-backed cleanup, sewer, container-disinfection, and Abu Ali River cleanup context;
- Saida/IBC accumulated-waste treatment context;
- a Saida/Deir Zahrani unnamed-collection-contractor disruption boundary;
- Beirut/Metn/Jdeideh landfill-access and contractor/CDR/MOE boundary evidence;
- Dbayeh/Ramco-City Blue coordination evidence tied to flood-preparedness and waste-contractor compliance.

`waste_site_registry.csv` adds a first seed layer for public waste sites and hotspots. It has:

- Jdeideh landfill access boundary evidence;
- Saida, Bchannine, and Burj al-Shamali landfill fire/escalation rows;
- Erzi and Deir Ammar waste-dump fire/open-burning rows;
- Abu Ali River dumping cleanup as a river-corridor boundary case.

## Known Limits

- Municipal contractor and union coverage is only seeded from event-backed evidence; it is not globally encoded.
- Waste-site data is a seed registry, not a permit registry or geometry layer.
- No generic collection, cleanup, inspection, or remediation SLA is encoded.
- Hazardous waste subcategory workflows require further source collection.
