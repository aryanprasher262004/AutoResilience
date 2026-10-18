"""The owned kind cluster: create, verify, provision, grant/revoke engine access.

Provisioning is the scripts/dev-cluster.sh sequence (same manifests, values and pinned
versions from infra/versions.env), runs with the operator's host credentials, and
always passes an explicit `--context kind-autoresilience` after verifying that the
context really points at this cluster's node. The engine never gets these credentials:
it gets a ServiceAccount kubeconfig (engine_kubeconfig) limited by infra/rbac/.
"""

import base64
import hashlib
import json
import os
import re
import time
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .paths import (
    ENGINE_NAMESPACE,
    ENGINE_SERVICE_ACCOUNT,
    ENGINE_TOKEN_SECRET,
    OWNER_SELECTOR,
    PROMETHEUS_HOST_PORT,
    PROVISIONER_SERVICE_ACCOUNT,
    PROVISIONER_TOKEN_SECRET,
    Paths,
    Versions,
)
from .runner import Runner
from .state import write_private

Log = Callable[[str], None]


class OwnershipError(Exception):
    """The context does not point at the cluster this tool manages."""


@dataclass(frozen=True)
class ClusterStatus:
    exists: bool
    running: bool


def cluster_status(runner: Runner, versions: Versions) -> ClusterStatus:
    clusters = runner.run(["kind", "get", "clusters"], check=False)
    exists = versions.cluster_name in clusters.stdout.split()
    running = False
    if exists:
        inspect = runner.run(["docker", "inspect", "-f", "{{.State.Running}}", versions.node], check=False)
        running = inspect.stdout.strip() == "true"
    return ClusterStatus(exists=exists, running=running)


def kubectl(versions: Versions, *args: str) -> list[str]:
    return ["kubectl", "--context", versions.context, *args]


def verify_owned(runner: Runner, versions: Versions) -> None:
    """Before any write: the explicit context must reach exactly this kind cluster."""
    result = runner.run(
        kubectl(versions, "get", "nodes", "-o", "jsonpath={.items[*].metadata.name}"),
        check=False,
        timeout=30,
    )
    if not result.ok:
        raise OwnershipError(
            f"Context {versions.context} is not reachable ({result.stderr.strip()[:200]}). "
            "Is the cluster running? Try `ar start`."
        )
    nodes = result.stdout.split()
    prefix = f"{versions.cluster_name}-"
    if versions.node not in nodes or any(not n.startswith(prefix) for n in nodes):
        raise OwnershipError(
            f"Context {versions.context} points at nodes {nodes}, not kind cluster "
            f"{versions.cluster_name!r}; refusing to change it."
        )


def create_cluster(runner: Runner, paths: Paths) -> None:
    runner.stream(
        ["kind", "create", "cluster", "--config", str(paths.manifest("infra/kind/cluster.yaml")), "--wait", "120s"]
    )


def start_node(runner: Runner, versions: Versions) -> None:
    """Restart a stopped kind node (e.g. after a Docker restart). Only the labelled node."""
    label = runner.run(
        ["docker", "inspect", "-f", '{{index .Config.Labels "io.x-k8s.kind.cluster"}}', versions.node], check=False
    )
    if label.stdout.strip() != versions.cluster_name:
        raise OwnershipError(f"Container {versions.node} is not a node of kind cluster {versions.cluster_name!r}")
    runner.run(["docker", "start", versions.node])


def stop_node(runner: Runner, versions: Versions) -> None:
    label = runner.run(
        ["docker", "inspect", "-f", '{{index .Config.Labels "io.x-k8s.kind.cluster"}}', versions.node], check=False
    )
    if label.stdout.strip() == versions.cluster_name:
        runner.run(["docker", "stop", versions.node], timeout=120)


def wait_api_server(
    runner: Runner, versions: Versions, timeout: float = 120, sleep: Callable[[float], None] = time.sleep
) -> None:
    deadline = time.monotonic() + timeout
    while True:
        if runner.run(kubectl(versions, "get", "--raw", "/readyz"), check=False, timeout=15).ok:
            return
        if time.monotonic() > deadline:
            raise OwnershipError(f"The Kubernetes API of {versions.context} did not become ready in {timeout:.0f}s")
        sleep(3)


