"""Kubernetes manifests (supported subset) -> normalized ImportSpec (pure).

Accepted kinds: apps/v1 Deployment and StatefulSet (one container, no persistent
volume claims), v1 Service (ClusterIP or headless). A `List` is flattened; a
Namespace is ignored (the import gets its own). Every other kind is refused: no
CRDs, RBAC, Secrets, ConfigMaps, Jobs, DaemonSets, Ingresses or webhooks.

Manifests are not applied as written: the supported fields are read through an
allowlist into the same spec a Compose file produces, and the plan renders fresh
objects from it. Anything security-sensitive (privileges, host namespaces, host
paths, added capabilities, hostPort, probe hosts, ServiceAccounts, Secrets) is
refused; anything merely unsupported is reported.
"""

from typing import Any

from app.schemas.imports import (
    ImportSpec,
    PortSpec,
    ProbeSpec,
    ServicePortSpec,
    ServiceSpec,
    VolumeSpec,
    WorkloadSpec,
)
from app.services.imports.common import (
    MAX_PORTS,
    MAX_REPLICAS,
    MAX_WORKLOADS,
    Findings,
    check_image,
    check_labels,
    check_name,
    check_strings,
    env_names,
    resources,
)
from app.services.imports.safe_yaml import YamlInputError, load_documents

WORKLOAD_KINDS = {"Deployment", "StatefulSet"}
SUPPORTED_KINDS = ["apps/v1 Deployment", "apps/v1 StatefulSet", "v1 Service"]
REFUSED_KINDS = {
    "Secret": "Secrets are never imported: credentials are not read or copied",
    "ConfigMap": "ConfigMaps are not imported in this version: configuration is not "
    "copied into test deployments",
    "CustomResourceDefinition": "CRDs change the cluster's API and are never imported",
    "Pod": "Bare Pods are not supported; use a Deployment",
    "DaemonSet": "DaemonSets run on every node and are not supported",
    "Job": "Jobs are not supported",
    "CronJob": "CronJobs are not supported",
    "ServiceAccount": "ServiceAccounts are not imported: imported Pods get no API access",
    "Role": "RBAC objects are never imported",
    "ClusterRole": "RBAC objects are never imported",
    "RoleBinding": "RBAC objects are never imported",
    "ClusterRoleBinding": "RBAC objects are never imported",
    "PersistentVolumeClaim": "Persistent storage is not provisioned for test deployments",
    "PersistentVolume": "Persistent storage is not provisioned for test deployments",
    "Ingress": "Ingresses would expose the application outside the cluster",
    "NetworkPolicy": "The import applies its own isolation policy",
    "ValidatingWebhookConfiguration": "Admission webhooks are never imported",
    "MutatingWebhookConfiguration": "Admission webhooks are never imported",
}
HOOK_ANNOTATIONS = ("helm.sh/hook", "argocd.argoproj.io/hook")

POD_SPEC_ALLOWED = {
    "containers",
    "volumes",
    "terminationGracePeriodSeconds",
    "securityContext",
}
# Dropped with a warning: scheduling and identity settings the test namespace sets itself.
POD_SPEC_IGNORED = {
    "nodeSelector",
    "affinity",
    "tolerations",
    "topologySpreadConstraints",
    "priorityClassName",
    "schedulerName",
    "dnsPolicy",
    "dnsConfig",
    "restartPolicy",
    "imagePullSecrets",
    "serviceAccountName",
    "serviceAccount",
    "automountServiceAccountToken",
    "enableServiceLinks",
    "hostname",
    "subdomain",
    "preemptionPolicy",
    "runtimeClassName",
}
POD_SPEC_REFUSED = {
    "hostNetwork": "Host networking is never allowed",
    "hostPID": "Sharing the host PID namespace is never allowed",
    "hostIPC": "Sharing the host IPC namespace is never allowed",
    "hostUsers": "Host user namespaces are not supported",
    "nodeName": "Pinning to a node is not allowed",
    "initContainers": "Init containers are not supported in this version",
    "ephemeralContainers": "Ephemeral containers are not supported",
    "shareProcessNamespace": "Sharing the process namespace is not supported",
    "hostAliases": "Host aliases are not supported",
    "overhead": "Not supported",
    "os": "Not supported",
    "readinessGates": "Not supported",
    "resourceClaims": "Not supported",
    "schedulingGates": "Not supported",
    "setHostnameAsFQDN": "Not supported",
}
CONTAINER_ALLOWED = {
    "name",
    "image",
    "imagePullPolicy",
    "command",
    "args",
    "workingDir",
    "ports",
    "env",
    "envFrom",
    "resources",
    "readinessProbe",
    "livenessProbe",
    "startupProbe",
    "volumeMounts",
    "securityContext",
    "terminationMessagePath",
    "terminationMessagePolicy",
    "stdin",
    "tty",
    "lifecycle",
}
CONTAINER_SECURITY_ALLOWED = {
    "runAsNonRoot",
    "runAsUser",
    "runAsGroup",
    "readOnlyRootFilesystem",
    "allowPrivilegeEscalation",
    "capabilities",
    "seccompProfile",
}


