# Next Data Acquisition Plan

Generated: 2026-06-02

This document translates the current CedarFix data inventory into the next
data work that will move the product forward. It is written for humans and code
assistants. Do not treat it as runtime truth; it is a prioritized acquisition
and review plan.

## Executive Summary

CedarFix no longer needs more raw municipality-name coverage as the first
priority. The data backbone now covers all 1,107 registry rows through the
municipality registry, aliases, service mappings, water resolver, electricity
resolver, and Civil Defense resolver.

The next bottleneck is operational evidence:

- Which official channel should a citizen use?
- Which fields does that channel require?
- Does the entity issue a ticket or reference number?
- Which union, contractor, ministry, or project owner handles shared services?
- Which cases were accepted, rejected, redirected, or resolved in real life?

Those answers should be collected before expanding generic training data.

## Current Evidence Shape

Strong layers:

- Municipality registry: 1,107 registry rows.
- Municipality aliases: 3,870 alias rows covering all registry rows.
- Water resolver: 1,107 rows across BMLWE, BWE, NLWE, and SLWE.
- Electricity resolver: 1,107 rows across EDL and EDZ.
- Civil Defense resolver: 1,107 rows.
- Entity catalog: 21 canonical entity JSON files plus index entries.
- Water shard: mature source, channel, contact, required-field, boundary, and
  eval coverage.

Weak layers:

- Municipality official channels: 102 rows covering only 11 municipality IDs.
- Municipality complaint workflows: 30 rows covering only 5 municipality IDs.
- Municipal union memberships: 841 row-level rows across all 59 union IDs;
  784 rows have registry IDs and 57 source-specific text rows still need
  manual registry reconciliation.
- Roads/public works, telecom, and waste/environment need deeper operational
  datasets even though their source registries are now populated from root
  source IDs.
- Outcome data exists as a schema, not a live calibration feed.

## Highest-Value Data To Get Next

### 1. Municipality Intake Channels

Target files:

- `knowledge_base/municipalities/municipality_official_channels.csv`
- `knowledge_base/municipalities/municipality_complaint_workflows.csv`
- `knowledge_base/municipalities/source_registry.csv`

Collect:

- official website, email, phone, WhatsApp, contact form, complaint form, app;
- official social page only when municipality-owned or clearly authenticated;
- accepted complaint types;
- required fields;
- ticket/reference behavior;
- retrieved date, source URL, and verification status.

Why this comes first:

The router can resolve municipalities, but citizens need actual intake paths.
This is the difference between "route to municipality" and "submit this issue
through this exact official channel."

### 2. Municipality Unions And Shared Services

Target files:

- `knowledge_base/municipalities/municipal_union_memberships.csv`
- new `knowledge_base/municipalities/municipal_union_service_responsibilities.csv`

Collect:

- registry reconciliation for the remaining text-only membership rows;
- services handled by union rather than individual municipality;
- waste, road, drainage, lighting, and public-space responsibility;
- union contacts and official service announcements;
- contractor/operator names only when publicly official.

Why:

Routine waste, road, drainage, and lighting complaints may be handled through
municipal unions or contracted operators. Without this layer CedarFix can be
technically correct but operationally incomplete.

### 3. Roads And Public Works Ownership

Target files:

- new `knowledge_base/roads_public_works/road_class_ownership_index.csv`
- new `knowledge_base/roads_public_works/cdr_project_service_areas.csv`
- `knowledge_base/roads_public_works/contact_points.csv`
- `knowledge_base/roads_public_works/source_registry.csv`

Collect:

- national/classified road evidence;
- road names or references;
- bridges, tunnels, retaining walls, sidewalks, and drainage ownership;
- MPWT regional or directorate contact coverage;
- CDR project locations, scopes, statuses, and GRM paths.

Why:

Road routing is ownership-sensitive. A pothole on a neighborhood road is not the
same as a bridge collapse, highway defect, or active CDR worksite.

### 4. Waste And Environment Operations

Target files:

- new `knowledge_base/waste_environment/waste_operator_coverage.csv`
- new `knowledge_base/waste_environment/waste_site_registry.csv`
- `knowledge_base/waste_environment/required_fields.csv`
- `knowledge_base/waste_environment/boundary_conditions.csv`

