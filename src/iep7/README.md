# IEP-7 — Calibration & Drift Monitor

Purpose
- Track per-sector calibration (ECE / Brier) and surface drift alerts for model
  performance degradation. Emits Prometheus gauges for operational dashboards.

Key files
- `calibration.py` — calibration snapshots and metrics
- `main.py` / `worker.py` — HTTP entrypoint and worker

Run & test
- Run locally: `python -m uvicorn src.iep7.main:app --port 8007`
- Unit tests: `python -m pytest scripts/tests/test_iep7_*.py -q`
