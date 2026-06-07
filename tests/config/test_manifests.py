from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def _yaml_docs():
    for base in (ROOT / "k8s", ROOT / "k8s-gcp"):
        for path in base.glob("*.yaml"):
            for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")):
                if doc:
                    yield path, doc


def test_all_kubernetes_yaml_documents_parse_and_have_identity():
    docs = list(_yaml_docs())
    assert docs
    for path, doc in docs:
        assert doc.get("apiVersion"), path
        assert doc.get("kind"), path
        if doc.get("kind") != "Kustomization":
            assert doc.get("metadata", {}).get("name"), path


def test_workload_manifests_have_container_images():
    workload_kinds = {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}
    workloads = [(path, doc) for path, doc in _yaml_docs() if doc.get("kind") in workload_kinds]
    assert workloads
    for path, doc in workloads:
        template = doc.get("spec", {}).get("template", {})
        containers = template.get("spec", {}).get("containers", [])
        assert containers, path
        for container in containers:
            assert container.get("name"), path
            assert container.get("image"), path


def test_service_manifests_expose_named_ports():
    services = [(path, doc) for path, doc in _yaml_docs() if doc.get("kind") == "Service"]
    assert services
    for path, doc in services:
        ports = doc.get("spec", {}).get("ports", [])
        assert ports, path
        for port in ports:
            assert port.get("port"), path
            assert port.get("targetPort") is not None, path


def test_python_dockerfiles_copy_shared_services_and_define_cmd():
    for name in ("api.Dockerfile", "ai.Dockerfile", "vision.Dockerfile"):
        text = (ROOT / "docker" / name).read_text(encoding="utf-8")
        assert "COPY shared /app/shared" in text
        assert "COPY services /app/services" in text
        assert "CMD [" in text


def test_fastapi_services_use_lifespan_instead_of_deprecated_on_event():
    service_mains = sorted((ROOT / "services").glob("*/app/main.py"))
    assert service_mains
    for path in service_mains:
        text = path.read_text(encoding="utf-8")
        assert ".on_event(" not in text, path