def for_namespace(manifest: str, namespace: str) -> str:
    """Re-target a manifest written for `shop` (same rule as dev-cluster.sh's sed)."""
    return re.sub(r"namespace: shop$", f"namespace: {namespace}", manifest, flags=re.MULTILINE)


def helm_env(paths: Paths) -> dict[str, str]:
    """Helm with its repository list and cache under ~/.autoresilience/helm.

    `helm repo add/update` would otherwise rewrite the user's own repositories.yaml.
    """
    return {
        **os.environ,
        "HELM_REPOSITORY_CONFIG": str(paths.helm / "repositories.yaml"),
        "HELM_REPOSITORY_CACHE": str(paths.helm / "cache"),
    }


def provision(runner: Runner, paths: Paths, versions: Versions, log: Log) -> None:
    """Sample apps, Prometheus, LitmusChaos and chaos RBAC (idempotent)."""
    verify_owned(runner, versions)
    m = paths.manifest
    helm = helm_env(paths)
    log("Sample workloads (shop, resilience-sandbox)")
    for manifest in ("infra/sample-app/shop.yaml", "infra/sample-app/sandbox.yaml"):
        runner.run(kubectl(versions, "apply", "-f", str(m(manifest))))
    script = m("infra/sample-app/loadgen/loadgen.py")
    configmap = runner.run(
        kubectl(
            versions,
            "-n",
            "shop",
            "create",
            "configmap",
            "loadgen-script",
            f"--from-file=loadgen.py={script}",
            "--dry-run=client",
            "-o",
            "yaml",
        )
    )
    runner.run(kubectl(versions, "apply", "-f", "-"), input=configmap.stdout_bytes)
    # Restart loadgen only when the script changed (checksum annotation).
    digest = hashlib.sha256(script.read_bytes()).hexdigest()[:16]
    patch = {"spec": {"template": {"metadata": {"annotations": {"autoresilience.io/script-sha": digest}}}}}
    runner.run(
        kubectl(versions, "-n", "shop", "patch", "deployment", "loadgen", "--type", "merge", "-p", json.dumps(patch))
    )

    log(f"Prometheus (chart {versions.prometheus_chart})")
    runner.run(
        [
            "helm",
            "repo",
            "add",
            "prometheus-community",
            "https://prometheus-community.github.io/helm-charts",
            "--force-update",
        ],
        env=helm,
    )
    runner.run(["helm", "repo", "update", "prometheus-community"], timeout=300, env=helm)
    runner.stream(
        [
            "helm",
            "upgrade",
            "--install",
            "prometheus",
            "prometheus-community/prometheus",
            "--kube-context",
            versions.context,
            "--namespace",
            "monitoring",
            "--create-namespace",
            "--version",
            versions.prometheus_chart,
            "--values",
            str(m("monitoring/prometheus/values.yaml")),
            "--wait",
            "--timeout",
            "5m",
        ],
        env=helm,
    )

    log(f"LitmusChaos (litmus-core {versions.litmus_core_chart}); pre-pulling images in the node")
    images = [versions.loadgen_image] + [
        f"litmuschaos.docker.scarf.sh/litmuschaos/{name}:{versions.litmus}"
        for name in ("chaos-operator", "chaos-runner", "go-runner")
    ]
    for image in images:
        runner.run(["docker", "exec", versions.node, "crictl", "pull", image], timeout=900)
    runner.run(
        ["helm", "repo", "add", "litmuschaos", "https://litmuschaos.github.io/litmus-helm/", "--force-update"],
        env=helm,
    )
    runner.run(["helm", "repo", "update", "litmuschaos"], timeout=300, env=helm)
    runner.stream(
        [
            "helm",
            "upgrade",
            "--install",
            "litmus",
            "litmuschaos/litmus-core",
            "--kube-context",
            versions.context,
            "--namespace",
            "litmus",
            "--create-namespace",
            "--version",
            versions.litmus_core_chart,
            "--values",
            str(m("chaos/litmus/values.yaml")),
            "--wait",
            "--timeout",
            "5m",
        ],
        env=helm,
    )
    rbac = m("chaos/rbac/pod-delete-rbac.yaml").read_text()
    for namespace in versions.chaos_namespaces:
        runner.run(kubectl(versions, "-n", namespace, "apply", "-f", str(m("chaos/templates/pod-delete.yaml"))))
        runner.run(kubectl(versions, "apply", "-f", "-"), input=for_namespace(rbac, namespace).encode())

    log("Waiting for workloads to roll out")
    for workload in ("deployment/frontend", "deployment/checkout", "deployment/loadgen", "statefulset/cart-redis"):
        runner.run(kubectl(versions, "-n", "shop", "rollout", "status", workload, "--timeout=180s"), timeout=200)
    runner.run(
        kubectl(versions, "-n", "resilience-sandbox", "rollout", "status", "deployment/fragile", "--timeout=180s"),
        timeout=200,
    )
    wait_http(f"http://127.0.0.1:{PROMETHEUS_HOST_PORT}/-/ready", 60, "Prometheus")


