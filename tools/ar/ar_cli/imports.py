"""Read-only discovery access to a further cluster (`ar cluster import|remove`).

The operator names a kubeconfig context and the namespaces to share. With the
operator's own credentials (explicit `--context`, never the current one) this tool
creates a ServiceAccount that may only get/list topology resources in exactly those
namespaces (infra/rbac/viewer-*.yaml), checks that with `kubectl auth can-i --as`, and
gives the engine a kubeconfig entry with that token only. The engine never receives
the operator's credentials and is never granted chaos execution on imported clusters.

Every object carries VIEWER_SELECTOR's three labels; removal deletes only those, and
only after the context still reaches the same cluster (kube-system namespace UID).
"""

import base64
import ipaddress
import json
import re
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import cast
from urllib.parse import urlsplit

from .cluster import KubeconfigEntry, OwnershipError, for_namespace
from .paths import OWNER_SELECTOR, Paths, Versions
from .runner import Runner

VIEWER_NAMESPACE = "autoresilience-system"
VIEWER_SERVICE_ACCOUNT = "autoresilience-viewer"
VIEWER_TOKEN_SECRET = "autoresilience-viewer-token"
VIEWER_USER = f"system:serviceaccount:{VIEWER_NAMESPACE}:{VIEWER_SERVICE_ACCOUNT}"
VIEWER_SELECTOR = f"{OWNER_SELECTOR},autoresilience.io/access=read-only-discovery"
# Mirrors apps/api/app/domain/safety_policy.py SYSTEM_NAMESPACES (refused there too).
SYSTEM_NAMESPACES = frozenset(
    {"kube-system", "kube-public", "kube-node-lease", "local-path-storage", "litmus", "monitoring"}
)
MAX_NAMESPACES = 50

_CONTEXT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,252}$")
_NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class ImportRefused(Exception):
    """The import cannot be done as asked; the message says why."""


