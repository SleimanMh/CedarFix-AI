from __future__ import annotations

import os

import httpx
import pytest


pytestmark = [pytest.mark.integration, pytest.mark.qdrant]


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def test_live_qdrant_health_and_collections_are_reachable():
    if not _truthy_env("CEDARFIX_RUN_QDRANT_TESTS"):
        pytest.skip("Set CEDARFIX_RUN_QDRANT_TESTS=true to probe a live Qdrant instance.")

    base_url = os.getenv("CEDARFIX_QDRANT_URL", "http://127.0.0.1:6333").rstrip("/")

    with httpx.Client(timeout=5.0) as client:
        health = client.get(f"{base_url}/healthz")
        assert health.status_code == 200, health.text[:200]

        collections = client.get(f"{base_url}/collections")
        assert collections.status_code == 200, collections.text[:200]
        payload = collections.json()

    assert "result" in payload
    assert "collections" in payload["result"]
    assert isinstance(payload["result"]["collections"], list)
