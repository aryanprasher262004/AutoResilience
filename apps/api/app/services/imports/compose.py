"""Docker Compose subset -> normalized ImportSpec (pure, never executes anything).

Supported per service: image, command, entrypoint, working_dir, ports, expose,
deploy.replicas / scale, deploy.resources, healthcheck, depends_on, networks, named
or anonymous volumes (as emptyDir), read_only, environment/env_file (names only).
Everything else is reported: ignored with a reason, or blocking when ignoring it
would change what runs or weaken isolation (build, privileged, host paths, ...).
Nothing referenced by the file (.env, env_file, build context, bind sources) is read.
"""

import re
import shlex
from typing import Any

from app.schemas.imports import (
    DeclaredRelation,
    ImportSpec,
    PortSpec,
    ProbeSpec,
    ServicePortSpec,
    ServiceSpec,
    VolumeSpec,
    WorkloadSpec,
)
from app.services.imports.common import (
    INTERPOLATION,
    MAX_PORTS,
    MAX_REPLICAS,
    MAX_WORKLOADS,
    Findings,
    check_image,
    check_name,
    check_strings,
    env_names,
    resources,
)
from app.services.imports.safe_yaml import YamlInputError, load_documents

TOP_LEVEL_SUPPORTED = {"services", "networks", "volumes", "name", "version"}
SUPPORTED_KEYS = [
    "image",
    "command",
    "entrypoint",
    "working_dir",
    "ports",
    "expose",
    "deploy",
    "scale",
    "healthcheck",
    "depends_on",
    "networks",
    "volumes",
    "read_only",
    "environment",
    "env_file",
]
# Ignored, with the reason shown as info.
IGNORED_KEYS = {
    "container_name": "Kubernetes names Pods itself; the service name is used",
    "hostname": "Pods get their own hostnames; reach services by service name",
    "restart": "Kubernetes always restarts failed containers of a Deployment",
    "labels": "Container labels are not copied; the import adds its own labels",
    "logging": "Logs are read from Kubernetes (kubectl logs)",
    "stop_signal": "Kubernetes sends SIGTERM",
    "stop_grace_period": "The Pod's default termination grace period is used",
    "init": "Not translated",
    "platform": "The node's platform is used",
    "pull_policy": "Images are pulled if not present on the node",
    "tty": "Not translated",
    "stdin_open": "Not translated",
    "links": "Every service is reachable by its service name in the namespace",
    "profiles": "",  # handled separately
}
# Ignoring these could hide a problem the user needs to know about.
WARN_KEYS = {
    "dns": "Cluster DNS is used",
    "dns_search": "Cluster DNS is used",
    "extra_hosts": "Host entries are not added; services resolve through cluster DNS",
    "ulimits": "Not translated; the container runtime's defaults apply",
    "user": "The image's own user is used",
    "domainname": "Not translated",
    "mac_address": "Not translated",
    "shm_size": "Not translated",
    "tmpfs": "Not translated; use a volume instead",
}
# Never deployed: they need host access, extra privileges, or code the import won't run.
BLOCKING_KEYS = {
    "build": (
        (
            "Building images is not supported: source code is never built or run "
            "during import"
        ),
        "Build and push the image yourself, then reference it with `image:`.",
    ),
    "privileged": (
        "Privileged containers are never deployed",
        "Remove `privileged: true`.",
    ),
    "cap_add": ("Added Linux capabilities are not allowed", "Remove `cap_add`."),
    "devices": ("Host devices are never mapped", "Remove `devices`."),
    "network_mode": (
        "Host or shared network namespaces are not supported",
        "Remove `network_mode`; services share the import's namespace network.",
    ),
    "pid": ("Sharing the host PID namespace is not allowed", "Remove `pid`."),
    "ipc": ("Sharing an IPC namespace is not allowed", "Remove `ipc`."),
    "userns_mode": ("User namespace modes are not supported", "Remove `userns_mode`."),
    "uts": ("Sharing the host UTS namespace is not allowed", "Remove `uts`."),
    "cgroup": ("cgroup namespace settings are not supported", "Remove `cgroup`."),
    "cgroup_parent": ("cgroup parents are not supported", "Remove `cgroup_parent`."),
    "security_opt": (
        "Security options (seccomp/AppArmor overrides) are not allowed",
        "Remove `security_opt`; the runtime's default profile is used.",
    ),
    "sysctls": ("Kernel parameters (sysctls) are not allowed", "Remove `sysctls`."),
    "group_add": ("Extra groups are not supported", "Remove `group_add`."),
    "runtime": ("Alternative container runtimes are not supported", None),
    "gpus": ("GPUs are not supported", None),
    "volumes_from": (
        "Sharing another container's volumes is not supported",
        "Use a named volume instead (it becomes an empty, per-Pod directory).",
    ),
    "extends": (
        "`extends` would read another file, which imports never do",
        "Inline the extended configuration.",
    ),
    "secrets": (
        "Secrets are never imported: no credentials are read or copied",
        "Remove `secrets`; use non-production test values built into the image.",
    ),
    "configs": (
        "Configs reference host files, which imports never read",
        "Bake the configuration into the image.",
    ),
    "oom_kill_disable": ("Disabling the OOM killer is not allowed", None),
    "oom_score_adj": ("OOM score adjustments are not allowed", None),
    "storage_opt": ("Storage options are not supported", None),
    "isolation": ("Isolation modes are not supported", None),
    "credential_spec": ("Credential specs are not supported", None),
    "external_links": ("Links outside the project are not supported", None),
    "attach": ("Not supported", None),
    "develop": ("Compose Watch (develop) is not supported", None),
    "post_start": ("Lifecycle hooks are not supported", None),
    "pre_stop": ("Lifecycle hooks are not supported", None),
    "models": ("Model runners are not supported", None),
    "provider": ("Compose providers run host code and are not supported", None),
}
_DURATION = re.compile(r"(\d+(?:\.\d+)?)(h|ms|m|s|us|ns)")
_DURATION_SECONDS = {
    "h": 3600.0,
    "m": 60.0,
    "s": 1.0,
    "ms": 0.001,
    "us": 1e-6,
    "ns": 1e-9,
}
_PORT = re.compile(
    r"^(?:(?:\[[0-9a-fA-F:]+\]|\d{1,3}(?:\.\d{1,3}){3}):)?(?:(?P<published>\d+(?:-\d+)?):)?"
    r"(?P<target>\d+(?:-\d+)?)(?:/(?P<protocol>tcp|udp))?$"
)
_COMPOSE_DEFAULTS = {"interval": 30, "timeout": 30, "retries": 3, "start_period": 0}


