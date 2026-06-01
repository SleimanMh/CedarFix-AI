# IEP-2 — Deduplication & Fusion Service

Purpose
- Detect near-duplicate complaints and fuse overlapping reports into a single
  canonical incident. Helps avoid duplicate routing and concentrates HITL effort.

Key files
- `dedup.py` — deduplication heuristics and hash-based similarity
- `fusion_model.py` — complaint fusion logic (merge heuristics, timestamp rules)
- `main.py` / `worker.py` — HTTP entrypoint and worker

Inputs / Outputs
- Input: sets of complaint records or a single complaint (worker pulls from queue)
- Output: fused incident object and a canonical complaint id mapping

Run & test
- Run locally: `python -m uvicorn src.iep2.main:app --port 8002`
- Unit tests: `python -m pytest scripts/tests/test_iep2_*.py -q`

Notes
- Fusion decisions aim for high precision (avoid incorrectly merging distinct
  incidents). When in doubt, the service prefers conservative non-merge and
  surfaces duplicates for human review.
