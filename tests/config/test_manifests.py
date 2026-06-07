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


def _docs_for(path):
    return [doc for doc in yaml.safe_load_all(path.read_text(encoding="utf-8")) if doc]


def _deployment_container(path, deployment_name, container_name):
    for doc in _docs_for(path):
        if doc.get("kind") != "Deployment" or doc.get("metadata", {}).get("name") != deployment_name:
            continue
        containers = doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", [])
        for container in containers:
            if container.get("name") == container_name:
                return container
    raise AssertionError(f"{path} missing {deployment_name}/{container_name}")


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


def test_kubernetes_configmaps_expose_location_routing_and_splitter_knobs():
    required = {
        "GOOGLE_GEOCODING_URL",
        "MULTI_COMPLAINT_SPLITTER_ENABLED",
        "MULTI_COMPLAINT_SPLITTER_LLM_ENABLED",
        "MULTI_COMPLAINT_SPLITTER_MAX_CHILDREN",
        "MULTI_COMPLAINT_SPLITTER_TIMEOUT",
        "QWEN_ROUTING_TIMEOUT",
        "QWEN_ROUTING_MAX_TOKENS",
    }

    for path in (ROOT / "k8s" / "configmap.yaml", ROOT / "k8s-gcp" / "configmap.yaml"):
        configmap = next(doc for doc in _docs_for(path) if doc.get("kind") == "ConfigMap")
        data = configmap.get("data", {})
        assert required <= set(data), path


def test_kubernetes_services_receive_google_maps_secret_key():
    for base in (ROOT / "k8s", ROOT / "k8s-gcp"):
        for manifest, deployment, container in (
            ("api-service.yaml", "api-service", "api-service"),
            ("ai-service.yaml", "ai-service", "ai-service"),
        ):
            env = _deployment_container(base / manifest, deployment, container).get("env", [])
            names = {entry.get("name") for entry in env}
            assert "GOOGLE_MAPS_API_KEY" in names, base / manifest

        secrets = next(doc for doc in _docs_for(base / "secrets.example.yaml") if doc.get("kind") == "Secret")
        assert "GOOGLE_MAPS_API_KEY" in secrets.get("stringData", {}), base / "secrets.example.yaml"


def test_database_schema_tracks_multi_submission_metadata():
    db_model = (ROOT / "shared" / "cedarfix_shared" / "db.py").read_text(encoding="utf-8")
    gateway_db = (ROOT / "services" / "gateway" / "app" / "database.py").read_text(encoding="utf-8")

    for field in ("parent_submission_id", "split_index", "split_total"):
        assert field in db_model
        assert f"ADD COLUMN IF NOT EXISTS {field}" in gateway_db