def _duration(value: Any) -> int | None:
    """Compose duration ("1m30s", "10s") in whole seconds (at least 1)."""
    if isinstance(value, int | float) and not isinstance(value, bool):
        return max(1, round(value))  # compose numbers are seconds here
    if not isinstance(value, str):
        return None
    parts = _DURATION.findall(value.strip())
    if not parts or "".join(n + u for n, u in parts) != value.strip():
        return None
    seconds = sum(float(n) * _DURATION_SECONDS[u] for n, u in parts)
    return max(1, round(seconds))


class _Service:
    def __init__(self, name: str, raw: dict[str, Any], findings: Findings) -> None:
        self.name = name
        self.raw = raw
        self.f = findings
        self.subject = f"service {name}"
        self.base = f"services.{name}"

    def block(self, code: str, message: str, key: str, hint: str | None = None) -> None:
        self.f.block(
            code, message, subject=self.subject, path=f"{self.base}.{key}", hint=hint
        )

    def warn(self, code: str, message: str, key: str, hint: str | None = None) -> None:
        self.f.warn(
            code, message, subject=self.subject, path=f"{self.base}.{key}", hint=hint
        )

    def info(self, code: str, message: str, key: str) -> None:
        self.f.info(code, message, subject=self.subject, path=f"{self.base}.{key}")

    # --- keys ---------------------------------------------------------------------

    def classify_keys(self) -> None:
        for key in self.raw:
            if key in SUPPORTED_KEYS or key == "profiles" or key.startswith("x-"):
                continue
            if key in BLOCKING_KEYS:
                message, hint = BLOCKING_KEYS[key]
                if key == "build" and self.raw.get("image"):
                    self.warn(
                        "build_ignored",
                        "`build` is ignored: the given image is pulled, nothing is built",
                        key,
                    )
                elif key == "privileged" and self.raw[key] is False:
                    continue
                else:
                    self.block(f"unsupported_{key}", message, key, hint)
            elif key in WARN_KEYS:
                self.warn(
                    "ignored_setting", f"`{key}` is ignored: {WARN_KEYS[key]}", key
                )
            elif key in IGNORED_KEYS:
                self.info(
                    "ignored_setting", f"`{key}` is ignored: {IGNORED_KEYS[key]}", key
                )
            else:
                self.block(
                    "unsupported_key",
                    f"`{key}` is not part of the supported Compose subset",
                    key,
                    "Remove it, or see docs/imports.md for what is supported.",
                )

    def ports(self) -> list[PortSpec]:
        out: dict[tuple[int, str], PortSpec] = {}
        published = False
        for key in ("ports", "expose"):
            raw = self.raw.get(key)
            if raw is None:
                continue
            if not isinstance(raw, list):
                self.block("invalid_ports", f"`{key}` must be a list", key)
                continue
            for i, entry in enumerate(raw):
                where = f"{key}[{i}]"
                target, protocol, host = self._port(entry, key == "expose", where)
                if target is None:
                    continue
                published = published or host
                out.setdefault(
                    (target, protocol),
                    PortSpec(
                        container_port=target,
                        protocol=protocol,  # type: ignore[arg-type]
                    ),
                )
        if published:
            self.info(
                "host_port_not_published",
                "Host ports are not published: the service is reachable only inside "
                "the cluster, at <service>:<container port>",
                "ports",
            )
        if len(out) > MAX_PORTS:
            self.block("too_many_ports", f"More than {MAX_PORTS} ports", "ports")
        return sorted(out.values(), key=lambda p: (p.container_port, p.protocol))

    def _port(
        self, entry: Any, expose: bool, where: str
    ) -> tuple[int | None, str, bool]:
        if isinstance(entry, dict):
            target, protocol = entry.get("target"), str(entry.get("protocol", "tcp"))
            host = entry.get("published") is not None
            if entry.get("mode") == "host":
                self.block("host_mode_port", "Host-mode ports bind on the node", where)
                return None, "TCP", False
        elif isinstance(entry, int | str) and not isinstance(entry, bool):
            text = str(entry).strip()
            if INTERPOLATION.search(text):
                self.block(
                    "unresolved_variable",
                    "The port contains a variable (.env files are not read)",
                    where,
                )
                return None, "TCP", False
            match = _PORT.match(text)
            if not match:
                self.block(
                    "invalid_port", f"{text[:40]!r} is not a port mapping", where
                )
                return None, "TCP", False
            # A published (host) range only matters to Docker; it is never published here.
            if "-" in match["target"]:
                self.block(
                    "port_range",
                    "Container port ranges are not supported",
                    where,
                    "List the container ports individually.",
                )
                return None, "TCP", False
            target, protocol = int(match["target"]), match["protocol"] or "tcp"
            host = bool(match["published"]) and not expose
        else:
            self.block("invalid_port", "Not a port mapping", where)
            return None, "TCP", False
        if not isinstance(target, int) or not 1 <= target <= 65535:
            self.block("invalid_port", "The container port must be 1-65535", where)
            return None, "TCP", False
        if protocol not in ("tcp", "udp"):
            self.block("invalid_port", f"Protocol {protocol!r} is not supported", where)
            return None, "TCP", False
        return target, protocol.upper(), host

    def replicas(self) -> int:
        deploy = self.raw.get("deploy") or {}
        if not isinstance(deploy, dict):
            self.block("invalid_deploy", "`deploy` must be a mapping", "deploy")
            return 1
        for key in deploy:
            if key not in ("replicas", "resources", "mode", "restart_policy", "labels"):
                self.warn(
                    "ignored_setting", f"`deploy.{key}` is ignored", f"deploy.{key}"
                )
        if deploy.get("mode") not in (None, "replicated"):
            self.block(
                "unsupported_deploy_mode",
                f"deploy.mode {deploy.get('mode')!r} is not supported",
                "deploy.mode",
                "Use replicated mode with deploy.replicas.",
            )
        value = deploy.get("replicas", self.raw.get("scale", 1))
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            self.block(
                "invalid_replicas",
                "Replicas must be a positive integer",
                "deploy.replicas",
            )
            return 1
        if value > MAX_REPLICAS:
            self.block(
                "too_many_replicas",
                f"{value} replicas; test deployments are limited to {MAX_REPLICAS}",
                "deploy.replicas",
            )
            return MAX_REPLICAS
        return value

    def resources(self) -> Any:
        deploy = (
            self.raw.get("deploy") if isinstance(self.raw.get("deploy"), dict) else {}
        )
        res = deploy.get("resources") or {}  # type: ignore[union-attr]
        if not isinstance(res, dict):
            res = {}

        def pick(section: Any) -> dict[str, Any]:
            section = section if isinstance(section, dict) else {}
            if section.get("devices") or section.get("generic_resources"):
                self.block(
                    "unsupported_resource",
                    "Devices and generic resources are not supported",
                    "deploy.resources",
                )
            out = {}
            if section.get("cpus") is not None:
                out["cpu"] = section["cpus"]
            if section.get("memory") is not None:
                out["memory"] = section["memory"]
            return out

        return resources(
            pick(res.get("limits")),
            pick(res.get("reservations")),
            self.subject,
            self.f,
            f"{self.base}.deploy.resources",
        )

    def healthcheck(self, ports: list[PortSpec]) -> ProbeSpec | None:
        raw = self.raw.get("healthcheck")
        if raw is None or (isinstance(raw, dict) and raw.get("disable") is True):
            tcp = next((p for p in ports if p.protocol == "TCP"), None)
            if tcp is None:
                self.info(
                    "no_health_check",
                    "No health check and no TCP port: the service counts as ready once "
                    "its container runs",
                    "healthcheck",
                )
                return None
            self.info(
                "generated_health_check",
                f"No health check declared: readiness is a TCP connection check on port "
                f"{tcp.container_port} (added by AutoResilience)",
                "healthcheck",
            )
            return ProbeSpec(
                type="tcp",
                port=tcp.container_port,
                period_seconds=5,
                timeout_seconds=2,
                generated=True,
            )
        if not isinstance(raw, dict):
            self.block(
                "invalid_healthcheck", "`healthcheck` must be a mapping", "healthcheck"
            )
            return None
        test = raw.get("test")
        if isinstance(test, str):
            test = ["CMD-SHELL", test]
        if (
            not isinstance(test, list)
            or not test
            or not all(isinstance(t, str) for t in test)
        ):
            self.block(
                "invalid_healthcheck",
                "`healthcheck.test` must be a list",
                "healthcheck.test",
            )
            return None
        if test[0] == "NONE":
            return None
        if test[0] == "CMD":
            command = check_strings(
                test[1:], self.subject, self.f, f"{self.base}.healthcheck.test"
            )
        elif test[0] == "CMD-SHELL" and len(test) == 2:
            command = check_strings(
                ["/bin/sh", "-c", test[1]],
                self.subject,
                self.f,
                f"{self.base}.healthcheck.test",
            )
        else:
            self.block(
                "invalid_healthcheck",
                'healthcheck.test must start with "CMD", "CMD-SHELL" or "NONE"',
                "healthcheck.test",
            )
            return None
        if not command:
            return None
        timing = {}
        for key, default in _COMPOSE_DEFAULTS.items():
            value = raw.get(key, default)
            seconds = value if key == "retries" else _duration(value)
            if key == "start_period" and value == 0:
                seconds = 0
            if not isinstance(seconds, int) or isinstance(seconds, bool) or seconds < 0:
                self.block(
                    "invalid_healthcheck",
                    f"healthcheck.{key} {value!r} is not a duration",
                    f"healthcheck.{key}",
                )
                return None
            timing[key] = seconds
        return ProbeSpec(
            type="exec",
            command=command,
            initial_delay_seconds=min(timing["start_period"], 300),
            period_seconds=min(max(timing["interval"], 1), 300),
            timeout_seconds=min(max(timing["timeout"], 1), 60),
            failure_threshold=min(max(timing["retries"], 1), 10),
        )

    def volumes(self, top_level: dict[str, Any]) -> list[VolumeSpec]:
        raw = self.raw.get("volumes")
        if raw is None:
            return []
        if not isinstance(raw, list):
            self.block("invalid_volumes", "`volumes` must be a list", "volumes")
            return []
        out: list[VolumeSpec] = []
        for i, entry in enumerate(raw):
            where = f"volumes[{i}]"
            source: Any
            target: Any
            if isinstance(entry, str):
                parts = entry.split(":")
                if len(parts) == 1:
                    source, target, mode = None, parts[0], ""
                elif len(parts) in (2, 3):
                    source, target = parts[0], parts[1]
                    mode = parts[2] if len(parts) == 3 else ""
                else:
                    self.block("invalid_volume", "Not a volume mapping", where)
                    continue
                kind = "volume"
                if source is not None and (
                    source.startswith((".", "/", "~", "$"))
                    or "/" in source
                    or "\\" in source
                ):
                    kind = "bind"
                read_only = "ro" in mode.split(",")
            elif isinstance(entry, dict):
                kind = str(entry.get("type", "volume"))
                source, target = entry.get("source"), entry.get("target")
                read_only = entry.get("read_only") is True
            else:
                self.block("invalid_volume", "Not a volume mapping", where)
                continue
            if kind in ("bind", "npipe", "cluster", "image"):
                docker = isinstance(source, str) and "docker.sock" in source
                self.block(
                    "docker_socket" if docker else "host_path_volume",
                    "Mounting the Docker socket would give the container control of "
                    "the host; it is never allowed"
                    if docker
                    else f"Host path {str(source)[:80]!r} is never mounted: imports "
                    "never read or expose host files",
                    where,
                    "Remove it. For scratch data use a named volume (it becomes an "
                    "empty per-Pod directory).",
                )
                continue
            if not isinstance(target, str) or not target.startswith("/"):
                self.block(
                    "invalid_volume", "The mount target must be an absolute path", where
                )
                continue
            if kind not in ("volume", "tmpfs"):
                self.block(
                    "invalid_volume", f"Volume type {kind!r} is not supported", where
                )
                continue
            if source and source not in top_level and kind == "volume":
                self.block(
                    "undeclared_volume",
                    f"Volume {source!r} is not declared under top-level `volumes`",
                    where,
                )
                continue
            out.append(
                VolumeSpec(
                    name=f"vol-{len(out)}",
                    mount_path=target,
                    read_only=read_only,
                    memory=kind == "tmpfs",
                )
            )
            self.warn(
                "ephemeral_volume",
                f"{target} becomes an empty directory per Pod: data is not persisted "
                "and not shared between replicas",
                where,
            )
        return out

    def environment(self) -> list[str]:
        names: list[str] = []
        raw = self.raw.get("environment")
        if isinstance(raw, dict):
            names = [str(k) for k in raw]
        elif isinstance(raw, list):
            names = [str(e).split("=", 1)[0] for e in raw if isinstance(e, str)]
        elif raw is not None:
            self.block(
                "invalid_environment",
                "`environment` must be a list or mapping",
                "environment",
            )
        if self.raw.get("env_file") is not None:
            self.warn(
                "env_file_not_read",
                "env_file is never read: its variables are not set",
                "env_file",
                "Imports never open files on your machine; nothing from it is copied.",
            )
        return env_names(names, self.subject, self.f, f"{self.base}.environment")

    def depends_on(self, services: set[str]) -> list[str]:
        raw = self.raw.get("depends_on")
        if raw is None:
            return []
        names = list(raw) if isinstance(raw, dict) else raw
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            self.block(
                "invalid_depends_on",
                "`depends_on` must be a list or mapping",
                "depends_on",
            )
            return []
        unknown = [n for n in names if n not in services]
        if unknown:
            self.block(
                "unknown_dependency",
                f"Depends on undefined service(s): {', '.join(unknown)}",
                "depends_on",
            )
        if isinstance(raw, dict) and any(
            isinstance(v, dict) and v.get("condition") for v in raw.values()
        ):
            self.info(
                "start_order_not_enforced",
                "Start conditions are not enforced: Kubernetes starts every workload at "
                "once and routes traffic only to ready Pods",
                "depends_on",
            )
        return sorted(n for n in names if n in services)

    def networks(self, declared: set[str]) -> list[str]:
        raw = self.raw.get("networks")
        if raw is None:
            return []
        names = list(raw) if isinstance(raw, dict) else raw
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            self.block(
                "invalid_networks", "`networks` must be a list or mapping", "networks"
            )
            return []
        if isinstance(raw, dict) and any(
            isinstance(v, dict) and (v.get("aliases") or v.get("ipv4_address"))
            for v in raw.values()
        ):
            self.warn(
                "ignored_setting",
                "Network aliases and fixed addresses are ignored; use the service name",
                "networks",
            )
        unknown = [n for n in names if n not in declared and n != "default"]
        if unknown:
            self.block(
                "unknown_network",
                f"Undeclared network(s): {', '.join(unknown)}",
                "networks",
            )
        return sorted(names)


