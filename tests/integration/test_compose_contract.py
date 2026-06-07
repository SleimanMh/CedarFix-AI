from __future__ import annotations

from pathlib import Path

import pytest
import yaml


pytestmark = pytest.mark.integration

ROOT = Path(__file__).resolve().parents[2]


def _compose():
    return yaml.safe_load((ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def _published_container_ports(service):
    ports = service.get("ports", [])
    result = set()
    for entry in ports:
        if isinstance(entry, str) and ":" in entry:
            result.add(int(entry.rsplit(":", 1)[1]))
        elif isinstance(entry, int):
            result.add(entry)
    return result


def _run_group_specs(service):
    command = service.get("command", [])
    if not isinstance(command, list) or "/app/docker/run_group.py" not in command:
        return []
    return [item for item in command if isinstance(item, str) and item.count(":") >= 2 and "=" in item]


def test_compose_build_contexts_and_dockerfiles_exist():
    compose = _compose()
    services = compose["services"]

    for name, service in services.items():
        build = service.get("build")
        if not build:
            continue
        context = ROOT / build["context"]
        dockerfile = context / build["dockerfile"]
        assert context.exists(), name
        assert dockerfile.exists(), name


def test_run_group_services_publish_their_declared_ports():
    compose = _compose()

    for name in ("api-service", "ai-service", "vision-service"):
        service = compose["services"][name]
        published = _published_container_ports(service)
        specs = _run_group_specs(service)
        assert specs, name
        for spec in specs:
            port = int(spec.rsplit(":", 1)[1])
            assert port in published, f"{name} command exposes {port} but ports are {sorted(published)}"


def test_core_compose_services_have_expected_dependencies_and_networks():
    compose = _compose()
    services = compose["services"]

    assert services["api-service"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["api-service"]["depends_on"]["qdrant"]["condition"] == "service_started"
    assert services["ai-service"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["ai-service"]["depends_on"]["qdrant"]["condition"] == "service_started"
    assert "api-service" in services["frontend"]["depends_on"]

    for name in ("api-service", "ai-service", "vision-service", "frontend"):
        assert "cedarfix-net" in services[name].get("networks", []), name


def test_compose_service_urls_match_grouped_service_names():
    env = _compose()["services"]["api-service"]["environment"]

    assert env["TEXT_SERVICE_URL"] == "http://ai-service:8001"
    assert env["IMAGE_SERVICE_URL"] == "http://vision-service:8002"
    assert env["EMBEDDING_SERVICE_URL"] == "http://ai-service:8003"
    assert env["CLUSTERING_SERVICE_URL"] == "http://ai-service:8004"
    assert env["ROUTING_SERVICE_URL"] == "http://ai-service:8006"
    assert env["PRIORITY_SERVICE_URL"] == "http://localhost:8005"
    assert env["EXPLANATION_SERVICE_URL"] == "http://localhost:8007"
    assert env["REVIEW_SERVICE_URL"] == "http://localhost:8008"
