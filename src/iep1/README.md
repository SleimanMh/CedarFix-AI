# IEP-1 — Multilingual Sector & Issue Classifier

Purpose
- Convert free-text complaint submissions into structured sector/issue labels
  suitable for routing and downstream resolution. Specialised for Lebanese
  Arabic/Arabizi mixed text but supports English/French fallbacks.

Key files
- `semantic_classifier.py` — main classification cascade (arabizi normaliser,
  Arabic keyword scoring, optional embedding cascade)
- `extractor.py` — text extraction and pre-processing helpers
- `main.py` / `worker.py` — HTTP entrypoint and async worker

Environment toggles
- `CEDARFIX_IEP1_USE_MULTILINGUAL=1` — enable the embedding-based cascade
  (requires downloading the multilingual sentence-transformers model).

Inputs / Outputs
- Input: complaint text (and optional metadata/attachments).
- Output: structured classification with `sector`, `issue_type`, `confidence`,
  and `evidence_terms` (see `semantic_classifier.py` for the exact dict).

Run & test
- Run locally: `python -m uvicorn src.iep1.main:app --port 8001`
- Unit tests: `python -m pytest scripts/tests/test_iep1_*.py -q`
- Eval fixture: `data/eval/arabic_multilingual_routing_eval_v1.jsonl`

Known limitations
- Embedding cascade improves multilingual recall but increases model size and
  cold-start latency (download the HF model to avoid repeated downloads).
- Char-gram fallback still underperforms on purely Arabic-script inputs
  without arabizi normalization; prefer enabling the multilingual mode.
