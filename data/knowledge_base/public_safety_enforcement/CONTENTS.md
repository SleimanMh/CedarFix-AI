# Public Safety and Enforcement KB Shard

This shard covers emergency routing and local enforcement boundaries for Civil Defense, ISF, municipalities, municipal police, DGLAC, MOIM, and Central Inspection.

Runtime scope:
- Fire, explosion, gas, rescue, and active collapse route first to Civil Defense.
- Crime, threat, weapon, traffic accident, and public-order cases route to ISF, with Civil Defense secondary when rescue or injury is present.
- Building-safety, falling tree/pole, stray animal, illegal construction, local noise, illegal parking, and public-space obstruction cases keep municipality or municipal police as the local resolver unless immediate danger or crime changes the route.
- Corruption, misconduct, and complaint-against-public-administration cases route to Central Inspection with HITL for evidence/privacy review.

The shard uses root source IDs from `data/knowledge_base/source_registry.csv` and does not introduce new scraped source IDs.