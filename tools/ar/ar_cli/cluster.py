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
import re
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from .paths import (
    ENGINE_NAMESPACE,
    ENGINE_SERVICE_ACCOUNT,
    ENGINE_TOKEN_SECRET,
    OWNER_SELECTOR,
    PROMETHEUS_HOST_PORT,
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


def provision(runner: Runner, paths: Paths, versions: Versions, log: Log) -> None:
    """Sample apps, Prometheus, LitmusChaos and chaos RBAC (idempotent)."""
    verify_owned(runner, versions)
    m = paths.manifest
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
        ]
    )
    runner.run(["helm", "repo", "update", "prometheus-community"], timeout=300)
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
        ]
    )

    log(f"LitmusChaos (litmus-core {versions.litmus_core_chart}); pre-pulling images in the node")
    images = [versions.loadgen_image] + [
        f"litmuschaos.docker.scarf.sh/litmuschaos/{name}:{versions.litmus}"
        for name in ("chaos-operator", "chaos-runner", "go-runner")
    ]
    for image in images:
        runner.run(["docker", "exec", versions.node, "crictl", "pull", image], timeout=900)
    runner.run(["helm", "repo", "add", "litmuschaos", "https://litmuschaos.github.io/litmus-helm/", "--force-update"])
    runner.run(["helm", "repo", "update", "litmuschaos"], timeout=300)
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
        ]
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
    verify_owned(runner, versions)
    wait_namespace_gone_or_active(runner, versions)
    runner.run(kubectl(versions, "apply", "-f", str(paths.manifest("infra/rbac/engine-rbac.yaml"))))
    role = paths.manifest("infra/rbac/engine-chaos-role.yaml").read_text()
    for namespace in versions.chaos_namespaces:
        runner.run(kubectl(versions, "apply", "-f", "-"), input=for_namespace(role, namespace).encode())


def read_token(
    runner: Runner, versions: Versions, attempts: int = 30, sleep: Callable[[float], None] = time.sleep
) -> tuple[str, str]:
    """(token, base64 CA) from the ServiceAccount token Secret, once the controller filled it."""
    for _ in range(attempts):
        result = runner.run(
            kubectl(versions, "-n", ENGINE_NAMESPACE, "get", "secret", ENGINE_TOKEN_SECRET, "-o", "json"), check=False
        )
        if result.ok:
            data = json.loads(result.stdout).get("data") or {}
            if data.get("token") and data.get("ca.crt"):
                return base64.b64decode(data["token"]).decode(), data["ca.crt"]
        sleep(1)
    raise OwnershipError(f"Secret {ENGINE_NAMESPACE}/{ENGINE_TOKEN_SECRET} has no token yet")


def engine_kubeconfig(versions: Versions, token: str, ca_b64: str) -> str:
    """Kubeconfig for the engine container: in-network server, ServiceAccount token only."""
    config = {
        "apiVersion": "v1",
        "kind": "Config",
        "clusters": [
            {
                "name": versions.context,
                # The control-plane container on the `kind` Docker network (its cert covers this name).
                "cluster": {"server": f"https://{versions.node}:6443", "certificate-authority-data": ca_b64},
            }
        ],
        "users": [{"name": ENGINE_SERVICE_ACCOUNT, "user": {"token": token}}],
        "contexts": [
            {"name": versions.context, "context": {"cluster": versions.context, "user": ENGINE_SERVICE_ACCOUNT}}
        ],
        "current-context": versions.context,
    }
    return json.dumps(config, indent=2) + "\n"  # JSON is valid YAML


def write_engine_kubeconfig(runner: Runner, paths: Paths, versions: Versions) -> None:
    token, ca = read_token(runner, versions)
    write_private(paths.kubeconfig, engine_kubeconfig(versions, token, ca))


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
        Permission("create", "chaosengines.litmuschaos.io", chaos, True),
        Permission("delete", "chaosresults.litmuschaos.io", chaos, True),
        # Must stay denied: no workload writes, no pod deletion, no secrets, no chaos
        # outside prepared namespaces, no RBAC changes.
        Permission("create", "deployments.apps", chaos, False),
        Permission("delete", "pods", chaos, False),
        Permission("get", "secrets", chaos, False),
        Permission("list", "secrets", None, False),
        Permission("create", "chaosengines.litmuschaos.io", "default", False),
        Permission("create", "rolebindings.rbac.authorization.k8s.io", chaos, False),
    ]


def check_engine_permissions(runner: Runner, versions: Versions) -> list[tuple[Permission, bool]]:
    """(permission, actual) via `kubectl auth can-i --as` the engine's ServiceAccount."""
    results = []
    for p in expected_permissions(versions):
        scope = ["--all-namespaces"] if p.namespace is None else ["-n", p.namespace]
        out = runner.run(
            kubectl(versions, "auth", "can-i", p.verb, p.resource, *scope, "--as", ENGINE_USER), check=False
        )
        results.append((p, out.stdout.strip() == "yes"))
    return results


def revoke_engine_access(runner: Runner, versions: Versions) -> None:
    """Delete only objects carrying both ownership labels (the engine's identity)."""
    verify_owned(runner, versions)
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
