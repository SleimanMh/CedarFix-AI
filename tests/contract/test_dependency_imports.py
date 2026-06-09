from __future__ import annotations

import importlib.machinery
import os
from pathlib import Path

import pytest


pytestmark = pytest.mark.contract


REAL_IMPORTS_REQUIRED_FOR_THE_TEST_LAYER = {
    "fastapi": "fastapi",
    "httpx": "httpx",
    "pydantic": "pydantic",
    "pytest": "pytest",
    "yaml": "PyYAML",
}

STRICT_RUNTIME_IMPORTS = {
    "langdetect": "langdetect",
    "openai": "openai",
    "pydantic_settings": "pydantic-settings",
    "qdrant_client": "qdrant-client",
    "sqlalchemy": "SQLAlchemy",
}

STUBBED_RUNTIME_IMPORTS = {
    "langdetect": "langdetect",
    "openai": "openai",
    "pydantic_settings": "pydantic-settings",
    "qdrant_client": "qdrant-client",
    "sqlalchemy": "SQLAlchemy",
    "torch": "torch",
    "transformers": "transformers",
}


def _real_spec(module_name: str):
    return importlib.machinery.PathFinder.find_spec(module_name)


def _declared_test_requirements(requirements_path: Path) -> set[str]:
    requirements: set[str] = set()
    for raw_line in requirements_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        name = line.split(";", 1)[0]
        for separator in ("==", ">=", "<=", "~=", "!=", ">", "<"):
            name = name.split(separator, 1)[0]
        requirements.add(name.strip().casefold())
    return requirements


@pytest.mark.parametrize(
    ("module_name", "distribution_name"),
    sorted(REAL_IMPORTS_REQUIRED_FOR_THE_TEST_LAYER.items()),
)
def test_core_test_dependencies_resolve_to_real_installed_modules(module_name, distribution_name):
    assert _real_spec(module_name) is not None, (
        f"{module_name!r} is required by the test layer but no real import spec was found. "
        f"Install {distribution_name!r} instead of relying on a stub."
    )


def test_stubbed_runtime_dependencies_are_explicitly_declared_or_intentionally_optional(repo_root):
    declared = _declared_test_requirements(repo_root / "tests" / "requirements.txt")
    intentionally_optional = {"qdrant-client", "torch", "transformers"}
    undocumented: list[str] = []

    for module_name, distribution_name in STUBBED_RUNTIME_IMPORTS.items():
        if _real_spec(module_name) is not None:
            continue
        normalized = distribution_name.casefold()
        if normalized not in declared and normalized not in intentionally_optional:
            undocumented.append(f"{module_name} ({distribution_name})")

    assert undocumented == [], (
        "Missing runtime dependencies are being covered by tests/conftest.py stubs without "
        f"a declaration in tests/requirements.txt or the intentional optional list: {undocumented}"
    )


@pytest.mark.parametrize(
    ("module_name", "distribution_name"),
    sorted(STRICT_RUNTIME_IMPORTS.items()),
)
def test_runtime_dependencies_have_real_imports_when_strict_contract_enabled(module_name, distribution_name):
    if os.getenv("CEDARFIX_STRICT_DEPENDENCY_CONTRACT", "false").lower() != "true":
        pytest.skip("Set CEDARFIX_STRICT_DEPENDENCY_CONTRACT=true to enforce real runtime imports.")

    assert _real_spec(module_name) is not None, (
        f"{module_name!r} should resolve to a real installed package under the strict dependency contract. "
        f"Install {distribution_name!r}."
    )