class _Manifests:
    def __init__(self, findings: Findings) -> None:
        self.f = findings
        self.workloads: list[tuple[WorkloadSpec, dict[str, str]]] = []
        self.services: list[tuple[ServiceSpec, dict[str, str], str]] = []

    # --- documents -------------------------------------------------------------

    def objects(self, documents: list[Any]) -> list[tuple[str, dict[str, Any]]]:
        out = []
        for i, doc in enumerate(documents):
            where = f"document {i + 1}"
            if not isinstance(doc, dict):
                self.f.block("invalid_object", "Not a Kubernetes object", path=where)
                continue
            if doc.get("kind") == "List" and isinstance(doc.get("items"), list):
                for j, item in enumerate(doc["items"]):
                    if isinstance(item, dict):
                        out.append((f"{where}.items[{j}]", item))
                    else:
                        self.f.block(
                            "invalid_object", "Not a Kubernetes object", path=where
                        )
                continue
            out.append((where, doc))
        return out

    def object(self, where: str, obj: dict[str, Any]) -> None:
        kind, api = obj.get("kind"), obj.get("apiVersion")
        meta = _d(obj.get("metadata"))
        name = meta.get("name") if isinstance(meta, dict) else None
        subject = f"{kind} {name}" if isinstance(kind, str) else where
        if not isinstance(kind, str) or not isinstance(api, str):
            self.f.block(
                "invalid_object",
                "Missing apiVersion or kind",
                subject=subject,
                path=where,
            )
            return
        annotations = _d(meta.get("annotations"))
        hooks = [a for a in HOOK_ANNOTATIONS if a in annotations]
        if hooks:
            self.f.block(
                "hook_annotation",
                f"Deployment hooks ({', '.join(hooks)}) are never run",
                subject=subject,
                path=f"{where}.metadata.annotations",
                hint="Remove the hook resources; imports deploy only plain workloads.",
            )
            return
        if kind == "Namespace":
            self.f.warn(
                "namespace_ignored",
                "Namespaces are not created as written: the import gets its own isolated "
                "namespace",
                subject=subject,
                path=where,
            )
            return
        if kind in REFUSED_KINDS:
            self.f.block(
                "unsupported_kind", REFUSED_KINDS[kind], subject=subject, path=where
            )
            return
        supported = (api == "apps/v1" and kind in WORKLOAD_KINDS) or (
            api == "v1" and kind == "Service"
        )
        if not supported:
            self.f.block(
                "unsupported_kind",
                f"{api} {kind} is not supported (custom resources and other kinds are "
                "never applied)",
                subject=subject,
                path=where,
                hint="Supported: " + ", ".join(SUPPORTED_KINDS) + ".",
            )
            return
        name = check_name(name, kind, self.f, f"{where}.metadata.name")
        if name is None:
            return
        namespace = meta.get("namespace")
        if namespace is not None:
            self.f.info(
                "namespace_replaced",
                f"metadata.namespace {str(namespace)[:63]!r} is replaced by the import's "
                "own namespace",
                subject=subject,
                path=f"{where}.metadata.namespace",
            )
        if annotations:
            self.f.info(
                "annotations_dropped",
                "Annotations are not copied (they can change controller behaviour or "
                "opt Pods into metric scraping)",
                subject=subject,
                path=f"{where}.metadata.annotations",
            )
        for key in obj:
            if key not in ("apiVersion", "kind", "metadata", "spec", "status"):
                self.f.block(
                    "unsupported_field",
                    f"Top-level `{key}` is not supported",
                    subject=subject,
                    path=f"{where}.{key}",
                )
        spec = obj.get("spec") if isinstance(obj.get("spec"), dict) else None
        if spec is None:
            self.f.block("invalid_object", "Missing spec", subject=subject, path=where)
            return
        if kind == "Service":
            self.service(name, spec, subject, f"{where}.spec")
        else:
            self.workload(kind, name, spec, subject, f"{where}.spec")

    # --- workloads ---------------------------------------------------------------

    def workload(
        self, kind: str, name: str, spec: dict[str, Any], subject: str, path: str
    ) -> None:
        for key in spec:
            if key in ("replicas", "selector", "template", "serviceName"):
                continue
            if key == "volumeClaimTemplates":
                self.f.block(
                    "persistent_storage",
                    "volumeClaimTemplates would provision persistent volumes; test "
                    "deployments use no persistent storage",
                    subject=subject,
                    path=f"{path}.{key}",
                    hint="Remove them, or mount an emptyDir for scratch data.",
                )
            else:
                self.f.info(
                    "ignored_setting",
                    f"spec.{key} is ignored",
                    subject=subject,
                    path=f"{path}.{key}",
                )
        replicas = spec.get("replicas", 1)
        if not isinstance(replicas, int) or isinstance(replicas, bool) or replicas < 1:
            self.f.block(
                "invalid_replicas",
                "Replicas must be a positive integer",
                subject=subject,
                path=f"{path}.replicas",
            )
            replicas = 1
        elif replicas > MAX_REPLICAS:
            self.f.block(
                "too_many_replicas",
                f"{replicas} replicas; test deployments are limited to {MAX_REPLICAS}",
                subject=subject,
                path=f"{path}.replicas",
            )
            replicas = MAX_REPLICAS
        selector = _d(spec.get("selector"))
        if set(selector) - {"matchLabels"}:
            self.f.block(
                "unsupported_selector",
                "Only selector.matchLabels is supported",
                subject=subject,
                path=f"{path}.selector",
            )
        match = check_labels(
            selector.get("matchLabels"), subject, self.f, f"{path}.selector"
        )
        template = _d(spec.get("template"))
        tmeta = _d(template.get("metadata"))
        labels = check_labels(
            tmeta.get("labels"), subject, self.f, f"{path}.template.metadata.labels"
        )
        if not match:
            self.f.block(
                "missing_selector",
                "A non-empty selector.matchLabels is required",
                subject=subject,
                path=f"{path}.selector",
            )
        elif any(labels.get(k) != v for k, v in match.items()):
            self.f.block(
                "selector_mismatch",
                "selector.matchLabels does not match the Pod template's labels",
                subject=subject,
                path=f"{path}.selector",
            )
        if tmeta.get("annotations"):
            self.f.info(
                "annotations_dropped",
                "Pod annotations are not copied (no metric scraping or sidecar "
                "injection opt-ins)",
                subject=subject,
                path=f"{path}.template.metadata.annotations",
            )
        pod = template.get("spec") if isinstance(template.get("spec"), dict) else None
        if pod is None:
            self.f.block(
                "invalid_object",
                "Missing spec.template.spec",
                subject=subject,
                path=path,
            )
            return
        workload = self.pod(
            kind, name, replicas, labels, pod, subject, f"{path}.template.spec"
        )
        if workload is None:
            return
        workload.selector = match
        if kind == "StatefulSet":
            service_name = spec.get("serviceName")
            workload.service_name = (
                service_name if isinstance(service_name, str) else None
            )
        self.workloads.append((workload, match))

    def pod(
        self,
        kind: str,
        name: str,
        replicas: int,
        labels: dict[str, str],
        pod: dict[str, Any],
        subject: str,
        path: str,
    ) -> WorkloadSpec | None:
        for key, value in pod.items():
            if key in POD_SPEC_ALLOWED:
                continue
            if key in POD_SPEC_REFUSED:
                if value in (False, None):
                    continue
                self.f.block(
                    f"unsafe_{key}",
                    POD_SPEC_REFUSED[key],
                    subject=subject,
                    path=f"{path}.{key}",
                )
            elif key in POD_SPEC_IGNORED:
                self.f.warn(
                    "ignored_setting",
                    f"{key} is ignored"
                    + (
                        ": imported Pods run without a ServiceAccount token"
                        if key.startswith(("serviceAccount", "automount"))
                        else ""
                    ),
                    subject=subject,
                    path=f"{path}.{key}",
                )
            else:
                self.f.block(
                    "unsupported_field",
                    f"Pod spec `{key}` is not supported",
                    subject=subject,
                    path=f"{path}.{key}",
                )
        pod_security = pod.get("securityContext") or {}
        if isinstance(pod_security, dict):
            for key in pod_security:
                if key in (
                    "runAsNonRoot",
                    "runAsUser",
                    "runAsGroup",
                    "fsGroup",
                    "seccompProfile",
                ):
                    continue
                self.f.block(
                    "unsafe_security_context",
                    f"Pod securityContext.{key} is not allowed",
                    subject=subject,
                    path=f"{path}.securityContext.{key}",
                )
            profile = pod_security.get("seccompProfile")
            if isinstance(profile, dict) and profile.get("type") == "Unconfined":
                self.f.block(
                    "unsafe_seccomp",
                    "An Unconfined seccomp profile is not allowed",
                    subject=subject,
                    path=f"{path}.securityContext.seccompProfile",
                )
        volumes = self.volumes(pod.get("volumes"), subject, f"{path}.volumes")
        containers = pod.get("containers")
        if not isinstance(containers, list) or not containers:
            self.f.block(
                "invalid_object",
                "No containers",
                subject=subject,
                path=f"{path}.containers",
            )
            return None
        if len(containers) > 1:
            self.f.block(
                "multiple_containers",
                "Only one container per workload is supported (no sidecars)",
                subject=subject,
                path=f"{path}.containers",
                hint="Split extra containers into their own Deployments.",
            )
            return None
        c = _d(containers[0])
        cpath = f"{path}.containers[0]"
        for key in c:
            if key not in CONTAINER_ALLOWED:
                self.f.block(
                    "unsupported_field",
                    f"Container `{key}` is not supported",
                    subject=subject,
                    path=f"{cpath}.{key}",
                )
        if c.get("lifecycle"):
            self.f.warn(
                "ignored_setting",
                "Lifecycle hooks are ignored",
                subject=subject,
                path=f"{cpath}.lifecycle",
            )
        image = check_image(c.get("image"), subject, self.f, f"{cpath}.image")
        security = c.get("securityContext") or {}
        run_as_user = None
        read_only = False
        drop_all = False
        non_root = None
        if isinstance(security, dict):
            for key, value in security.items():
                if key not in CONTAINER_SECURITY_ALLOWED:
                    self.f.block(
                        "unsafe_security_context",
                        f"securityContext.{key} is not allowed",
                        subject=subject,
                        path=f"{cpath}.securityContext.{key}",
                    )
            if security.get("allowPrivilegeEscalation") is True:
                self.f.block(
                    "privilege_escalation",
                    "allowPrivilegeEscalation: true is not allowed",
                    subject=subject,
                    path=f"{cpath}.securityContext",
                )
            caps = security.get("capabilities") or {}
            if isinstance(caps, dict) and caps.get("add"):
                self.f.block(
                    "added_capabilities",
                    "Added Linux capabilities are not allowed",
                    subject=subject,
                    path=f"{cpath}.securityContext.capabilities.add",
                )
            user = security.get("runAsUser")
            if isinstance(user, int) and not isinstance(user, bool):
                run_as_user = user
            read_only = security.get("readOnlyRootFilesystem") is True
            drop_all = isinstance(caps, dict) and "ALL" in (caps.get("drop") or [])
            non_root = (
                security.get("runAsNonRoot")
                if isinstance(security.get("runAsNonRoot"), bool)
                else None
            )
        ports = self.ports(c.get("ports"), subject, f"{cpath}.ports")
        names: list[str] = []
        for i, env in enumerate(c.get("env") or []):
            if isinstance(env, dict) and isinstance(env.get("name"), str):
                names.append(env["name"])
                if (
                    isinstance(env.get("valueFrom"), dict)
                    and "secretKeyRef" in env["valueFrom"]
                ):
                    self.f.warn(
                        "secret_reference_dropped",
                        f"{env['name']} reads a Secret; it is not set",
                        subject=subject,
                        path=f"{cpath}.env[{i}]",
                    )
        if c.get("envFrom"):
            self.f.warn(
                "env_from_dropped",
                "envFrom is ignored: no ConfigMaps or Secrets are copied",
                subject=subject,
                path=f"{cpath}.envFrom",
            )
        res = _d(c.get("resources"))
        limits = _d(res.get("limits"))
        requests = _d(res.get("requests"))
        for section in (limits, requests):
            for key in list(section):
                if key not in ("cpu", "memory"):
                    self.f.block(
                        "unsupported_resource",
                        f"Resource {key!r} is not supported",
                        subject=subject,
                        path=f"{cpath}.resources",
                    )
        mounts = []
        by_name = {v.name: v for v in volumes}
        for i, m in enumerate(c.get("volumeMounts") or []):
            if not isinstance(m, dict) or m.get("name") not in by_name:
                self.f.block(
                    "invalid_volume_mount",
                    "Mounts an undeclared or refused volume",
                    subject=subject,
                    path=f"{cpath}.volumeMounts[{i}]",
                )
                continue
            target = m.get("mountPath")
            if not isinstance(target, str) or not target.startswith("/"):
                self.f.block(
                    "invalid_volume_mount",
                    "mountPath must be absolute",
                    subject=subject,
                    path=f"{cpath}.volumeMounts[{i}]",
                )
                continue
            if m.get("mountPropagation") not in (None, "None"):
                self.f.block(
                    "mount_propagation",
                    "Mount propagation is not allowed",
                    subject=subject,
                    path=f"{cpath}.volumeMounts[{i}]",
                )
                continue
            base = by_name[m["name"]]
            mounts.append(
                VolumeSpec(
                    name=base.name,
                    mount_path=target,
                    read_only=m.get("readOnly") is True,
                    memory=base.memory,
                )
            )
        working_dir = c.get("workingDir")
        return WorkloadSpec(
            name=name,
            kind=kind,  # type: ignore[arg-type]
            image=image or "",
            replicas=replicas,
            command=check_strings(
                c.get("command"), subject, self.f, f"{cpath}.command"
            ),
            args=check_strings(c.get("args"), subject, self.f, f"{cpath}.args"),
            working_dir=working_dir
            if isinstance(working_dir, str) and working_dir.startswith("/")
            else None,
            ports=ports,
            readiness=self.probe(
                c.get("readinessProbe"), subject, f"{cpath}.readinessProbe"
            ),
            liveness=self.probe(
                c.get("livenessProbe"), subject, f"{cpath}.livenessProbe"
            ),
            startup=self.probe(c.get("startupProbe"), subject, f"{cpath}.startupProbe"),
            resources=resources(
                limits, requests, subject, self.f, f"{cpath}.resources"
            ),
            volumes=mounts,
            read_only_root=read_only,
            drop_all_capabilities=drop_all,
            run_as_non_root=non_root,
            run_as_user=run_as_user,
            termination_grace_seconds=_grace(pod.get("terminationGracePeriodSeconds")),
            labels=labels,
            selector={},
            env_names=env_names(names, subject, self.f, f"{cpath}.env"),
        )

    def volumes(self, raw: Any, subject: str, path: str) -> list[VolumeSpec]:
        out = []
        for i, v in enumerate(raw or []):
            if not isinstance(v, dict) or not isinstance(v.get("name"), str):
                self.f.block(
                    "invalid_volume",
                    "Not a volume",
                    subject=subject,
                    path=f"{path}[{i}]",
                )
                continue
            sources = [k for k in v if k != "name"]
            if sources == ["emptyDir"]:
                empty = _d(v["emptyDir"])
                out.append(
                    VolumeSpec(
                        name=v["name"],
                        mount_path="/",
                        memory=empty.get("medium") == "Memory",
                    )
                )
                self.f.warn(
                    "ephemeral_volume",
                    f"Volume {v['name']} is an emptyDir: data is lost when the Pod goes",
                    subject=subject,
                    path=f"{path}[{i}]",
                )
                continue
            kind = sources[0] if sources else "unknown"
            message = {
                "hostPath": "hostPath volumes would expose node files; never allowed",
                "secret": "Secret volumes are not imported (no credentials are copied)",
                "configMap": "ConfigMap volumes are not supported in this version",
                "persistentVolumeClaim": "Persistent volumes are not provisioned",
                "projected": "Projected volumes (tokens, secrets) are not allowed",
            }.get(kind, f"{kind} volumes are not supported")
            self.f.block(
                "unsafe_volume" if kind == "hostPath" else "unsupported_volume",
                message,
                subject=subject,
                path=f"{path}[{i}]",
                hint="Only emptyDir volumes are supported.",
            )
        return out

    def ports(self, raw: Any, subject: str, path: str) -> list[PortSpec]:
        out = []
        for i, p in enumerate(raw or []):
            if (
                not isinstance(p, dict)
                or not isinstance(p.get("containerPort"), int)
                or not (1 <= p["containerPort"] <= 65535)
            ):
                self.f.block(
                    "invalid_port",
                    "containerPort must be 1-65535",
                    subject=subject,
                    path=f"{path}[{i}]",
                )
                continue
            if p.get("hostPort") or p.get("hostIP"):
                self.f.block(
                    "host_port",
                    "hostPort binds on the node and is not allowed",
                    subject=subject,
                    path=f"{path}[{i}]",
                    hint="Remove hostPort; reach the workload through its Service.",
                )
                continue
            protocol = p.get("protocol", "TCP")
            if protocol not in ("TCP", "UDP"):
                self.f.block(
                    "invalid_port",
                    f"Protocol {protocol!r} is not supported",
                    subject=subject,
                    path=f"{path}[{i}]",
                )
                continue
            name = p.get("name") if isinstance(p.get("name"), str) else None
            out.append(
                PortSpec(
                    container_port=p["containerPort"], protocol=protocol, name=name
                )
            )
        if len(out) > MAX_PORTS:
            self.f.block(
                "too_many_ports",
                f"More than {MAX_PORTS} ports",
                subject=subject,
                path=path,
            )
        return out

    def probe(self, raw: Any, subject: str, path: str) -> ProbeSpec | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            self.f.block("invalid_probe", "Not a probe", subject=subject, path=path)
            return None
        timing: dict[str, Any] = {
            "initial_delay_seconds": _bounded(
                raw.get("initialDelaySeconds"), 0, 300, 0
            ),
            "period_seconds": _bounded(raw.get("periodSeconds"), 1, 300, 10),
            "timeout_seconds": _bounded(raw.get("timeoutSeconds"), 1, 60, 1),
            "failure_threshold": _bounded(raw.get("failureThreshold"), 1, 10, 3),
        }
        handlers = [k for k in ("exec", "httpGet", "tcpSocket", "grpc") if k in raw]
        if len(handlers) != 1:
            self.f.block(
                "invalid_probe",
                "A probe needs exactly one of exec, httpGet, tcpSocket, grpc",
                subject=subject,
                path=path,
            )
            return None
        handler = _d(raw[handlers[0]])
        if handler.get("host"):
            self.f.block(
                "probe_host",
                "Probes with a `host` would make the kubelet contact another address",
                subject=subject,
                path=f"{path}.{handlers[0]}.host",
                hint="Remove `host`; probes check the Pod itself.",
            )
            return None
        if handlers[0] == "exec":
            command = check_strings(
                handler.get("command"), subject, self.f, f"{path}.exec.command"
            )
            return (
                ProbeSpec(type="exec", command=command, **timing) if command else None
            )
        port = handler.get("port")
        if not (isinstance(port, int) and 1 <= port <= 65535) and not (
            isinstance(port, str)
            and port.isalnum()
            and port.islower()
            and len(port) <= 15
        ):
            self.f.block(
                "invalid_probe", "The probe port is invalid", subject=subject, path=path
            )
            return None
        if handlers[0] == "httpGet":
            probe_path = handler.get("path", "/")
            if handler.get("httpHeaders"):
                self.f.warn(
                    "ignored_setting",
                    "Probe httpHeaders are ignored",
                    subject=subject,
                    path=path,
                )
            if handler.get("scheme") not in (None, "HTTP", "HTTPS"):
                self.f.block(
                    "invalid_probe",
                    "Unsupported probe scheme",
                    subject=subject,
                    path=path,
                )
                return None
            if not isinstance(probe_path, str) or not probe_path.startswith("/"):
                self.f.block(
                    "invalid_probe",
                    "The probe path must be absolute",
                    subject=subject,
                    path=path,
                )
                return None
            return ProbeSpec(type="http", path=probe_path[:200], port=port, **timing)
        return ProbeSpec(
            type="tcp" if handlers[0] == "tcpSocket" else "grpc", port=port, **timing
        )

    # --- services ----------------------------------------------------------------

    def service(self, name: str, spec: dict[str, Any], subject: str, path: str) -> None:
        kind = spec.get("type", "ClusterIP")
        if kind == "ExternalName" or spec.get("externalName"):
            self.f.block(
                "external_service",
                "ExternalName Services point outside the cluster and are not supported",
                subject=subject,
                path=path,
            )
            return
        if spec.get("externalIPs"):
            self.f.block(
                "external_ips",
                "externalIPs are not allowed",
                subject=subject,
                path=f"{path}.externalIPs",
            )
            return
        if kind in ("NodePort", "LoadBalancer"):
            self.f.warn(
                "service_exposure_removed",
                f"type {kind} becomes ClusterIP: test deployments are not exposed outside "
                "the cluster",
                subject=subject,
                path=f"{path}.type",
            )
        elif kind != "ClusterIP":
            self.f.block(
                "invalid_service",
                f"Service type {kind!r} is not supported",
                subject=subject,
                path=f"{path}.type",
            )
            return
        for key in spec:
            if key not in (
                "type",
                "selector",
                "ports",
                "clusterIP",
                "clusterIPs",
                "sessionAffinity",
                "ipFamilyPolicy",
                "ipFamilies",
                "publishNotReadyAddresses",
                "internalTrafficPolicy",
            ):
                self.f.info(
                    "ignored_setting",
                    f"spec.{key} is ignored",
                    subject=subject,
                    path=f"{path}.{key}",
                )
        headless = spec.get("clusterIP") == "None"
        selector = check_labels(
            spec.get("selector"), subject, self.f, f"{path}.selector"
        )
        if not selector:
            self.f.block(
                "service_without_selector",
                "Services without a selector are not supported (their endpoints would "
                "be managed by hand)",
                subject=subject,
                path=f"{path}.selector",
            )
            return
        ports = []
        for i, p in enumerate(spec.get("ports") or []):
            if (
                not isinstance(p, dict)
                or not isinstance(p.get("port"), int)
                or not (1 <= p["port"] <= 65535)
            ):
                self.f.block(
                    "invalid_port",
                    "port must be 1-65535",
                    subject=subject,
                    path=f"{path}.ports[{i}]",
                )
                continue
            target = p.get("targetPort", p["port"])
            if not (isinstance(target, int) and 1 <= target <= 65535) and not (
                isinstance(target, str) and target.isalnum() and len(target) <= 15
            ):
                self.f.block(
                    "invalid_port",
                    "Invalid targetPort",
                    subject=subject,
                    path=f"{path}.ports[{i}]",
                )
                continue
            protocol = p.get("protocol", "TCP")
            if protocol not in ("TCP", "UDP"):
                self.f.block(
                    "invalid_port",
                    f"Protocol {protocol!r} is not supported",
                    subject=subject,
                    path=f"{path}.ports[{i}]",
                )
                continue
            port_name = p.get("name") if isinstance(p.get("name"), str) else None
            ports.append(
                ServicePortSpec(
                    name=port_name,
                    port=p["port"],
                    target_port=target,
                    protocol=protocol,
                )
            )
        if not ports and not headless:
            self.f.block(
                "invalid_service",
                "A Service needs at least one port",
                subject=subject,
                path=f"{path}.ports",
            )
            return
        self.services.append(
            (
                ServiceSpec(name=name, workload="", headless=headless, ports=ports),
                selector,
                subject,
            )
        )

    def link(self) -> list[ServiceSpec]:
        """Each Service must select the Pods of exactly one imported workload."""
        out = []
        for service, selector, subject in self.services:
            matches = [
                w.name
                for w, _ in self.workloads
                if all(w.labels.get(k) == v for k, v in selector.items())
            ]
            if len(matches) != 1:
                self.f.block(
                    "service_selector_unmatched"
                    if not matches
                    else "service_selector_ambiguous",
                    "The selector matches no imported workload"
                    if not matches
                    else f"The selector matches several workloads ({', '.join(matches)})",
                    subject=subject,
                    hint="Each Service must select the Pods of exactly one Deployment or "
                    "StatefulSet in the file.",
                )
                continue
            service.workload = matches[0]
            out.append(service)
        names = [s.name for s in out]
        for w, _ in self.workloads:
            if w.kind == "StatefulSet" and w.service_name not in names:
                self.f.block(
                    "statefulset_service_missing",
                    f"serviceName {w.service_name!r} is not a Service in the file",
                    subject=f"StatefulSet {w.name}",
                )
        return out


