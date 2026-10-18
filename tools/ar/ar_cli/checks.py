"""Read-only environment detection (`ar doctor`): tools, Docker resources and ports.

Statuses follow the safety-check vocabulary: OK, MISSING, INSUFFICIENT, ERROR, plus
CONFLICT for a port another program already uses. Nothing here installs or changes
anything; missing tools are reported with where to get them.
"""

import json
import re
import shutil
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .paths import PROJECT, Versions
from .runner import Runner

OK = "OK"
MISSING = "MISSING"
INSUFFICIENT = "INSUFFICIENT"
CONFLICT = "CONFLICT"
ERROR = "ERROR"

MIN_VERSIONS: dict[str, tuple[int, int]] = {
    "docker": (24, 0),
    "compose": (2, 20),  # depends_on: service_completed_successfully, up --wait
    "kind": (0, 20),
    "kubectl": (1, 28),
    "helm": (3, 12),
}
INSTALL_HINTS = {
    "docker": "Install Docker Desktop (or Docker Engine) and start it: https://docs.docker.com/get-docker/",
    "compose": "Docker Compose v2 ships with Docker Desktop; on Linux install docker-compose-plugin",
    "kind": "https://kind.sigs.k8s.io/docs/user/quick-start/#installation",
    "kubectl": "https://kubernetes.io/docs/tasks/tools/",
    "helm": "https://helm.sh/docs/intro/install/",
}
# Measured on the full stack (kind + Prometheus + Litmus + sample apps + compose stack);
# see docs/local-stack.md "Requirements".
MIN_MEMORY_BYTES = 4 * 1024**3
RECOMMENDED_MEMORY_BYTES = 6 * 1024**3
MIN_CPUS = 2
MIN_FREE_DISK_BYTES = 10 * 1024**3


@dataclass(frozen=True)
class Finding:
    name: str
    status: str
    detail: str
    fix: str | None = None

    @property
    def ok(self) -> bool:
        return self.status == OK


def parse_version(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"v?(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _version_finding(name: str, raw: str) -> Finding:
    version = parse_version(raw)
    minimum = MIN_VERSIONS[name]
    want = ".".join(map(str, minimum))
    if version is None:
        return Finding(name, ERROR, f"could not parse version from {raw.strip()[:80]!r}")
    shown = ".".join(map(str, version))
    if version[:2] < minimum:
        return Finding(name, INSUFFICIENT, f"{shown} < required {want}", INSTALL_HINTS[name])
    return Finding(name, OK, shown)


TOOL_VERSION_ARGV = {
    "kind": ["kind", "version"],
    "kubectl": ["kubectl", "version", "--client"],
    "helm": ["helm", "version", "--short"],
}


def check_tool(runner: Runner, name: str) -> Finding:
    if runner.which(name) is None:
        return Finding(name, MISSING, "not found on PATH", INSTALL_HINTS[name])
    result = runner.run(TOOL_VERSION_ARGV[name], check=False, timeout=20)
    if not result.ok:
        return Finding(name, ERROR, result.stderr.strip()[:200] or "version check failed")
    return _version_finding(name, result.stdout)


@dataclass(frozen=True)
class DockerInfo:
    cpus: int
    memory_bytes: int


def check_docker(runner: Runner) -> tuple[list[Finding], DockerInfo | None]:
    if runner.which("docker") is None:
        return [Finding("docker", MISSING, "not found on PATH", INSTALL_HINTS["docker"])], None
    result = runner.run(["docker", "info", "--format", "{{json .}}"], check=False, timeout=30)
    if not result.ok:
        return [
            Finding(
                "docker",
                ERROR,
                "the Docker daemon is not reachable",
                "Start Docker Desktop (or `sudo systemctl start docker`) and retry",
            )
        ], None
    try:
        info = json.loads(result.stdout)
    except ValueError:
        return [Finding("docker", ERROR, "unexpected `docker info` output")], None
    findings = [_version_finding("docker", str(info.get("ServerVersion", "")))]
    compose = runner.run(["docker", "compose", "version", "--short"], check=False, timeout=20)
    findings.append(
        _version_finding("compose", compose.stdout)
        if compose.ok
        else Finding("compose", MISSING, "`docker compose` is not available", INSTALL_HINTS["compose"])
    )
    docker = DockerInfo(cpus=int(info.get("NCPU") or 0), memory_bytes=int(info.get("MemTotal") or 0))
    findings += check_resources(docker)
    return findings, docker


def _gib(value: int) -> str:
    return f"{value / 1024**3:.1f} GiB"


def check_resources(info: DockerInfo) -> list[Finding]:
    fix = "Raise the limits in Docker Desktop → Settings → Resources"
    memory = (
        Finding("docker memory", INSUFFICIENT, f"{_gib(info.memory_bytes)} < required {_gib(MIN_MEMORY_BYTES)}", fix)
        if info.memory_bytes < MIN_MEMORY_BYTES
        else Finding(
            "docker memory",
            OK,
            _gib(info.memory_bytes)
            + (
                ""
                if info.memory_bytes >= RECOMMENDED_MEMORY_BYTES
                else f" (recommended {_gib(RECOMMENDED_MEMORY_BYTES)})"
            ),
        )
    )
    cpus = (
        Finding("docker cpus", INSUFFICIENT, f"{info.cpus} < required {MIN_CPUS}", fix)
        if info.cpus < MIN_CPUS
        else Finding("docker cpus", OK, str(info.cpus))
    )
    return [memory, cpus]


def check_disk(path: Path) -> Finding:
    probe = path
    while not probe.exists():
        probe = probe.parent
    free = shutil.disk_usage(probe).free
    if free < MIN_FREE_DISK_BYTES:
        return Finding(
            "disk",
            INSUFFICIENT,
            f"{_gib(free)} free < required {_gib(MIN_FREE_DISK_BYTES)}",
            "Free disk space (images, cluster and backups need about 10 GiB)",
        )
    return Finding("disk", OK, f"{_gib(free)} free")


def port_in_use(port: int, host: str = "127.0.0.1") -> bool:
    """Something listens (connect succeeds) or the address cannot be bound."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) == 0:
            return True
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as bind:
        try:
            bind.bind((host, port))
        except OSError:
            return True
    return False


def owned_ports(runner: Runner, versions: Versions) -> set[int]:
    """Host ports published by this project's containers (compose stack, kind node)."""
    ports: set[int] = set()
    for label in (f"com.docker.compose.project={PROJECT}", f"io.x-k8s.kind.cluster={versions.cluster_name}"):
        result = runner.run(["docker", "ps", "--filter", f"label={label}", "--format", "{{.Ports}}"], check=False)
        ports |= {int(p) for p in re.findall(r":(\d+)->", result.stdout)}
    return ports


def check_ports(ports: Iterable[tuple[str, int, str]], owned: set[int]) -> list[Finding]:
    findings = []
    for name, port, fix in ports:
        if port in owned:
            findings.append(Finding(f"port {port}", OK, f"{name}: in use by AutoResilience"))
        elif port_in_use(port):
            findings.append(Finding(f"port {port}", CONFLICT, f"{name}: already in use by another program", fix))
        else:
            findings.append(Finding(f"port {port}", OK, f"{name}: free"))
    return findings
