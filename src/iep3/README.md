# IEP-3 — Routing Service

Purpose
- Map a structured complaint to the responsible municipal or public entity and
  attach routing metadata (priority, SLA hints, HITL flags).

Key files
- `router.py` — canonical routing logic and KB promotion hooks
- `main.py` / `worker.py` — HTTP entrypoint and worker

Integration notes
- IEP-3 uses the canonical `src/route_complaint.py` logic and layers
  calibration/prioritisation and HITL gating on top. The service promotes KB
  answers for fully vetted sectors while falling back to legacy sector→agency
  maps when coverage is uncertain.

Run & test
- Run locally: `python -m uvicorn src.iep3.main:app --port 8003`
- Unit tests: `python -m pytest scripts/tests/test_iep3_*.py -q`