Collect:

- municipality or union waste operators;
- transfer stations, sorting sites, landfills, dump sites, and open-burning
  hotspots when official or reputable sources support them;
- hazardous, medical, chemical, industrial, river, quarry, and crusher process
  boundaries;
- MoE required fields by complaint category.

Why:

Waste routing depends on whether the issue is routine collection, illegal
dumping, fire, hazardous waste, industrial pollution, or regulatory enforcement.

### 5. Telecom Fixed/Mobile Boundaries

Target files:

- `knowledge_base/telecom/required_fields.csv`
- `knowledge_base/telecom/complaint_channels.csv`
- new `knowledge_base/telecom/mobile_operator_channels.csv`

Collect:

- OGERO 1515/app/form fields and reference behavior;
- fixed line, DSL, fiber, cabinet, cable, and exchange-area evidence;
- Alfa and Touch official channels;
- TRA escalation required fields and deadline wording;
- private ISP, home router, device, and satellite-service exclusion cases.

Why:

The most common telecom mistake is routing every internet issue to OGERO or
TRA. CedarFix needs evidence to distinguish fixed infrastructure, mobile
service, private providers, private devices, and public-space hazards.

### 6. Outcome And Human-Override Data

Target files:

- `complaint_intelligence/complaint_resolution_event.schema.json`
- new `complaint_intelligence/routing_override_review_queue.csv`
- `complaint_intelligence/normalized/`

Collect:

- original route;
- accepted/rejected/redirected/resolved status;
- corrected route;
- correction reason;
- missing evidence or missing location;
- response and resolution timestamps when source-backed or user-consented.

Why:

Outcome data is the fastest way to improve routing confidence. Without it, the
system can have complete KB coverage but still lack evidence about which routes
work in practice.

### 7. Targeted Evals And Visual Hazards

Target files:

- sector eval fixtures under `data/eval/`
- new versioned fixtures when behavior changes;
- image-fusion eval successors when adding visual cases.

Collect:

- electricity hard cases: EDZ/EDL/private generator/internal wiring/streetlight;
- telecom hard cases: OGERO/mobile/private router/private ISP/public cable;
- public safety hard cases: CD/ISF/municipal police/roads/environment;
- waste hard cases: routine collection/dumping/hazardous/fire/crime;
- consented or public-source hazard images with license and privacy metadata.

Why:

Water routing already has strong eval coverage. The next evaluation lift should
target weak sectors and boundary cases, not generic easy examples.

## What Not To Collect Yet

Avoid these until governance is clear:

- private WhatsApp groups or closed social groups;
- citizen comments with usernames, faces, exact homes, or phone numbers;
- unverified contact directories;
- bulk scraped social posts without platform-compliant access;
- generic training examples that do not target a failure mode;
- SLA promises unless a source-backed table supports them;
- exact coordinates for private property unless submitted directly with consent.

## Promotion Rules

Use this path for every new fact:

1. Add source evidence or a source target first.
2. Place uncertain findings in a research/backlog file.
3. Promote only official, reputable, or explicitly marked secondary evidence.
4. Add source IDs and confidence fields.
5. Add or update eval cases when routing behavior changes.
6. Keep eval, locked test, and gold OOD rows out of training.

## Two-Week Sprint Recommendation

1. Verify and promote the first 200 municipality contact candidates.
2. Expand municipality workflows from 5 municipalities toward 100.
3. Complete municipal union memberships and create a service-responsibility
   table for shared services.
4. Build the first road-class/project-owner index for MPWT and CDR boundaries.
5. Add waste operator/site queue rows for the highest population municipalities
   and known union/shared-service areas.
6. Capture OGERO, TRA, Alfa, and Touch channel/field details.
7. Start outcome and override logging using the existing resolution-event schema.
8. Add targeted v2 eval cases only for source-backed or stable synthetic
   boundary cases.

## Machine-Readable Queue

The actionable queue is:

```text
complaint_intelligence/next_data_acquisition_queue.csv
```

Use `priority = P0` as the first implementation lane. P1 is important but can
wait until P0 collection has enough verified source rows to change routing or
resolution behavior.
