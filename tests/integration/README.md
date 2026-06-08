# Integration Readiness Tests

These tests are safe by default and skip unless you explicitly point them at
running local or deployed services.

```powershell
# Health-check every default local service port.
$env:CEDARFIX_RUN_LOCAL_HEALTH_CHECKS="true"
python -m pytest tests/integration/test_live_service_health.py -q -rs

# Or provide a custom comma-separated list.
$env:CEDARFIX_LIVE_HEALTH_URLS="gateway=http://127.0.0.1:8000/health,routing=http://127.0.0.1:8006/health"
python -m pytest tests/integration/test_live_service_health.py -q -rs

# Qdrant readiness.
$env:CEDARFIX_RUN_QDRANT_TESTS="true"
$env:CEDARFIX_QDRANT_URL="http://127.0.0.1:6333"
python -m pytest tests/integration/test_live_qdrant_readiness.py -q -rs

# Database readiness.
$env:CEDARFIX_RUN_DB_TESTS="true"
$env:CEDARFIX_DATABASE_URL="postgresql://cedarfix:cedarfix_secret@127.0.0.1:5432/cedarfix"
python -m pytest tests/integration/test_live_database_readiness.py -q -rs
```
