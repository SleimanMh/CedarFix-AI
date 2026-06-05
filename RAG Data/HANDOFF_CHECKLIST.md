# RAG Handoff Checklist (2026-06-05)

Purpose: hand this folder to the teammate who will run DB/Qdrant ingestion.

## What To Transfer

Transfer the entire `monitoring/RAG Data` folder.

If you want a minimal transfer set, include at least:

- `compiled/routing_knowledge_compiled_production.json`
- `municipality/municipality_lookup_compiled_production.json`
- `validation_report.md`

Recommended full routing package:

- `dossiers/entities/`
- `dossiers/advanced/structured_rag_docs.jsonl`
- `logs/` (optional provenance)

## One-File Normalization Applied

The folders were cleaned to one canonical file each:

- `compiled/` -> `routing_knowledge_compiled_production.json`
- `municipality/` -> `municipality_lookup_compiled_production.json`

All other split/manifest variants were moved (not deleted) to:

- `_trash/_archive/kb_cleanup_2026-06-05/rag_onefile_handoff/compiled/`
- `_trash/_archive/kb_cleanup_2026-06-05/rag_onefile_handoff/municipality/`

## Seed Command For Teammate

From repository root:

```powershell
$env:ROUTING_KNOWLEDGE_DOCS = "monitoring/RAG Data/compiled/routing_knowledge_compiled_production.json"
python monitoring/scripts/seed_routing_knowledge.py
```

## Sanity Checks After Seed

PostgreSQL:

```sql
SELECT COUNT(*) AS routing_docs FROM routing_knowledge;
```

Qdrant:

```http
GET /collections/routing_knowledge
```

Expected corpus size in the current handoff:

- Routing documents: 8831
- Municipality lookup records: 1065
- Guarded non-CIB municipality routes: 180
- CIB oversight-only municipality routes: 885
- Validation errors: 0
- Validation warnings: 0

Known source-data caveat resolved: all municipality rows now include Arabic
names.
