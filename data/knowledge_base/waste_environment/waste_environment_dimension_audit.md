# Waste and Environment Dimension Audit

## Dimensions Covered

- Entity contacts: MUN, MOE, CD, ISF, MOIM escalation.
- Channels: municipality dynamic contacts, MOE hotline/email, Civil Defense 125, ISF 112.
- Required fields: location, waste/pollution type, source, danger status, evidence, waterway name, contractor if known.
- Boundaries: routine collection, illegal dumping, hazardous waste, waste fire, industrial pollution, river pollution, quarry/crusher, security threat.
- Operator/context seeds: routine-waste municipality guardrail plus event-backed contractor/multi-actor rows in `waste_operator_coverage.csv`.
- Site/hotspot seeds: public landfill, dump, open-burning, and river-dumping cleanup rows in `waste_site_registry.csv`.
- SLA policy: no invented response times; MOE complaint number/date policy captured separately from remediation timing.

## Production Decision

The pack is production-usable for conservative routing because daily local waste and regulatory/environmental enforcement are separated, and emergency cases remain first-responder routes. The operator and site registries are seed layers; they improve known-case grounding but do not replace current contract verification, permit checks, or site geometry.
