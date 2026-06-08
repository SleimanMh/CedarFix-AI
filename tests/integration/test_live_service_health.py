from __future__ import annotations

import json
import os
from typing import Iterable

import httpx
import pytest


pytestmark = pytest.mark.integration


DEFAULT_LOCAL_HEALTH_TARGETS = {
    "gateway": "http://127.0.0.1:8000/health",
    "text": "http://127.0.0.1:8001/health",
    "image": "http://127.0.0.1:8002/health",
    "embedding": "http://127.0.0.1:8003/health",
    "clustering": "http://127.0.0.1:8004/health",
    "priority": "http://127.0.0.1:8005/health",
    "routing": "http://127.0.0.1:8006/health",
    "explanation": "http://127.0.0.1:8007/health",
    "review": "http://127.0.0.1:8008/health",
}


def _truthy_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _target_items(raw: str) -> Iterable[tuple[str, str]]:
    raw = raw.strip()
    if not raw:
        return []

    if raw.startswith("{") or raw.startswith("["):
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return [(str(name), str(url)) for name, url in parsed.items()]
        if isinstance(parsed, list):
            return [(f"service-{index + 1}", str(url)) for index, url in enumerate(parsed)]
        raise AssertionError("CEDARFIX_LIVE_HEALTH_URLS JSON must be an object or list")

    targets: list[tuple[str, str]] = []
    for index, item in enumerate(part.strip() for part in raw.split(",") if part.strip()):
        if "=" in item:
            name, url = item.split("=", 1)
            targets.append((name.strip(), url.strip()))
        else:
            targets.append((f"service-{index + 1}", item))
    return targets


def _health_targets() -> dict[str, str]:
    raw_targets = os.getenv("CEDARFIX_LIVE_HEALTH_URLS", "")
    targets = dict(_target_items(raw_targets))
    if targets:
        return targets

    if _truthy_env("CEDARFIX_RUN_LOCAL_HEALTH_CHECKS"):
        return DEFAULT_LOCAL_HEALTH_TARGETS

    pytest.skip(
        "Set CEDARFIX_LIVE_HEALTH_URLS or CEDARFIX_RUN_LOCAL_HEALTH_CHECKS=true "
        "to probe live service /health endpoints."
    )


def test_live_services_expose_healthy_status_payloads():
    failures: list[str] = []

    with httpx.Client(timeout=5.0) as client:
        for name, url in _health_targets().items():
            try:
                response = client.get(url)
            except Exception as exc:
                failures.append(f"{name}: request to {url} failed with {type(exc).__name__}: {exc}")
                continue

            if response.status_code != 200:
                failures.append(f"{name}: expected HTTP 200 from {url}, got {response.status_code}")
                continue

            try:
                payload = response.json()
            except ValueError:
                failures.append(f"{name}: /health did not return JSON: {response.text[:120]!r}")
                continue

            if payload.get("status") != "ok":
                failures.append(f"{name}: expected status='ok', got {payload!r}")
            if not payload.get("service"):
                failures.append(f"{name}: expected non-empty service name, got {payload!r}")

    assert failures == []
