# IEP-8 — Grounded Resolution Co-Pilot

Purpose
- Produce a grounded, citation-backed resolution plan for routed complaints.
  Avoids hallucination by retrieving verified KB facts and dropping unsupported
  steps. Emits `EvidenceGap` signals when coverage is missing.

Key files
- `retriever.py` — TF-IDF retriever with Arabic/Arabizi tokenisation
- `knowledge_gaps.py` — gap detection and structured abstention reasons
- `planner.py` — plan synthesis and citation wiring
- `main.py` / `worker.py` — HTTP entrypoint and worker

Run & test
- Run locally: `python -m uvicorn src.iep8.main:app --port 8008`
- Unit tests: `python -m pytest scripts/tests/test_iep8_*.py -q`
- Eval fixture: `data/eval/resolution_grounding_eval_v1.jsonl`

Notes
- The retriever now tokenises Arabic and Arabizi inputs to ensure evidence is
  returned for non-Latin queries. The planner conservatively drops steps that
  cannot be grounded and annotates gaps for KB acquisition.
