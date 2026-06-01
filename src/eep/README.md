# EEP — External Event Pipeline

Purpose
- HTTP intake service that validates incoming complaint payloads, scrubs PII,
  persists the canonical complaint, and enqueues work (Redis / Postgres fallback).

Key files
- `main.py` — FastAPI app and endpoints
- `db.py` — SQLAlchemy/aiosqlite persistence models (includes `RetrainingCandidate`)
- `models.py` — Pydantic API schemas (Complaint, ComplaintState, ComplaintFeedback)
- `queue.py` — enqueue/dequeue helpers and Redis stream interactions

Recent additions
- `POST /complaints/{complaint_id}/feedback` — ingest human feedback and create
  retraining candidates.
- `GET /retraining-queue` — list pending retraining candidates.

How it integrates
- Receives the raw submission, normalises text and attachments, then publishes
  to the IEP worker queue(s). Feedback collected here seeds the retraining queue
  consumed by offline model training jobs.

Run & test
- Run locally: `python -m uvicorn src.eep.main:app --port 8000`
- Unit tests: `python -m pytest scripts/tests/test_eep_*.py -q`

Notes
- `RetrainingCandidate` rows are stored in the database; consumer/ingest
  automation that turns candidates into training examples is a recommended next
  step (not included in round-2 hardening).
