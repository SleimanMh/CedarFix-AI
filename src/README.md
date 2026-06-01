# src — Code Layout & Quickstart

This folder contains the runtime microservices that process incoming citizen
complaints: the External Event Pipeline (EEP) intake, and the IEP worker
services (IEP-1 .. IEP-8). Each service lives in its own package with a
`main.py` HTTP entrypoint and a `worker.py` async worker.

Quick run (per-service):

1. Activate virtualenv: `.\.venv\Scripts\Activate.ps1`
2. Install deps: `pip install -r requirements.txt`
3. Run a service locally (example):
   - `python -m uvicorn src.eep.main:app --port 8000`
   - `python -m uvicorn src.iep1.main:app --port 8001`

Health endpoints are available under `/health`; metrics are exposed on
`/metrics` for Prometheus scraping.

Where to look:
- `src/eep/` — intake, validation, feedback endpoints, retraining candidates
- `src/iep1/` .. `src/iep8/` — individual IEP services (see their READMEs)
- `src/shared/` — common schemas, metrics, arabizi helpers, fusion rules

If you are iterating on a single IEP, open its `README.md` (for example
`src/iep1/README.md`) to see run/test instructions and evaluation fixtures.