def wait_http(url: str, timeout: float, name: str, sleep: Callable[[float], None] = time.sleep) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            with urllib.request.urlopen(url, timeout=3):
                return
        except OSError:
            if time.monotonic() > deadline:
                raise OwnershipError(f"{name} not reachable at {url} after {timeout:.0f}s") from None
            sleep(2)


# --- engine runtime identity ------------------------------------------------------

ENGINE_USER = f"system:serviceaccount:{ENGINE_NAMESPACE}:{ENGINE_SERVICE_ACCOUNT}"


def wait_namespace_gone_or_active(
    runner: Runner, versions: Versions, timeout: float = 180, sleep: Callable[[float], None] = time.sleep
) -> None:
    """A just-revoked engine namespace may still be terminating; applying into it would fail."""
    deadline = time.monotonic() + timeout
    while True:
        phase = runner.run(
            kubectl(
                versions, "get", "namespace", ENGINE_NAMESPACE, "-o", "jsonpath={.status.phase}", "--ignore-not-found"
            ),
            check=False,
        ).stdout.strip()
        if phase != "Terminating":
            return
        if time.monotonic() > deadline:
            raise OwnershipError(f"Namespace {ENGINE_NAMESPACE} is still terminating after {timeout:.0f}s; retry later")
        sleep(3)


def grant_engine_access(runner: Runner, paths: Paths, versions: Versions) -> None:
    """The engine's identity, and the separate provisioner identity for imports (P7)."""
    verify_owned(runner, versions)
    wait_namespace_gone_or_active(runner, versions)
    runner.run(kubectl(versions, "apply", "-f", str(paths.manifest("infra/rbac/engine-rbac.yaml"))))
    runner.run(kubectl(versions, "apply", "-f", str(paths.manifest("infra/rbac/provisioner.yaml"))))
    role = paths.manifest("infra/rbac/engine-chaos-role.yaml").read_text()
    for namespace in versions.chaos_namespaces:
        runner.run(kubectl(versions, "apply", "-f", "-"), input=for_namespace(role, namespace).encode())


def read_token(
    runner: Runner,
    versions: Versions,
    attempts: int = 30,
    sleep: Callable[[float], None] = time.sleep,
    secret: str = ENGINE_TOKEN_SECRET,
) -> tuple[str, str]:
    """(token, base64 CA) from the ServiceAccount token Secret, once the controller filled it."""
    for _ in range(attempts):
        result = runner.run(
            kubectl(versions, "-n", ENGINE_NAMESPACE, "get", "secret", secret, "-o", "json"), check=False
        )
        if result.ok:
            data = json.loads(result.stdout).get("data") or {}
            if data.get("token") and data.get("ca.crt"):
                return base64.b64decode(data["token"]).decode(), data["ca.crt"]
        sleep(1)
    raise OwnershipError(f"Secret {ENGINE_NAMESPACE}/{secret} has no token yet")


