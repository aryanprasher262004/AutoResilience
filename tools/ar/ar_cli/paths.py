"""Where things live: the repository (manifests, compose.yaml) and the local state home."""

import os
import re
from dataclasses import dataclass
from pathlib import Path

PROJECT = "autoresilience"
CONTEXT_PREFIX = "kind-"
ENGINE_NAMESPACE = "autoresilience-system"
ENGINE_SERVICE_ACCOUNT = "autoresilience-engine"
ENGINE_TOKEN_SECRET = "autoresilience-engine-token"
# Deploys imported applications (P7); a separate identity from the engine's.
PROVISIONER_SERVICE_ACCOUNT = "autoresilience-provisioner"
PROVISIONER_TOKEN_SECRET = "autoresilience-provisioner-token"
# Both labels on every object tools/ar creates; cleanup deletes only objects with both.
OWNER_SELECTOR = "app.kubernetes.io/managed-by=autoresilience,autoresilience.io/owner=local-manager"
DATA_VOLUME = "autoresilience-data"
DEFAULT_WEB_PORT = 3000
DEFAULT_API_PORT = 8000
PROMETHEUS_HOST_PORT = 9090  # infra/kind/cluster.yaml


@dataclass(frozen=True)
class Paths:
    root: Path
    home: Path

    @property
    def state(self) -> Path:
        return self.home / "state.json"

    @property
    def stack_env(self) -> Path:
        return self.home / "stack.env"

    @property
    def kubeconfig(self) -> Path:
        return self.home / "engine.kubeconfig"

    @property
    def provisioner_kubeconfig(self) -> Path:
        """The identity that deploys imported applications (infra/rbac/provisioner.yaml)."""
        return self.home / "provisioner.kubeconfig"

    @property
    def backups(self) -> Path:
        return self.home / "backups"

    @property
    def helm(self) -> Path:
        """Helm repository config and cache used by `ar`, kept apart from the user's own."""
        return self.home / "helm"

    @property
    def compose_file(self) -> Path:
        return self.root / "compose.yaml"

    def manifest(self, relative: str) -> Path:
        return self.root / relative


def default_paths() -> Paths:
    root = Path(__file__).resolve().parents[3]
    home = Path(os.environ.get("AUTORESILIENCE_HOME") or Path.home() / ".autoresilience")
    return Paths(root=root, home=home)


@dataclass(frozen=True)
class Versions:
    cluster_name: str
    prometheus_chart: str
    litmus_core_chart: str
    litmus: str
    loadgen_image: str
    chaos_namespaces: tuple[str, ...]

    @property
    def context(self) -> str:
        return CONTEXT_PREFIX + self.cluster_name

    @property
    def node(self) -> str:
        return f"{self.cluster_name}-control-plane"


_NAME = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")
_VERSION = re.compile(r"^[0-9A-Za-z.+-]+$")
_IMAGE = re.compile(r"^[a-z0-9./:_-]+$")


def parse_env_file(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def load_versions(paths: Paths) -> Versions:
    """infra/versions.env, validated so it can only ever contain plain names/versions."""
    raw = parse_env_file((paths.root / "infra" / "versions.env").read_text())
    versions = Versions(
        cluster_name=raw["CLUSTER_NAME"],
        prometheus_chart=raw["PROMETHEUS_CHART_VERSION"],
        litmus_core_chart=raw["LITMUS_CORE_CHART_VERSION"],
        litmus=raw["LITMUS_VERSION"],
        loadgen_image=raw["LOADGEN_IMAGE"],
        chaos_namespaces=tuple(raw["CHAOS_NAMESPACES"].split()),
    )
    if versions.cluster_name != PROJECT:
        raise ValueError("tools/ar only manages the cluster named 'autoresilience'")
    for name in versions.chaos_namespaces:
        if not _NAME.match(name):
            raise ValueError(f"invalid namespace in versions.env: {name!r}")
    for version in (versions.prometheus_chart, versions.litmus_core_chart, versions.litmus):
        if not _VERSION.match(version):
            raise ValueError(f"invalid version in versions.env: {version!r}")
    if not _IMAGE.match(versions.loadgen_image):
        raise ValueError(f"invalid image in versions.env: {versions.loadgen_image!r}")
    return versions
