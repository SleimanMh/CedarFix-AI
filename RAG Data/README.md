# RAG Data

This folder is the production routing RAG corpus for CedarFix. It must contain
RAG-ready data only: curated entity dossiers, normalized structured retrieval
documents, compiled JSONL, a manifest, and validation output. It is intentionally
not a raw mirror of the project `data/` folder.

## Folder Contract

- `dossiers/entities/` contains curated entity responsibility dossiers imported
  from the original RAG data branch.
- `dossiers/advanced/structured_rag_docs.jsonl` contains normalized RAG-ready
  documents generated from useful structured CedarFix data and the uploaded v74
  municipality gap-resolution handoff.
- `compiled/routing_knowledge_docs.jsonl` is the complete embedding/seed input.
- `compiled/routing_knowledge_manifest.json` records corpus counts, source
  profiles, document types, route modes, and routing entities.
- `validation_report.md` is produced by the validator and must pass before the
  corpus is seeded.

Raw CSV, SQLite, evaluation sets, municipality registries, and uploaded zip
contents should stay outside this folder. The compiler reads those sources in
place and writes only normalized RAG documents here.

## What Is Included

The compiled corpus currently combines:

- Entity responsibilities and boundary/HITL guardrails for 21 CedarFix routing
  entities.
- Complaint taxonomy, routing rules, remediation workflows, SLA policies, and
  responsibility boundaries.
- Municipality service maps for water, electricity, fixed telecom, local roads,
  national roads, unions, complaint workflows, and official channels.
- Domain-specific public works, telecom, electricity, water, waste/environment,
  irrigation, mobile-operator, and trusted-context documents.
- Uploaded v74 municipality contact-gap material as audit/support documents only.

The v74 handoff is deliberately conservative:

- Contact fallback rows are `contact_fallback_only`.
- No v74 row grants auto-route permission.
- Sir Ed Danniye is retained as a Human Review staging candidate only.
- Municipalities with no usable endpoint are blocker/user-assist documents.

## Route Modes

Route modes are used by the router and prompt to prevent weak records from
becoming fake authority.

- `routing_candidate`, `routing_rule`, and `geo_service_route` can support
  production routing when confidence and location match.
- `contact_fallback_only`, `audit_context`, `contact_context`,
  `query_and_type_expansion`, `resolution_context`, `resolution_policy`,
  `supporting_context`, and `manual_review_only` are support-only.
- Documents with `hitl_always_required=true` must not auto-route.

## Regeneration

Run from the repository root:

```powershell
python scripts\compile_routing_knowledge.py
python scripts\validate_routing_knowledge.py
```

Then seed PostgreSQL and Qdrant:

```powershell
python scripts\seed_routing_knowledge.py
```

The seed script reads `compiled/routing_knowledge_docs.jsonl` by default. Use
`ROUTING_KNOWLEDGE_DOCS` only when testing an alternate compiled corpus.

## Current Validation

The current corpus validates with:

- Documents: 8,084
- Entities: 21
- Errors: 0
- Warnings: 0

