from __future__ import annotations

from pathlib import Path
import json

import pytest

from conftest import import_or_skip


pytestmark = pytest.mark.contract


def _yaml():
    return import_or_skip("yaml")


def _load_yaml_documents(path: Path) -> list[dict]:
    yaml = _yaml()
    text = path.read_text(encoding="utf-8")
    return [doc for doc in yaml.safe_load_all(text) if isinstance(doc, dict)]


def _manifest_documents(repo_root: Path, folder_name: str) -> list[tuple[Path, dict]]:
    folder = repo_root / folder_name
    docs: list[tuple[Path, dict]] = []
    for path in sorted(folder.glob("*.y*ml")):
        if path.name.endswith(".example.yaml"):
            continue
        for doc in _load_yaml_documents(path):
            if doc.get("apiVersion") or doc.get("kind"):
                docs.append((path, doc))
    return docs


def _all_yaml_documents(repo_root: Path, folder_name: str) -> list[tuple[Path, dict]]:
    folder = repo_root / folder_name
    docs: list[tuple[Path, dict]] = []
    for path in sorted(folder.glob("*.y*ml")):
        for doc in _load_yaml_documents(path):
            docs.append((path, doc))
    return docs


def _workload_container_specs(docs: list[tuple[Path, dict]]) -> list[tuple[Path, dict, dict]]:
    specs: list[tuple[Path, dict, dict]] = []
    for path, doc in docs:
        if doc.get("kind") in {"Deployment", "StatefulSet", "DaemonSet"}:
            for container in doc.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
                specs.append((path, doc, container))
    return specs


@pytest.mark.parametrize("folder_name", ["k8s", "k8s-gcp"])
def test_kubernetes_manifests_are_parseable_and_named(repo_root, folder_name):
    docs = _manifest_documents(repo_root, folder_name)

    assert docs
    for path, doc in docs:
        assert doc.get("apiVersion"), path
        assert doc.get("kind"), path
        if doc.get("kind") != "Kustomization":
            assert doc.get("metadata", {}).get("name"), path


@pytest.mark.parametrize("folder_name", ["k8s", "k8s-gcp"])
def test_kubernetes_service_selectors_match_workload_labels(repo_root, folder_name):
    docs = _manifest_documents(repo_root, folder_name)
    workloads: list[dict] = []
    services: list[tuple[Path, dict]] = []

    for path, doc in docs:
        kind = doc.get("kind")
        if kind in {"Deployment", "StatefulSet", "DaemonSet"}:
            labels = doc.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {})
            workloads.append(labels)
        if kind == "Service" and doc.get("spec", {}).get("selector"):
            services.append((path, doc))

    for path, service in services:
        selector = service["spec"]["selector"]
        assert any(
            all(labels.get(key) == value for key, value in selector.items())
            for labels in workloads
        ), f"{folder_name}/{path.name} selector does not match any workload labels: {selector}"


@pytest.mark.parametrize("folder_name", ["k8s", "k8s-gcp"])
def test_kustomization_resources_exist(repo_root, folder_name):
    kustomization = repo_root / folder_name / "kustomization.yaml"
    assert kustomization.exists()

    doc = _load_yaml_documents(kustomization)[0]
    missing = [
        resource
        for resource in doc.get("resources", [])
        if not (kustomization.parent / resource).exists()
    ]

    assert missing == []


def test_docker_compose_services_reference_existing_dependencies(repo_root):
    compose_path = repo_root / "docker-compose.yml"
    docs = _load_yaml_documents(compose_path)
    compose = docs[0]
    services = compose.get("services", {})
    service_names = set(services)

    assert {"postgres", "qdrant", "api-service", "ai-service", "frontend"} <= service_names

    missing_dependencies: dict[str, list[str]] = {}
    for name, spec in services.items():
        depends_on = spec.get("depends_on", {})
        if isinstance(depends_on, dict):
            dependencies = set(depends_on)
        elif isinstance(depends_on, list):
            dependencies = set(depends_on)
        else:
            dependencies = set()
        missing = sorted(dependencies - service_names)
        if missing:
            missing_dependencies[name] = missing

    assert missing_dependencies == {}


def test_gcp_env_configmap_and_secret_refs_are_declared(repo_root):
    docs = _all_yaml_documents(repo_root, "k8s-gcp")
    configmaps = {
        doc.get("metadata", {}).get("name"): set((doc.get("data") or {}).keys())
        for _, doc in docs
        if doc.get("kind") == "ConfigMap"
    }
    secrets = {
        doc.get("metadata", {}).get("name"): set((doc.get("data") or {}).keys()) | set((doc.get("stringData") or {}).keys())
        for _, doc in docs
        if doc.get("kind") == "Secret"
    }
    missing: list[str] = []

    for path, workload, container in _workload_container_specs(_manifest_documents(repo_root, "k8s-gcp")):
        for env_from in container.get("envFrom", []) or []:
            ref_name = (env_from.get("configMapRef") or {}).get("name")
            if ref_name and ref_name not in configmaps:
                missing.append(f"{path.name}/{workload['metadata']['name']}/{container['name']}: configMapRef {ref_name}")

        for env in container.get("env", []) or []:
            value_from = env.get("valueFrom") or {}
            config_ref = value_from.get("configMapKeyRef")
            secret_ref = value_from.get("secretKeyRef")
            if config_ref:
                name = config_ref.get("name")
                key = config_ref.get("key")
                if name not in configmaps or key not in configmaps.get(name, set()):
                    missing.append(f"{path.name}/{container['name']}: configMapKeyRef {name}.{key}")
            if secret_ref:
                name = secret_ref.get("name")
                key = secret_ref.get("key")
                if name not in secrets or key not in secrets.get(name, set()):
                    missing.append(f"{path.name}/{container['name']}: secretKeyRef {name}.{key}")

    assert missing == []


