"""Import request -> findings, normalized spec and a deterministic deployment plan.

The plan is the complete list of Kubernetes objects a deployment would create, all in
one dedicated namespace (`ar-imp-<name>`) and all carrying the import's ownership
labels. It is rendered from the normalized spec only (never from the input text), so
the same input always gives the same objects and the same digest.

Isolation every plan includes:
  - Pod Security Admission `baseline` enforced on the namespace (`restricted` warned);
  - a ResourceQuota and LimitRange (no NodePorts, LoadBalancers or volume claims);
  - a NetworkPolicy: imported Pods accept traffic only from the namespace (and
    Prometheus), and may only reach the namespace and cluster DNS;
  - no ServiceAccount token, no service-link environment, RuntimeDefault seccomp,
    allowPrivilegeEscalation=false, and no annotations on imported Pods (so they
    cannot opt into metric scraping and pose as AutoResilience's load generator).
Chaos preparation is the same vetted pod-delete setup as the sample namespaces.
"""

import hashlib
import json
from importlib import resources as pkg
from typing import Any

from app.schemas.imports import (
    DeploymentPlan,
    ImportPreview,
    ImportRequest,
    ImportSpec,
    PlannedObject,
    PortSpec,
    ProbeSpec,
    ServicePortSpec,
    ServiceSpec,
    TrafficTarget,
    WorkloadSpec,
)
from app.services.imports.common import (
    Findings,
    check_image,
)
from app.services.imports.compose import parse_compose
from app.services.imports.manifests import parse_manifests
from app.services.imports.safe_yaml import load_documents

NAMESPACE_PREFIX = "ar-imp-"
MANAGED_BY = {"app.kubernetes.io/managed-by": "autoresilience"}
OWNER_LABEL = "autoresilience.io/owner"
OWNER_VALUE = "import"
IMPORT_LABEL = "autoresilience.io/import"
IMPORT_ID_LABEL = "autoresilience.io/import-id"
WORKLOAD_LABEL = "autoresilience.io/workload"
LOADGEN_NAME = "autoresilience-loadgen"
LOADGEN_SCRIPT = "autoresilience-loadgen-script"
# Shared with chaos/rbac (ClusterRoles in infra/rbac/provisioner.yaml).
CHAOS_SERVICE_ACCOUNT = "autoresilience-chaos"
CHAOS_RUNNER_ROLE = "autoresilience-chaos-runner"
ENGINE_CHAOS_ROLE = "autoresilience-engine-chaos"
ENGINE_SUBJECT = {
    "kind": "ServiceAccount",
    "name": "autoresilience-engine",
    "namespace": "autoresilience-system",
}
QUOTA = {
    "pods": "30",
    "requests.cpu": "4",
    "requests.memory": "4Gi",
    "limits.cpu": "8",
    "limits.memory": "8Gi",
    "services": "20",
    "services.nodeports": "0",
    "services.loadbalancers": "0",
    "persistentvolumeclaims": "0",
}


def namespace_for(name: str) -> str:
    return f"{NAMESPACE_PREFIX}{name}"


def is_import_namespace(namespace: str) -> bool:
    return namespace.startswith(NAMESPACE_PREFIX)


def _asset(name: str) -> str:
    return pkg.files("app.services.imports").joinpath("assets", name).read_text()


def parse(request: ImportRequest) -> tuple[ImportSpec | None, Findings]:
    source = request.source
    if source.kind == "image":
        return _image_spec(request)
    if not source.content or not source.content.strip():
        findings = Findings()
        findings.block("empty_file", "The file is empty")
        return None, findings
    if source.kind == "compose":
        return parse_compose(source.content)
    return parse_manifests(source.content)


