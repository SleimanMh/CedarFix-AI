# IEP-6 — Multimodal Vision & Image Hazard Fusion

Purpose
- Inspect attached photos and fuse image signals with text to detect hazards
  (safety, flooding, damaged infrastructure) and improve routing confidence.

Key files
- `vision.py` — CLIP-based image/text scoring and heuristics
- `image_schemas.py` (in `src/shared`) — fusion rules and agree/conflict logic
- `main.py` / `worker.py` — HTTP entrypoint and worker

Run & test
- Run locally: `python -m uvicorn src.iep6.main:app --port 8006`
- Unit tests: `python -m pytest scripts/tests/test_iep6_*.py -q`
- Eval fixture: `data/eval/image_hazard_fusion_eval_v1.jsonl`

Notes
- Fusion returns `agree` / `conflict` / `no_image_signal` and the `fuse_image_text()`
  rules are implemented in `src/shared/image_schemas.py`. Tests were expanded
  during the hardening round to increase coverage (15→45 cases).
