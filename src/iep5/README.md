# IEP-5 — Incident Lifecycle

Purpose
- Maintain the incident timeline, lifecycle events (open, acknowledge, resolve,
  reopen) and surface retraining signals when incidents are re-opened or
  corrected by human reviewers.

Key files
- `lifecycle.py` — event sourcing utilities and lifecycle transitions
- `risk.py` — risk scoring and priority adjustments
- `main.py` / `worker.py` — HTTP entrypoint and worker

Run & test
- Run locally: `python -m uvicorn src.iep5.main:app --port 8005`
- Unit tests: `python -m pytest scripts/tests/test_iep5_*.py -q`

Notes
- Reopen events currently enqueue `RetrainingCandidate` entries in EEP; a
  downstream retraining consumer is recommended to convert those rows into
  training examples for scheduled model retraining.