def _image_spec(request: ImportRequest) -> tuple[ImportSpec | None, Findings]:
    findings = Findings()
    image = request.source.image
    if image is None:
        findings.block("missing_image", "No image is given")
        return None, findings
    ref = check_image(image.image, f"image {request.name}", findings, "image")
    if ref is None:
        return None, findings
    from app.services.imports.common import DEFAULT_RESOURCES

    ports = [PortSpec(container_port=image.port)] if image.port else []
    workload = WorkloadSpec(
        name=request.name,
        image=ref,
        replicas=image.replicas,
        ports=ports,
        readiness=ProbeSpec(
            type="tcp",
            port=image.port,
            period_seconds=5,
            timeout_seconds=2,
            generated=True,
        )
        if image.port
        else None,
        resources=DEFAULT_RESOURCES,
        labels={"app.kubernetes.io/name": request.name},
        selector={"app.kubernetes.io/name": request.name},
    )
    if image.port:
        findings.info(
            "generated_health_check",
            f"Readiness is a TCP connection check on port {image.port} (added by "
            "AutoResilience)",
            subject=f"image {request.name}",
        )
    services = (
        [
            ServiceSpec(
                name=request.name,
                workload=request.name,
                ports=[
                    ServicePortSpec(
                        name=f"tcp-{image.port}",
                        port=image.port,
                        target_port=image.port,
                    )
                ],
            )
        ]
        if image.port
        else []
    )
    return ImportSpec(source="image", workloads=[workload], services=services), findings


def check_traffic(
    spec: ImportSpec, traffic: list[TrafficTarget], findings: Findings
) -> list[TrafficTarget]:
    """Load-generator endpoints must be TCP ports of Services in this import."""
    services = {s.name: s for s in spec.services}
    out: list[TrafficTarget] = []
    for i, t in enumerate(traffic):
        service = services.get(t.service)
        if service is None or not any(
            p.port == t.port and p.protocol == "TCP" for p in service.ports
        ):
            findings.block(
                "invalid_traffic_target",
                f"{t.service}:{t.port} is not a TCP port of a Service in this import",
                path=f"traffic[{i}]",
                hint="Load can only be sent to the imported application's own Services.",
            )
            continue
        if service.headless:
            findings.block(
                "invalid_traffic_target",
                f"{t.service} is headless; send load to a ClusterIP Service",
                path=f"traffic[{i}]",
            )
            continue
        if any(o.service == t.service for o in out):
            findings.block(
                "duplicate_traffic_target",
                f"Only one load target per Service ({t.service})",
                path=f"traffic[{i}]",
            )
            continue
        out.append(t)
    return out


# --- rendering ------------------------------------------------------------------------


def _labels(
    name: str, import_id: str | None, extra: dict[str, str] | None = None
) -> dict[str, str]:
    labels = {**MANAGED_BY, OWNER_LABEL: OWNER_VALUE, IMPORT_LABEL: name}
    if import_id:
        labels[IMPORT_ID_LABEL] = import_id
    return {**(extra or {}), **labels}


def _probe(probe: ProbeSpec | None) -> dict[str, Any] | None:
    if probe is None:
        return None
    out: dict[str, Any] = {
        "initialDelaySeconds": probe.initial_delay_seconds,
        "periodSeconds": probe.period_seconds,
        "timeoutSeconds": probe.timeout_seconds,
        "failureThreshold": probe.failure_threshold,
    }
    if probe.type == "exec":
        out["exec"] = {"command": probe.command}
    elif probe.type == "http":
        out["httpGet"] = {"path": probe.path or "/", "port": probe.port}
    elif probe.type == "tcp":
        out["tcpSocket"] = {"port": probe.port}
    else:
        out["grpc"] = {"port": probe.port}
    return out


def _container(w: WorkloadSpec) -> dict[str, Any]:
    security: dict[str, Any] = {
        "allowPrivilegeEscalation": False,
        "privileged": False,
    }
    if w.read_only_root:
        security["readOnlyRootFilesystem"] = True
    if w.drop_all_capabilities:
        security["capabilities"] = {"drop": ["ALL"]}
    if w.run_as_non_root is not None:
        security["runAsNonRoot"] = w.run_as_non_root
    if w.run_as_user is not None:
        security["runAsUser"] = w.run_as_user
    container: dict[str, Any] = {
        "name": w.name,
        "image": w.image,
        "imagePullPolicy": "IfNotPresent",
        "resources": {
            "requests": {
                "cpu": w.resources.cpu_request,
                "memory": w.resources.memory_request,
            },
            "limits": {
                "cpu": w.resources.cpu_limit,
                "memory": w.resources.memory_limit,
            },
        },
        "securityContext": security,
    }
    if w.command:
        container["command"] = w.command
    if w.args:
        container["args"] = w.args
    if w.working_dir:
        container["workingDir"] = w.working_dir
    if w.ports:
        container["ports"] = [
            {
                "containerPort": p.container_port,
                "protocol": p.protocol,
                **({"name": p.name} if p.name else {}),
            }
            for p in w.ports
        ]
    for key, probe in (
        ("readinessProbe", w.readiness),
        ("livenessProbe", w.liveness),
        ("startupProbe", w.startup),
    ):
        rendered = _probe(probe)
        if rendered:
            container[key] = rendered
    if w.volumes:
        container["volumeMounts"] = [
            {
                "name": v.name,
                "mountPath": v.mount_path,
                **({"readOnly": True} if v.read_only else {}),
            }
            for v in w.volumes
        ]
    return container


