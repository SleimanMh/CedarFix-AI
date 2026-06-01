# shared — Common utilities and schemas

Purpose
- Shared code used by multiple IEP services and EEP: schemas, metrics, arabizi
  helpers, tokenisation policies, image/text fusion rules, and the civic
  compiler components.

Key modules
- `arabizi_features.py` — arabizi normalization and feature extraction
- `arabizi_lexical_policy.py` — lexical policies and term scoring
- `civic_compiler.py` — proof-carrying incident program utilities
- `image_schemas.py` — image↔text fusion rules used by IEP-6
- `metrics.py` — Prometheus metrics helpers
- `resolution_schemas.py` / `schemas.py` — shared Pydantic models

Notes & gotchas
- Historically `resolution_schemas.tokenize()` was Latin-only; IEP-8 added a
  multilingual tokeniser locally to avoid breaking other services. When
  modifying tokenisation, prefer adding a new multilingual helper here and
  migrating callers incrementally.