@dataclass(frozen=True)
class KubeconfigEntry:
    """One context of the engine's kubeconfig: server, CA and a ServiceAccount token."""

    context: str
    user: str
    server: str
    ca_b64: str
    token: str


def engine_kubeconfig(versions: Versions, token: str, ca_b64: str, extra: Sequence[KubeconfigEntry] = ()) -> str:
    """Kubeconfig for the engine container: ServiceAccount tokens only, no operator credentials.

    The owned cluster (KUBE_CONTEXT) is reached in-network; `extra` are imported clusters
    (read-only discovery, `ar cluster import`).
    """
    owned = KubeconfigEntry(
        versions.context,
        ENGINE_SERVICE_ACCOUNT,
        # The control-plane container on the `kind` Docker network (its cert covers this name).
        f"https://{versions.node}:6443",
        ca_b64,
        token,
    )
    entries = [owned, *extra]
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {"name": e.context, "cluster": {"server": e.server, "certificate-authority-data": e.ca_b64}}
            for e in entries
        ],
        "users": [{"name": e.user, "user": {"token": e.token}} for e in entries],
        "contexts": [{"name": e.context, "context": {"cluster": e.context, "user": e.user}} for e in entries],
        "current-context": versions.context,
    }
    return json.dumps(config, indent=2) + "\n"  # JSON is valid YAML


def kubeconfig_entries(path: Path) -> dict[str, KubeconfigEntry]:
    """The entries of an engine kubeconfig written by this tool, by context ({} if absent)."""
    try:
        config = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    clusters = {c["name"]: c["cluster"] for c in config.get("clusters", [])}
    users = {u["name"]: u["user"] for u in config.get("users", [])}
    entries = {}
    for ctx in config.get("contexts", []):
        name, ref = ctx["name"], ctx["context"]
        cluster, user = clusters[ref["cluster"]], users[ref["user"]]
        entries[name] = KubeconfigEntry(
            name, ref["user"], cluster["server"], cluster["certificate-authority-data"], user["token"]
        )
    return entries


def write_engine_kubeconfig(
    runner: Runner, paths: Paths, versions: Versions, imported: Sequence[str] = (), add: Sequence[KubeconfigEntry] = ()
) -> bool:
    """(Re)write the engine kubeconfig; True if its content changed.

    Imported contexts listed in `imported` keep their existing entries (their tokens are
    only obtainable from those clusters); `add` replaces or adds entries.
    """
    token, ca = read_token(runner, versions)
    existing = kubeconfig_entries(paths.kubeconfig)
    keep = {name: existing[name] for name in imported if name in existing}
    keep.update({e.context: e for e in add})
    content = engine_kubeconfig(versions, token, ca, [keep[name] for name in sorted(keep)])
    before = paths.kubeconfig.read_text() if paths.kubeconfig.exists() else None
    write_private(paths.kubeconfig, content)
    return content != before


def write_provisioner_kubeconfig(runner: Runner, paths: Paths, versions: Versions) -> bool:
    """The provisioner's kubeconfig (its ServiceAccount token only); True if it changed.

    Kept apart from the engine's kubeconfig: the engine's own identity can never deploy,
    and this one can only write inside import namespaces (infra/rbac/provisioner.yaml).
    """
    token, ca = read_token(runner, versions, secret=PROVISIONER_TOKEN_SECRET)
    entry = KubeconfigEntry(versions.context, PROVISIONER_SERVICE_ACCOUNT, f"https://{versions.node}:6443", ca, token)
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [{"name": entry.context, "cluster": {"server": entry.server, "certificate-authority-data": ca}}],
        "users": [{"name": entry.user, "user": {"token": token}}],
        "contexts": [{"name": entry.context, "context": {"cluster": entry.context, "user": entry.user}}],
        "current-context": entry.context,
    }
    content = json.dumps(config, indent=2) + "\n"
    path = paths.provisioner_kubeconfig
    before = path.read_text() if path.exists() else None
    write_private(path, content)
    return content != before


@dataclass(frozen=True)
class Permission:
    verb: str
    resource: str
    namespace: str | None  # None: all namespaces
    expected: bool