def _workload(
    name: str, namespace: str, import_id: str | None, w: WorkloadSpec
) -> dict[str, Any]:
    selector = w.selector or w.labels
    pod_labels = {**w.labels, WORKLOAD_LABEL: w.name}
    volumes: dict[str, dict[str, Any]] = {}
    for v in w.volumes:
        volumes.setdefault(
            v.name,
            {"name": v.name, "emptyDir": {"medium": "Memory"} if v.memory else {}},
        )
    pod: dict[str, Any] = {
        "automountServiceAccountToken": False,
        "enableServiceLinks": False,
        "securityContext": {"seccompProfile": {"type": "RuntimeDefault"}},
        "containers": [_container(w)],
    }
    if volumes:
        pod["volumes"] = list(volumes.values())
    if w.termination_grace_seconds is not None:
        pod["terminationGracePeriodSeconds"] = w.termination_grace_seconds
    spec: dict[str, Any] = {
        "replicas": w.replicas,
        "selector": {"matchLabels": selector},
        "template": {
            "metadata": {"labels": _labels(name, import_id, pod_labels)},
            "spec": pod,
        },
    }
    if w.kind == "StatefulSet":
        spec["serviceName"] = w.service_name
    else:
        spec["revisionHistoryLimit"] = 2
    return {
        "apiVersion": "apps/v1",
        "kind": w.kind,
        "metadata": {
            "name": w.name,
            "namespace": namespace,
            "labels": _labels(name, import_id, {**w.labels, WORKLOAD_LABEL: w.name}),
        },
        "spec": spec,
    }


def _service(
    name: str, namespace: str, import_id: str | None, s: ServiceSpec, w: WorkloadSpec
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "type": "ClusterIP",
        "selector": w.selector or w.labels,
        "ports": [
            {
                "port": p.port,
                "targetPort": p.target_port,
                "protocol": p.protocol,
                **({"name": p.name} if p.name else {}),
            }
            for p in s.ports
        ],
    }
    if s.headless:
        spec["clusterIP"] = "None"
    return {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {
            "name": s.name,
            "namespace": namespace,
            "labels": _labels(name, import_id, {WORKLOAD_LABEL: s.workload}),
        },
        "spec": spec,
    }