def test_gcp_services_target_actual_container_ports(repo_root):
    docs = _manifest_documents(repo_root, "k8s-gcp")
    workloads = [
        doc for _, doc in docs
        if doc.get("kind") in {"Deployment", "StatefulSet", "DaemonSet"}
    ]
    failures: list[str] = []

    for _, service in [(path, doc) for path, doc in docs if doc.get("kind") == "Service"]:
        selector = service.get("spec", {}).get("selector") or {}
        selected = [
            workload
            for workload in workloads
            if all(
                workload.get("spec", {}).get("template", {}).get("metadata", {}).get("labels", {}).get(key) == value
                for key, value in selector.items()
            )
        ]
        port_numbers: set[int] = set()
        port_names: set[str] = set()
        for workload in selected:
            for container in workload.get("spec", {}).get("template", {}).get("spec", {}).get("containers", []):
                for port in container.get("ports", []) or []:
                    if "containerPort" in port:
                        port_numbers.add(port["containerPort"])
                    if port.get("name"):
                        port_names.add(port["name"])

        for port in service.get("spec", {}).get("ports", []) or []:
            target = port.get("targetPort", port.get("port"))
            if isinstance(target, int) and target not in port_numbers:
                failures.append(f"{service['metadata']['name']} targetPort {target} not exposed by selected workload")
            if isinstance(target, str) and target not in port_names:
                failures.append(f"{service['metadata']['name']} targetPort {target} not named by selected workload")

    assert failures == []


def test_gcp_core_workloads_have_resources_and_readiness(repo_root):
    docs = _manifest_documents(repo_root, "k8s-gcp")
    core_primary_containers = {"api-service", "ai-service", "vision-service", "frontend"}
    failures: list[str] = []

    for path, workload, container in _workload_container_specs(docs):
        resources = container.get("resources") or {}
        if not resources.get("requests") or not resources.get("limits"):
            failures.append(f"{path.name}/{workload['metadata']['name']}/{container['name']}: missing resource requests/limits")

        if container.get("name") in core_primary_containers:
            probe = container.get("readinessProbe") or {}
            if not probe.get("httpGet"):
                failures.append(f"{path.name}/{container['name']}: missing readinessProbe.httpGet")

    assert failures == []


@pytest.mark.xfail(
    strict=True,
    reason="Future production hardening: core GCP workloads should expose livenessProbe.httpGet.",
)
def test_gcp_core_workloads_have_liveness_probes(repo_root):
    docs = _manifest_documents(repo_root, "k8s-gcp")
    core_primary_containers = {"api-service", "ai-service", "vision-service", "frontend"}
    failures: list[str] = []

    for path, _, container in _workload_container_specs(docs):
        if container.get("name") not in core_primary_containers:
            continue
        probe = container.get("livenessProbe") or {}
        if not probe.get("httpGet"):
            failures.append(f"{path.name}/{container['name']}: missing livenessProbe.httpGet")

    assert failures == []


def test_gcp_frontend_backendconfig_and_ingress_are_coherent(repo_root):
    docs = _manifest_documents(repo_root, "k8s-gcp")
    services = {doc.get("metadata", {}).get("name"): doc for _, doc in docs if doc.get("kind") == "Service"}
    backend_configs = {doc.get("metadata", {}).get("name") for _, doc in docs if doc.get("kind") == "BackendConfig"}
    ingresses = [doc for _, doc in docs if doc.get("kind") == "Ingress"]

    frontend = services["frontend"]
    annotation = frontend.get("metadata", {}).get("annotations", {}).get("cloud.google.com/backend-config")
    backend_mapping = json.loads(annotation)
    configured_backend = backend_mapping["ports"]["80"]

    assert configured_backend in backend_configs

    for ingress in ingresses:
        annotations = ingress.get("metadata", {}).get("annotations", {})
        assert annotations.get("kubernetes.io/ingress.class") == "gce"
        assert annotations.get("kubernetes.io/ingress.global-static-ip-name")
        for rule in ingress.get("spec", {}).get("rules", []) or []:
            for path in rule.get("http", {}).get("paths", []) or []:
                service = path.get("backend", {}).get("service", {})
                service_name = service.get("name")
                service_port = service.get("port", {}).get("number")
                assert service_name in services
                assert any(port.get("port") == service_port for port in services[service_name].get("spec", {}).get("ports", []))