def _d(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _bounded(value: Any, low: int, high: int, default: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        return default
    return min(max(value, low), high)


def _grace(value: Any) -> int | None:
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    return min(max(value, 0), 120)


def parse_manifests(text: str) -> tuple[ImportSpec | None, Findings]:
    findings = Findings()
    try:
        documents = load_documents(text)
    except YamlInputError as exc:
        findings.block("invalid_yaml", str(exc))
        return None, findings
    parser = _Manifests(findings)
    objects = parser.objects(documents)
    if not objects:
        findings.block("no_objects", "The file contains no Kubernetes objects")
        return None, findings
    for where, obj in objects:
        parser.object(where, obj)
    seen: set[tuple[str, str]] = set()
    for w, _ in parser.workloads:
        if ("workload", w.name) in seen:
            findings.block("duplicate_name", f"Two workloads are named {w.name!r}")
        seen.add(("workload", w.name))
    if len(parser.workloads) > MAX_WORKLOADS:
        findings.block("too_many_workloads", f"More than {MAX_WORKLOADS} workloads")
        return None, findings
    services = parser.link()
    if len({s.name for s in services}) != len(services):
        findings.block("duplicate_name", "Two Services have the same name")
    if not parser.workloads:
        findings.block("no_workloads", "No Deployment or StatefulSet to deploy")
        return None, findings
    return (
        ImportSpec(
            source="manifests",
            workloads=[w for w, _ in parser.workloads],
            services=services,
        ),
        findings,
    )
