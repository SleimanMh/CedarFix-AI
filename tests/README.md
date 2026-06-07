# Unit Test Suite

Run all unit tests from the `gcp-fix` root:

```powershell
python -m pytest -q
```

The grouped runner is also available:

```powershell
python scripts\run_unit_tests.py
```

Integration tests live under `tests/integration` and are opt-in:

```powershell
python scripts\run_integration_tests.py
```

The suite is intentionally isolated from live infrastructure. Qdrant, GCS,
model imports, Postgres sessions, and missing optional settings dependencies
are stubbed or faked in tests so the unit suite stays fast and deterministic.

Install optional test tooling with:

```powershell
pip install -r requirements-test.txt
```

CI installs `requirements-test.txt` and enforces coverage with pytest-cov.
Local runs stay plugin-light so development machines without optional plugins
can still run the deterministic suite.
