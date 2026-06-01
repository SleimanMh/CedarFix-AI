# Roads and Public Works Dossier

## Routing Summary

- Local roads, sidewalks, alleys, and ordinary neighborhood potholes route to the resolved municipality.
- Classified roads, highways, autostrades, national-route signals, and bridges route to MPWT with HITL when class evidence is not enough.
- CDR is not a daily maintenance resolver; it is used only for explicit CDR, reconstruction, or active public-project/worksite complaints.
- Civil Defense and ISF remain emergency/security entities. Collapse, fire, rescue, accident, and public-order danger should not wait for asset ownership review.

## Evidence Position

The shard uses existing official and reputable source IDs already registered in the root source registry: MPWT roads/buildings and contact pages, CDR home/contact pages, Civil Defense 125, ISF mission/service context, and municipal governance sources.

`road_class_ownership_index.csv` adds a first seed layer for road ownership and context. It has:

- default guardrails for local/neighborhood roads versus classified/national/highway roads;
- named MPWT evidence for Jbeil-Nahr Ibrahim coastal highway paving, Bazouriyeh-Borj El Chemali main-road restoration, Qammoua snow opening, Sin el Fil drainage response, Jounieh flood-mitigation works, Dbayeh flood-preparedness, and an Akkar bridge repair;
- a CDR/project-owner signal for the Jounieh road expansion project;
- a Beirut Al-Rihab boundary case where Beirut Municipality stays primary even though MPWT helped clear flooding;
- a Dahr al-Baidar main-road rehabilitation context row that remains MPWT/CDR HITL because owner and project scope are not fully proven.

`cdr_project_service_areas.csv` adds the first CDR-specific project/service-area seed. It has:

- an explicit CDR worksite guardrail;
- CDR Roads and Employment Project GRM evidence for project-specific road worksites;
- road ESMP/T807 complaint timeline evidence for CDR road-project GRM handling;
- Lake Qaraoun Pollution Prevention Project GRM evidence for CDR water/environment project complaints;
- the Jounieh road expansion CDR owner/admin-pipeline signal;
- the Dbayeh flood-preparedness row as a CDR coordination boundary, not a CDR primary-owner proof.

## Known Limits

- No verified national GIS layer of classified roads is encoded; the seed index is not a geometry layer.
- No generic public SLA for road repair or snow clearance is encoded.
- CDR project boundaries are only seeded; no complete active project inventory, contractor list, road-package geometry, or project polygon layer is encoded.
- Drainage cases can involve MPWT, municipality, CDR, sewer actors, and contractors; keep HITL when the asset owner is not named.