@dataclass(frozen=True)
class ImportRecord:
    context: str
    namespaces: list[str]
    include_nodes: bool
    cluster_uid: str
    # The API server URL the engine container uses.
    server: str
    created_namespace: bool
    imported_at: str

    @staticmethod
    def from_dict(raw: dict[str, object]) -> "ImportRecord":
        return ImportRecord(
            context=str(raw["context"]),
            namespaces=[str(n) for n in cast(list[object], raw["namespaces"])],
            include_nodes=bool(raw["include_nodes"]),
            cluster_uid=str(raw["cluster_uid"]),
            server=str(raw["server"]),
            created_namespace=bool(raw["created_namespace"]),
            imported_at=str(raw["imported_at"]),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Plan:
    context: str
    namespaces: list[str]
    include_nodes: bool
    cluster_uid: str
    server: str
    ca_b64: str
    create_namespace: bool


def kubectl(context: str, *args: str) -> list[str]:
    return ["kubectl", "--context", context, *args]


def list_contexts(runner: Runner) -> list[str]:
    """Context names of the operator's kubeconfig (names only, no credentials)."""
    result = runner.run(["kubectl", "config", "get-contexts", "-o", "name"], check=False)
    return sorted(line.strip() for line in result.stdout.splitlines() if line.strip()) if result.ok else []


def validate(versions: Versions, context: str, namespaces: list[str]) -> list[str]:
    if not _CONTEXT.match(context):
        raise ImportRefused(f"{context!r} is not a valid context name")
    if context == versions.context:
        raise ImportRefused(
            f"{context} is the stack's own cluster; the engine already reads it (and runs experiments there)"
        )
    if not namespaces:
        raise ImportRefused("Name at least one namespace to share (--namespace)")
    if len(set(namespaces)) > MAX_NAMESPACES:
        raise ImportRefused(f"At most {MAX_NAMESPACES} namespaces")
    for namespace in namespaces:
        if not _NAMESPACE.match(namespace) or len(namespace) > 63:
            raise ImportRefused(f"{namespace!r} is not a namespace name")
        if namespace in SYSTEM_NAMESPACES or namespace == VIEWER_NAMESPACE:
            raise ImportRefused(f"{namespace!r} is a system namespace and cannot be shared")
    return sorted(set(namespaces))


def fingerprint(runner: Runner, context: str) -> str:
    """The kube-system namespace UID: identifies the cluster behind a context."""
    result = runner.run(
        kubectl(context, "get", "namespace", "kube-system", "-o", "jsonpath={.metadata.uid}"),
        check=False,
        timeout=30,
    )
    uid = result.stdout.strip()
    if not result.ok or not uid:
        raise OwnershipError(f"Context {context} is not reachable ({result.stderr.strip()[:200]})")
    return uid


def verify_same_cluster(runner: Runner, record: ImportRecord) -> None:
    uid = fingerprint(runner, record.context)
    if uid != record.cluster_uid:
        raise OwnershipError(
            f"Context {record.context} now points at a different cluster (kube-system UID {uid}, "
            f"imported {record.cluster_uid}); refusing to change it"
        )


def engine_server(context: str, server: str) -> str:
    """The API server URL as the engine container must use it.

    Inside the container, loopback is the container itself. kind publishes its API on
    host loopback, but the engine shares kind's Docker network, where the control-plane
    container name is in the API certificate. Other loopback servers are unreachable.
    """
    parts = urlsplit(server)
    host = parts.hostname or ""
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback:
        return server
    if context.startswith("kind-") and context != "kind-":
        return f"https://{context.removeprefix('kind-')}-control-plane:6443"
    raise ImportRefused(
        f"{context} uses {server}, a loopback address the engine container cannot reach. "
        "Only kind clusters (on the `kind` Docker network) and clusters with a routable "
        "API server address can be imported."
    )


def cluster_endpoint(runner: Runner, context: str) -> tuple[str, str]:
    """(server, base64 CA) for the context. The operator's user credentials are not kept."""
    result = runner.run(["kubectl", "config", "view", "--minify", "--flatten", "--context", context, "-o", "json"])
    config = json.loads(result.stdout)
    clusters = config.get("clusters") or []
    if not clusters:
        raise ImportRefused(f"Context {context} has no cluster entry")
    entry = clusters[0].get("cluster") or {}
    ca = entry.get("certificate-authority-data")
    if not ca or entry.get("insecure-skip-tls-verify"):
        raise ImportRefused(f"Context {context} has no CA certificate; imports require a verified TLS connection")
    return str(entry["server"]), str(ca)


def plan(runner: Runner, versions: Versions, context: str, namespaces: list[str], include_nodes: bool) -> Plan:
    """Read-only checks with the operator's credentials; nothing is changed."""
    namespaces = validate(versions, context, namespaces)
    if context not in list_contexts(runner):
        raise ImportRefused(f"No context {context!r} in your kubeconfig (see `ar cluster contexts`)")
    uid = fingerprint(runner, context)
    for namespace in namespaces:
        found = runner.run(kubectl(context, "get", "namespace", namespace, "-o", "name"), check=False)
        if not found.ok:
            raise ImportRefused(f"Namespace {namespace} does not exist in {context}")
    existing = runner.run(
        kubectl(context, "get", "namespace", VIEWER_NAMESPACE, "-o", "json", "--ignore-not-found"), check=False
    )
    create_namespace = not existing.stdout.strip()
    if not create_namespace:
        labels = (json.loads(existing.stdout).get("metadata") or {}).get("labels") or {}
        owned = all(labels.get(k) == v for k, v in (p.split("=") for p in OWNER_SELECTOR.split(",")))
        if not owned:
            raise ImportRefused(
                f"Namespace {VIEWER_NAMESPACE} exists in {context} and was not created by AutoResilience; refusing"
            )
    server, ca = cluster_endpoint(runner, context)
    return Plan(context, namespaces, include_nodes, uid, engine_server(context, server), ca, create_namespace)


def describe(p: Plan) -> list[str]:
    lines = [f"in context {p.context} (cluster kube-system UID {p.cluster_uid}), with your credentials:"]
    if p.create_namespace:
        lines.append(f"  - create namespace {VIEWER_NAMESPACE}")
    lines += [
        f"  - create ServiceAccount {VIEWER_NAMESPACE}/{VIEWER_SERVICE_ACCOUNT} and its token Secret",
        f"  - in {', '.join(p.namespaces)}: a Role + RoleBinding to get/list Deployments, ReplicaSets,",
        "    StatefulSets, Pods, Services, EndpointSlices and Events (read-only)",
    ]
    if p.include_nodes:
        lines.append("  - a ClusterRole + binding to get/list Nodes (read-only, --include-nodes)")
    lines += [
        "  - not granted: Secrets, ConfigMaps, any write, chaos execution",
        f"then give the engine a kubeconfig entry for {p.context} (server {p.server}) with that token only",
    ]
    return lines


def apply(runner: Runner, paths: Paths, p: Plan) -> None:
    if fingerprint(runner, p.context) != p.cluster_uid:
        raise OwnershipError(f"Context {p.context} changed clusters since the plan; nothing applied")
    m = paths.manifest
    if p.create_namespace:
        runner.run(kubectl(p.context, "apply", "-f", str(m("infra/rbac/viewer-namespace.yaml"))))
    runner.run(kubectl(p.context, "apply", "-f", str(m("infra/rbac/viewer-identity.yaml"))))
    role = m("infra/rbac/viewer-role.yaml").read_text()
    for namespace in p.namespaces:
        runner.run(kubectl(p.context, "apply", "-f", "-"), input=for_namespace(role, namespace).encode())
    if p.include_nodes:
        runner.run(kubectl(p.context, "apply", "-f", str(m("infra/rbac/viewer-nodes.yaml"))))


@dataclass(frozen=True)
class Permission:
    verb: str
    resource: str
    namespace: str | None
    expected: bool


def expected_permissions(p: Plan) -> list[Permission]:
    ns = p.namespaces[0]
    return [
        Permission("list", "pods", ns, True),
        Permission("list", "deployments.apps", ns, True),
        Permission("list", "endpointslices.discovery.k8s.io", ns, True),
        Permission("list", "events", ns, True),
        Permission("list", "nodes", None, p.include_nodes),
        # Must stay denied.
        Permission("list", "pods", None, False),
        Permission("get", "secrets", ns, False),
        Permission("list", "configmaps", ns, False),
        Permission("delete", "pods", ns, False),
        Permission("patch", "deployments.apps", ns, False),
        Permission("create", "chaosengines.litmuschaos.io", ns, False),
        Permission("create", "rolebindings.rbac.authorization.k8s.io", ns, False),
    ]


def check_permissions(runner: Runner, p: Plan) -> list[tuple[Permission, bool]]:
    results = []
    for perm in expected_permissions(p):
        scope = ["--all-namespaces"] if perm.namespace is None else ["-n", perm.namespace]
        out = runner.run(
            kubectl(p.context, "auth", "can-i", perm.verb, perm.resource, *scope, "--as", VIEWER_USER), check=False
        )
        results.append((perm, out.stdout.strip() == "yes"))
    return results


def read_token(runner: Runner, context: str, attempts: int = 30, sleep: Callable[[float], None] = time.sleep) -> str:
    for _ in range(attempts):
        result = runner.run(
            kubectl(context, "-n", VIEWER_NAMESPACE, "get", "secret", VIEWER_TOKEN_SECRET, "-o", "json"), check=False
        )
        if result.ok:
            token = (json.loads(result.stdout).get("data") or {}).get("token")
            if token:
                return base64.b64decode(token).decode()
        sleep(1)
    raise OwnershipError(f"Secret {VIEWER_NAMESPACE}/{VIEWER_TOKEN_SECRET} in {context} has no token yet")


def kubeconfig_entry(p: Plan, token: str) -> KubeconfigEntry:
    return KubeconfigEntry(p.context, f"{VIEWER_SERVICE_ACCOUNT}@{p.context}", p.server, p.ca_b64, token)


def record(p: Plan) -> ImportRecord:
    return ImportRecord(
        context=p.context,
        namespaces=p.namespaces,
        include_nodes=p.include_nodes,
        cluster_uid=p.cluster_uid,
        server=p.server,
        created_namespace=p.create_namespace,
        imported_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )


def revoke(runner: Runner, r: ImportRecord) -> None:
    """Delete only this tool's labelled viewer objects, after re-checking the cluster."""
    verify_same_cluster(runner, r)
    for namespace in r.namespaces:
        runner.run(
            kubectl(
                r.context, "-n", namespace, "delete", "rolebinding,role", "-l", VIEWER_SELECTOR, "--ignore-not-found"
            )
        )
    runner.run(
        kubectl(r.context, "delete", "clusterrolebinding,clusterrole", "-l", VIEWER_SELECTOR, "--ignore-not-found")
    )
    runner.run(
        kubectl(
            r.context,
            "-n",
            VIEWER_NAMESPACE,
            "delete",
            "secret,serviceaccount",
            "-l",
            VIEWER_SELECTOR,
            "--ignore-not-found",
        )
    )
    if r.created_namespace:
        runner.run(
            # Only a namespace carrying the access label, i.e. viewer-namespace.yaml's.
            kubectl(r.context, "delete", "namespace", "-l", VIEWER_SELECTOR, "--ignore-not-found", "--wait=false")
        )


def discovery_setting(records: list[ImportRecord]) -> str:
    """The engine's DISCOVERY_CLUSTERS value (compact JSON, safe in an env file)."""
    value = [{"context": r.context, "namespaces": r.namespaces} for r in sorted(records, key=lambda r: r.context)]
    return json.dumps(value, separators=(",", ":"))
