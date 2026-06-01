# IEP-4 — Explainer Service

Purpose
- Generate citizen-facing explanations and human-readable HITL narratives for
  routing decisions and resolution plans. Useful for transparency and audit.

Key files
- `explainer.py` — explanation generation logic
- `main.py` / `worker.py` — HTTP entrypoint and worker
- `prompts/` — any prompt templates used for explanation generation

Run & test
- Run locally: `python -m uvicorn src.iep4.main:app --port 8004`
- Unit tests: `python -m pytest scripts/tests/test_iep4_*.py -q`