def _isolation(name: str, namespace: str, import_id: str | None) -> list[PlannedObject]:
    labels = _labels(name, import_id)
    imported = {"matchExpressions": [{"key": WORKLOAD_LABEL, "operator": "Exists"}]}
    return [
        PlannedObject(
            api_version="v1",
            kind="Namespace",
            name=namespace,
            namespace=None,
            group="isolation",
            purpose="Dedicated namespace: everything the import creates lives here and "
            "is removed with it. Pod Security 'baseline' is enforced.",
            manifest={
                "apiVersion": "v1",
                "kind": "Namespace",
                "metadata": {
                    "name": namespace,
                    "labels": {
                        **labels,
                        "pod-security.kubernetes.io/enforce": "baseline",
                        "pod-security.kubernetes.io/warn": "restricted",
                        "pod-security.kubernetes.io/audit": "restricted",
                    },
                },
            },
        ),
        PlannedObject(
            api_version="v1",
            kind="ResourceQuota",
            name="autoresilience-quota",
            namespace=namespace,
            group="isolation",
            purpose="Caps the namespace's total CPU, memory and Pods; forbids NodePorts, "
            "LoadBalancers and persistent volume claims.",
            manifest={
                "apiVersion": "v1",
                "kind": "ResourceQuota",
                "metadata": {
                    "name": "autoresilience-quota",
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {"hard": QUOTA},
            },
        ),
        PlannedObject(
            api_version="v1",
            kind="LimitRange",
            name="autoresilience-limits",
            namespace=namespace,
            group="isolation",
            purpose="Default and maximum CPU/memory per container.",
            manifest={
                "apiVersion": "v1",
                "kind": "LimitRange",
                "metadata": {
                    "name": "autoresilience-limits",
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "limits": [
                        {
                            "type": "Container",
                            "default": {"cpu": "500m", "memory": "256Mi"},
                            "defaultRequest": {"cpu": "50m", "memory": "64Mi"},
                            "max": {"cpu": "1", "memory": "1Gi"},
                        }
                    ]
                },
            },
        ),
        PlannedObject(
            api_version="networking.k8s.io/v1",
            kind="NetworkPolicy",
            name="autoresilience-isolation",
            namespace=namespace,
            group="isolation",
            purpose="Imported Pods accept connections only from this namespace and "
            "Prometheus, and may connect only within this namespace and to cluster DNS "
            "(enforced if the cluster's network plugin supports NetworkPolicy).",
            manifest={
                "apiVersion": "networking.k8s.io/v1",
                "kind": "NetworkPolicy",
                "metadata": {
                    "name": "autoresilience-isolation",
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "podSelector": imported,
                    "policyTypes": ["Ingress", "Egress"],
                    "ingress": [
                        {
                            "from": [
                                {"podSelector": {}},
                                {
                                    "namespaceSelector": {
                                        "matchLabels": {
                                            "kubernetes.io/metadata.name": "monitoring"
                                        }
                                    }
                                },
                            ]
                        }
                    ],
                    "egress": [
                        {"to": [{"podSelector": {}}]},
                        {
                            "to": [
                                {
                                    "namespaceSelector": {
                                        "matchLabels": {
                                            "kubernetes.io/metadata.name": "kube-system"
                                        }
                                    },
                                    "podSelector": {
                                        "matchLabels": {"k8s-app": "kube-dns"}
                                    },
                                }
                            ],
                            "ports": [
                                {"protocol": "UDP", "port": 53},
                                {"protocol": "TCP", "port": 53},
                            ],
                        },
                    ],
                },
            },
        ),
    ]


def _chaos(name: str, namespace: str, import_id: str | None) -> list[PlannedObject]:
    labels = _labels(name, import_id)
    experiment = load_documents(_asset("pod-delete.yaml"))[0]
    experiment["metadata"]["namespace"] = namespace
    experiment["metadata"]["labels"] = {
        **experiment["metadata"].get("labels", {}),
        **labels,
    }

    def binding(
        binding_name: str, role: str, subject: dict[str, str]
    ) -> dict[str, Any]:
        return {
            "apiVersion": "rbac.authorization.k8s.io/v1",
            "kind": "RoleBinding",
            "metadata": {
                "name": binding_name,
                "namespace": namespace,
                "labels": labels,
            },
            "roleRef": {
                "apiGroup": "rbac.authorization.k8s.io",
                "kind": "ClusterRole",
                "name": role,
            },
            "subjects": [subject],
        }

    return [
        PlannedObject(
            api_version="litmuschaos.io/v1alpha1",
            kind="ChaosExperiment",
            name="pod-delete",
            namespace=namespace,
            group="chaos",
            purpose="The vetted pod-delete definition (chaos/templates/pod-delete.yaml); "
            "it runs only when you start an experiment.",
            manifest=experiment,
        ),
        PlannedObject(
            api_version="v1",
            kind="ServiceAccount",
            name=CHAOS_SERVICE_ACCOUNT,
            namespace=namespace,
            group="chaos",
            purpose="Identity of Litmus' pod-delete runner in this namespace.",
            manifest={
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {
                    "name": CHAOS_SERVICE_ACCOUNT,
                    "namespace": namespace,
                    "labels": labels,
                },
            },
        ),
        PlannedObject(
            api_version="rbac.authorization.k8s.io/v1",
            kind="RoleBinding",
            name=CHAOS_SERVICE_ACCOUNT,
            namespace=namespace,
            group="chaos",
            purpose="Lets the runner delete Pods in this namespace only (the same rules "
            "as chaos/rbac/pod-delete-rbac.yaml).",
            manifest=binding(
                CHAOS_SERVICE_ACCOUNT,
                CHAOS_RUNNER_ROLE,
                {
                    "kind": "ServiceAccount",
                    "name": CHAOS_SERVICE_ACCOUNT,
                    "namespace": namespace,
                },
            ),
        ),
        PlannedObject(
            api_version="rbac.authorization.k8s.io/v1",
            kind="RoleBinding",
            name=ENGINE_CHAOS_ROLE,
            namespace=namespace,
            group="chaos",
            purpose="Lets the engine create and stop its own ChaosEngines here (local "
            "stack identity; the same rules as in the sample namespaces).",
            manifest=binding(ENGINE_CHAOS_ROLE, ENGINE_CHAOS_ROLE, ENGINE_SUBJECT),
        ),
    ]


def _loadgen(
    name: str,
    namespace: str,
    import_id: str | None,
    spec: ImportSpec,
    traffic: list[TrafficTarget],
    image: str,
) -> list[PlannedObject]:
    labels = _labels(name, import_id)
    services = {s.name: s for s in spec.services}
    suffix = f".{namespace}.svc.cluster.local"
    targets = ";".join(
        f"{namespace}/{services[t.service].workload}=http://{t.service}{suffix}:{t.port}{t.path}"
        for t in traffic
    )
    pod_labels = {
        **labels,
        "app.kubernetes.io/name": LOADGEN_NAME,
        WORKLOAD_LABEL: LOADGEN_NAME,
    }
    script = _asset("loadgen.py")
    digest = hashlib.sha256(script.encode()).hexdigest()[:16]
    return [
        PlannedObject(
            api_version="v1",
            kind="ConfigMap",
            name=LOADGEN_SCRIPT,
            namespace=namespace,
            group="load-generator",
            purpose="AutoResilience's load generator script (infra/sample-app/loadgen).",
            manifest={
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": LOADGEN_SCRIPT,
                    "namespace": namespace,
                    "labels": labels,
                },
                "data": {"loadgen.py": script},
            },
        ),
        PlannedObject(
            api_version="apps/v1",
            kind="Deployment",
            name=LOADGEN_NAME,
            namespace=namespace,
            group="load-generator",
            purpose="Sends 5 requests per second to each approved endpoint and exports what "
            "the client saw, for client-side evidence. It refuses any target outside this "
            "namespace.",
            manifest={
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {
                    "name": LOADGEN_NAME,
                    "namespace": namespace,
                    "labels": labels,
                },
                "spec": {
                    "replicas": 1,
                    "selector": {
                        "matchLabels": {"app.kubernetes.io/name": LOADGEN_NAME}
                    },
                    "template": {
                        "metadata": {
                            "labels": pod_labels,
                            "annotations": {
                                "prometheus.io/scrape": "true",
                                "prometheus.io/port": "9100",
                                "prometheus.io/path": "/metrics",
                                "autoresilience.io/script-sha": digest,
                            },
                        },
                        "spec": {
                            "automountServiceAccountToken": False,
                            "enableServiceLinks": False,
                            "securityContext": {
                                "seccompProfile": {"type": "RuntimeDefault"}
                            },
                            "containers": [
                                {
                                    "name": "loadgen",
                                    "image": image,
                                    "imagePullPolicy": "IfNotPresent",
                                    "command": ["python", "-u", "/app/loadgen.py"],
                                    "env": [
                                        {"name": "TARGETS", "value": targets},
                                        {
                                            "name": "ALLOWED_HOST_SUFFIX",
                                            "value": suffix,
                                        },
                                        {"name": "INTERVAL_SECONDS", "value": "0.2"},
                                        {"name": "TIMEOUT_SECONDS", "value": "1"},
                                    ],
                                    "ports": [
                                        {"name": "metrics", "containerPort": 9100}
                                    ],
                                    "readinessProbe": {
                                        "httpGet": {"path": "/metrics", "port": 9100}
                                    },
                                    "volumeMounts": [
                                        {"name": "script", "mountPath": "/app"}
                                    ],
                                    "resources": {
                                        "requests": {"cpu": "20m", "memory": "24Mi"},
                                        "limits": {"cpu": "200m", "memory": "64Mi"},
                                    },
                                    "securityContext": {
                                        "allowPrivilegeEscalation": False,
                                        "privileged": False,
                                        "runAsNonRoot": True,
                                        "runAsUser": 65534,
                                        "readOnlyRootFilesystem": True,
                                        "capabilities": {"drop": ["ALL"]},
                                    },
                                }
                            ],
                            "volumes": [
                                {
                                    "name": "script",
                                    "configMap": {"name": LOADGEN_SCRIPT},
                                }
                            ],
                        },
                    },
                },
            },
        ),
    ]