def _split(value: Any, svc: _Service, key: str) -> Any:
    """A string command is split like Compose does (shell-like quoting, no shell)."""
    if not isinstance(value, str):
        return value
    try:
        return shlex.split(value)
    except ValueError:
        svc.block("invalid_command", f"`{key}` has unbalanced quotes", key)
        return None


def parse_compose(text: str) -> tuple[ImportSpec | None, Findings]:
    findings = Findings()
    try:
        documents = load_documents(text, max_documents=1)
    except YamlInputError as exc:
        findings.block("invalid_yaml", str(exc))
        return None, findings
    if len(documents) != 1 or not isinstance(documents[0], dict):
        findings.block(
            "not_compose", "A Compose file is one YAML mapping with a `services` key"
        )
        return None, findings
    doc: dict[str, Any] = documents[0]
    for key in doc:
        if key.startswith("x-"):
            findings.info(
                "extension_ignored", f"Extension field `{key}` is ignored", path=key
            )
        elif key == "include":
            findings.block(
                "unsupported_include",
                "`include` would read other files, which imports never do",
                path=key,
                hint="Merge the included services into this file.",
            )
        elif key in ("secrets", "configs"):
            findings.block(
                f"unsupported_{key}",
                f"Top-level `{key}` reference host files or credentials, which are never "
                "read or copied",
                path=key,
                hint=f"Remove `{key}`; test deployments should not need real credentials.",
            )
        elif key == "version":
            findings.info(
                "obsolete_version", "`version` is obsolete and ignored", path=key
            )
        elif key not in TOP_LEVEL_SUPPORTED:
            findings.block(
                "unsupported_key", f"Top-level `{key}` is not supported", path=key
            )
    services = doc.get("services")
    if not isinstance(services, dict) or not services:
        findings.block("no_services", "The file defines no services", path="services")
        return None, findings
    networks = doc.get("networks") or {}
    volumes = doc.get("volumes") or {}
    if not isinstance(networks, dict) or not isinstance(volumes, dict):
        findings.block("invalid_top_level", "`networks` and `volumes` must be mappings")
        return None, findings
    for name, net in networks.items():
        if isinstance(net, dict) and (
            net.get("external") or net.get("driver") not in (None, "bridge")
        ):
            findings.warn(
                "network_not_translated",
                f"Network {name!r} (external or custom driver) is not created; services "
                "share the import's namespace network",
                path=f"networks.{name}",
            )
    for name, vol in volumes.items():
        if isinstance(vol, dict) and (
            vol.get("external") or vol.get("driver") or vol.get("driver_opts")
        ):
            findings.warn(
                "volume_not_translated",
                f"Volume {name!r}: external volumes and drivers are not used; it becomes "
                "an empty per-Pod directory",
                path=f"volumes.{name}",
            )

    active = {
        n: s
        for n, s in services.items()
        if not (isinstance(s, dict) and s.get("profiles"))
    }
    for n in services:
        if n not in active:
            findings.info(
                "profile_skipped",
                "Has `profiles`, so `docker compose up` skips it by default; not imported",
                subject=f"service {n}",
                path=f"services.{n}.profiles",
            )
    if len(active) > MAX_WORKLOADS:
        findings.block(
            "too_many_services", f"More than {MAX_WORKLOADS} services", path="services"
        )
        return None, findings

    workloads: list[WorkloadSpec] = []
    service_specs: list[ServiceSpec] = []
    declared: list[DeclaredRelation] = []
    names = set(active)
    for raw_name, raw in sorted(active.items()):
        path = f"services.{raw_name}"
        name = check_name(raw_name, "Service", findings, path)
        if name is None:
            continue
        if not isinstance(raw, dict):
            findings.block("invalid_service", "A service must be a mapping", path=path)
            continue
        svc = _Service(name, raw, findings)
        svc.classify_keys()
        image = check_image(raw.get("image"), svc.subject, findings, f"{path}.image")
        ports = svc.ports()
        args = check_strings(
            _split(raw.get("command"), svc, "command"),
            svc.subject,
            findings,
            f"{path}.command",
        )
        command = check_strings(
            _split(raw.get("entrypoint"), svc, "entrypoint"),
            svc.subject,
            findings,
            f"{path}.entrypoint",
        )
        working_dir = raw.get("working_dir")
        if working_dir is not None and (
            not isinstance(working_dir, str) or not working_dir.startswith("/")
        ):
            svc.block(
                "invalid_working_dir",
                "working_dir must be an absolute path",
                "working_dir",
            )
            working_dir = None
        workload = WorkloadSpec(
            name=name,
            image=image or "",
            replicas=svc.replicas(),
            command=command,
            args=args,
            working_dir=working_dir,
            ports=ports,
            readiness=svc.healthcheck(ports),
            resources=svc.resources(),
            volumes=svc.volumes(volumes),
            read_only_root=raw.get("read_only") is True,
            labels={"app.kubernetes.io/name": name},
            selector={"app.kubernetes.io/name": name},
            env_names=svc.environment(),
        )
        workloads.append(workload)
        if ports:
            service_specs.append(
                ServiceSpec(
                    name=name,
                    workload=name,
                    ports=[
                        ServicePortSpec(
                            name=f"{p.protocol.lower()}-{p.container_port}",
                            port=p.container_port,
                            target_port=p.container_port,
                            protocol=p.protocol,
                        )
                        for p in ports
                    ],
                )
            )
        for target in svc.depends_on(names):
            declared.append(
                DeclaredRelation(
                    source=name,
                    target=target,
                    type="depends_on",
                    detail=f"services.{name}.depends_on lists {target} (start order "
                    "only; not proof that they talk to each other)",
                )
            )
        svc.networks(set(networks))
    if not workloads:
        return None, findings
    return (
        ImportSpec(
            source="compose",
            workloads=workloads,
            services=service_specs,
            declared=declared,
            networks=sorted(networks),
        ),
        findings,
    )
