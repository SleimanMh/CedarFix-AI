# CedarFix Routing Backup Test Suite

This folder contains tests only. It intentionally does not change existing
application, data, infrastructure, or script files.

## Test Layers

- `unit/`: deterministic tests for pure routing, scoring, splitting, alignment,
  parsing, and schema behavior. These should not call networks, databases,
  Qdrant, model downloads, or LLM APIs.
- `contract/`: static asset and manifest checks for schemas, RAG data, Docker
  Compose, Kubernetes YAML, and dependency boundaries.
- `integration/`: opt-in live readiness probes for running services, Qdrant,
  and the database. These skip unless the required environment flags are set.

## Run

From `cedarfix-routing-backup`:

```powershell
python -m pytest tests -m "unit or contract" -q
```

With coverage when the project dependencies are installed:

```powershell
python -m pytest tests -m "unit or contract" --cov=services --cov=cedarfix_shared --cov-branch
```

Strict dependency contract:

```powershell
$env:CEDARFIX_STRICT_DEPENDENCY_CONTRACT="true"
python -m pytest tests/contract/test_dependency_imports.py -q
```

Live readiness checks:

```powershell
python -m pytest tests/integration -q -rs
```

See `integration/README.md` for the environment flags that enable live service,
Qdrant, and database probes.

## Known Readiness Gates

- GCP core workload liveness probes are tracked by a strict `xfail` contract in
  `contract/test_infra_manifest_contracts.py`. The test will become a hard
  failure if the manifests add liveness probes and the contract is not promoted.

## Quality Target

- Unit tests stay fast and hermetic.
- External systems are mocked or skipped.
- Integration checks should be added under a separate `integration/` folder and
  marked with `integration`, `qdrant`, `db`, `model`, or `slow`.
- Set `CEDARFIX_STRICT_DEPENDENCY_CONTRACT=true` when you want contract tests to
  require real runtime imports for dependencies that unit tests usually stub.