def digest_of(objects: list[PlannedObject]) -> str:
    canonical = json.dumps(
        [o.manifest for o in objects], sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def render_plan(
    name: str,
    spec: ImportSpec,
    traffic: list[TrafficTarget],
    *,
    import_id: str | None,
    loadgen_image: str,
) -> DeploymentPlan:
    namespace = namespace_for(name)
    workloads = {w.name: w for w in spec.workloads}
    objects = _isolation(name, namespace, import_id) + _chaos(
        name, namespace, import_id
    )
    for w in spec.workloads:
        objects.append(
            PlannedObject(
                api_version="apps/v1",
                kind=w.kind,
                name=w.name,
                namespace=namespace,
                group="application",
                purpose=f"{w.replicas} replica(s) of {w.image}.",
                manifest=_workload(name, namespace, import_id, w),
            )
        )
    for s in spec.services:
        objects.append(
            PlannedObject(
                api_version="v1",
                kind="Service",
                name=s.name,
                namespace=namespace,
                group="application",
                purpose=f"Cluster-internal address for {s.workload}: "
                + ", ".join(f"{s.name}:{p.port}" for p in s.ports)
                + ".",
                manifest=_service(name, namespace, import_id, s, workloads[s.workload]),
            )
        )
    if traffic:
        objects += _loadgen(name, namespace, import_id, spec, traffic, loadgen_image)
    unset = sum(len(w.env_names) for w in spec.workloads)
    kinds: dict[str, int] = {}
    for o in objects:
        if o.group == "application":
            kinds[o.kind] = kinds.get(o.kind, 0) + 1
    actions = [
        (
            f"Create namespace {namespace} on the execution cluster, labelled as owned "
            "by this import, with Pod Security 'baseline' enforced"
        ),
        "Create "
        + ", ".join(f"{n} {k}{'s' if n > 1 else ''}" for k, n in sorted(kinds.items()))
        + " from the reviewed images",
        "Add a resource quota, default limits and a network isolation policy",
        "Bind the provisioner to a writer role inside this namespace only",
        "Prepare the vetted pod-delete experiment (it never runs by itself)",
    ]
    if traffic:
        actions.append(
            "Start a load generator for: "
            + ", ".join(f"{t.service}:{t.port}{t.path}" for t in traffic)
        )
    guarantees = [
        f"Nothing outside {namespace} is created or changed",
        (
            "No host paths, Docker socket, privileged containers, host namespaces or "
            "added capabilities"
        ),
        "No Secrets, ConfigMaps or environment values copied"
        + (f" ({unset} variable(s) stay unset)" if unset else ""),
        "No NodePort or LoadBalancer: reachable only inside the cluster",
        "Imported Pods get no Kubernetes API token",
        "No experiment starts: chaos still needs a reviewed, validated experiment",
    ]
    return DeploymentPlan(
        namespace=namespace,
        objects=objects,
        digest=digest_of(objects),
        actions=actions,
        guarantees=guarantees,
        traffic=traffic,
    )


def preview(
    request: ImportRequest, *, import_id: str | None, loadgen_image: str
) -> ImportPreview:
    spec, findings = parse(request)
    traffic: list[TrafficTarget] = []
    if spec is not None:
        traffic = check_traffic(spec, request.traffic, findings)
        if not spec.services and not findings.blocking:
            findings.info(
                "no_services",
                "No ports, so no Services: the workloads are not reachable and no load "
                "can be sent to them",
            )
    deployable = spec is not None and not findings.blocking
    plan = (
        render_plan(
            request.name,
            spec,
            traffic,
            import_id=import_id,
            loadgen_image=loadgen_image,
        )
        if deployable and spec is not None
        else None
    )
    return ImportPreview(
        name=request.name,
        source=request.source.kind,
        filename=request.source.filename,
        spec=spec,
        findings=findings.sorted(),
        deployable=deployable,
        plan=plan,
    )