def expected_permissions(versions: Versions) -> list[Permission]:
    chaos = versions.chaos_namespaces[0]
    return [
        Permission("list", "deployments.apps", None, True),
        Permission("list", "statefulsets.apps", None, True),
        Permission("list", "pods", None, True),
        # Topology view (read-only).
        Permission("list", "replicasets.apps", None, True),
        Permission("list", "services", None, True),
        Permission("list", "endpointslices.discovery.k8s.io", None, True),
        Permission("list", "events", None, True),
        Permission("list", "nodes", None, True),
        Permission("list", "namespaces", None, True),
        Permission("create", "chaosengines.litmuschaos.io", chaos, True),
        Permission("delete", "chaosresults.litmuschaos.io", chaos, True),
        # Must stay denied: no workload writes, no pod deletion, no secrets or config
        # data, no chaos outside prepared namespaces, no RBAC changes.
        Permission("create", "deployments.apps", chaos, False),
        Permission("delete", "pods", chaos, False),
        Permission("get", "secrets", chaos, False),
        Permission("list", "secrets", None, False),
        Permission("list", "configmaps", None, False),
        Permission("delete", "services", chaos, False),
        Permission("create", "chaosengines.litmuschaos.io", "default", False),
        Permission("create", "rolebindings.rbac.authorization.k8s.io", chaos, False),
    ]


PROVISIONER_USER = f"system:serviceaccount:{ENGINE_NAMESPACE}:{PROVISIONER_SERVICE_ACCOUNT}"


def expected_provisioner_permissions(versions: Versions) -> list[Permission]:
    """RBAC only: writes are further confined to import namespaces by the admission policy."""
    chaos = versions.chaos_namespaces[0]
    return [
        Permission("create", "namespaces", None, True),
        Permission("create", "rolebindings.rbac.authorization.k8s.io", chaos, True),
        # Never outside an import namespace (it binds its writer role only there).
        Permission("create", "deployments.apps", chaos, False),
        Permission("delete", "pods", chaos, False),
        Permission("get", "secrets", chaos, False),
        Permission("list", "configmaps", None, False),
        Permission("create", "chaosengines.litmuschaos.io", chaos, False),
        Permission("create", "clusterrolebindings.rbac.authorization.k8s.io", None, False),
    ]


def check_engine_permissions(
    runner: Runner, versions: Versions, provisioner: bool = False
) -> list[tuple[Permission, bool]]:
    """(permission, actual) via `kubectl auth can-i --as` the engine's (or provisioner's) ServiceAccount."""
    user = PROVISIONER_USER if provisioner else ENGINE_USER
    wanted = expected_provisioner_permissions(versions) if provisioner else expected_permissions(versions)
    results = []
    for p in wanted:
        scope = ["--all-namespaces"] if p.namespace is None else ["-n", p.namespace]
        out = runner.run(kubectl(versions, "auth", "can-i", p.verb, p.resource, *scope, "--as", user), check=False)
        results.append((p, out.stdout.strip() == "yes"))
    return results


def revoke_engine_access(runner: Runner, versions: Versions) -> None:
    """Delete only objects carrying both ownership labels (the engine's identity)."""
    verify_owned(runner, versions)
    runner.run(
        kubectl(
            versions,
            "delete",
            "validatingadmissionpolicybinding,validatingadmissionpolicy",
            "-l",
            OWNER_SELECTOR,
            "--ignore-not-found",
        )
    )
    runner.run(
        kubectl(versions, "delete", "clusterrolebinding,clusterrole", "-l", OWNER_SELECTOR, "--ignore-not-found")
    )
    for namespace in versions.chaos_namespaces:
        runner.run(
            kubectl(versions, "-n", namespace, "delete", "rolebinding,role", "-l", OWNER_SELECTOR, "--ignore-not-found")
        )
    runner.run(kubectl(versions, "delete", "namespace", "-l", OWNER_SELECTOR, "--ignore-not-found", "--wait=false"))


def delete_cluster(runner: Runner, versions: Versions) -> None:
    runner.stream(["kind", "delete", "cluster", "--name", versions.cluster_name])
