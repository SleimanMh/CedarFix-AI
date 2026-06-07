# Integration Tests

Place compose-contract and live-service tests here and mark them with
`@pytest.mark.integration`.

Static contract tests in this folder do not start containers; they verify
deployment wiring. Live tests may use Docker Compose, Postgres, Qdrant, GCS, or
model-serving endpoints.

Run them explicitly from the `gcp-fix` root:

```powershell
python scripts\run_integration_tests.py
```

Recommended first integration checks:

- Gateway `/complaints` happy path against mocked or local service containers.
- Qdrant store/search round trip for text and CLIP collections.
- Postgres retraining-store write/read/export workflow.
- GCS/local storage parity for image references.
- Routing RAG retrieval against seeded `routing_knowledge`.
