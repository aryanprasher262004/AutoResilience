"""Topology graph: nodes and edges built from one read-only cluster snapshot (pure).

Every edge is a relationship the Kubernetes API itself states, never an inference:

    owns          metadata.ownerReferences (controller=true), owner UID verified
    selects       a Service's spec.selector matches the Pod's labels (same namespace)
    endpoint      an EndpointSlice endpoint's targetRef names the Pod (UID verified)
    slice_for     an EndpointSlice's kubernetes.io/service-name label, when it has no
                  owner reference to that Service
    scheduled_on  the Pod's spec.nodeName

Edges are declared configuration and control-plane state, not measured traffic.
Whatever could not be verified (a refused listing, an owner of a kind that is not
listed, a selector-less Service, ...) is reported in `unknowns` instead of being
guessed. Object fields are copied through an explicit allowlist: no annotations
(except the ReplicaSet revision), environment variables, commands or Secrets.

See docs/topology.md for the contract (`autoresilience-topology/1`).
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from app.integrations.kubernetes_adapter import ClusterSnapshot, ListingError
from app.services.analysis.services import health

SCHEMA = "autoresilience-topology/1"

# Snapshot resource -> node kind.
KINDS = {
    "deployments": "Deployment",
    "replicasets": "ReplicaSet",
    "statefulsets": "StatefulSet",
    "pods": "Pod",
    "services": "Service",
    "endpointslices": "EndpointSlice",
    "nodes": "Node",
}
NAMESPACED = [r for r in KINDS if r != "nodes"]
KIND_ORDER = list(KINDS.values())
WORKLOAD_KINDS = {"Deployment", "StatefulSet"}  # supported experiment targets
SERVICE_NAME_LABEL = "kubernetes.io/service-name"
REVISION_ANNOTATION = "deployment.kubernetes.io/revision"
EVENTS_PER_NODE = 10
MESSAGE_LIMIT = 500
UNKNOWN_SORT = ("type", "subject", "resource", "namespace", "detail")

Obj = dict[str, Any]


def node_id(kind: str, namespace: str | None, name: str) -> str:
    """Stable across snapshots: kind, namespace and name (the UID is an attribute)."""
    return f"{kind}:{namespace}/{name}" if namespace else f"{kind}:{name}"


def _meta(obj: Obj) -> Obj:
    meta = obj.get("metadata")
    return meta if isinstance(meta, dict) else {}


def _dict(value: Any) -> Obj:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _labels(obj: Obj) -> dict[str, str]:
    return {
        str(k): str(v)
        for k, v in _dict(_meta(obj).get("labels")).items()
        if isinstance(v, str)
    }


def _condition(obj: Obj, kind: str) -> str | None:
    for c in _list(_dict(obj.get("status")).get("conditions")):
        if isinstance(c, dict) and c.get("type") == kind:
            return str(c.get("status"))
    return None


def _selector_string(selector: Any) -> str | None:
    """A LabelSelector (match_labels + expressions) as kubectl prints it."""
    selector = _dict(selector)
    parts = [f"{k}={v}" for k, v in sorted(_dict(selector.get("matchLabels")).items())]
    for expr in _list(selector.get("matchExpressions")):
        expr = _dict(expr)
        values = ",".join(sorted(str(v) for v in _list(expr.get("values"))))
        op, key = expr.get("operator"), expr.get("key")
        parts.append(
            {
                "In": f"{key} in ({values})",
                "NotIn": f"{key} notin ({values})",
                "Exists": f"{key}",
                "DoesNotExist": f"!{key}",
            }.get(str(op), f"{key} {op} ({values})")
        )
    return ",".join(parts) or None


def _replicas(obj: Obj, kind: str) -> Obj:
    spec, status = _dict(obj.get("spec")), _dict(obj.get("status"))
    # spec.replicas is defaulted to 1 by the API server; absent only in malformed data.
    desired = _int(spec.get("replicas")) if "replicas" in spec else 1
    out: Obj = {
        "desired": desired,
        "current": _int(status.get("replicas")),
        "ready": _int(status.get("readyReplicas")),
        "available": _int(status.get("availableReplicas")),
        "updated": _int(status.get("updatedReplicas")),
        "selector": _selector_string(spec.get("selector")),
    }
    if kind == "ReplicaSet":
        revision = _dict(_meta(obj).get("annotations")).get(REVISION_ANNOTATION)
        out["revision"] = str(revision) if revision is not None else None
    return out


def _pod_details(obj: Obj) -> Obj:
    spec, status = _dict(obj.get("spec")), _dict(obj.get("status"))
    containers = []
    for c in _list(status.get("containerStatuses")):
        c = _dict(c)
        state = next(iter(_dict(c.get("state"))), None)
        reason = _dict(_dict(c.get("state")).get(state or "")).get("reason")
        containers.append(
            {
                "name": str(c.get("name", "")),
                "image": str(c.get("image", "")),
                "ready": c.get("ready") is True,
                "restart_count": _int(c.get("restartCount")),
                "state": state,
                "reason": str(reason) if reason else None,
            }
        )
    return {
        "phase": str(status.get("phase") or "Unknown"),
        "ready": _condition(obj, "Ready") == "True",
        "terminating": _meta(obj).get("deletionTimestamp") is not None,
        "restarts": sum(c["restart_count"] for c in containers),
        "node_name": spec.get("nodeName"),
        "pod_ip": status.get("podIP"),
        "start_time": status.get("startTime"),
        "containers": containers,
    }


def _pod_health(details: Obj) -> tuple[str, str]:
    phase = details["phase"]
    if details["terminating"]:
        return "DEGRADED", "Terminating"
    if phase == "Running":
        if details["ready"]:
            return "HEALTHY", "Running and Ready"
        return "DEGRADED", "Running, not Ready"
    if phase == "Succeeded":
        return "COMPLETED", "Succeeded"
    if phase in ("Pending", "Failed"):
        return "UNAVAILABLE", phase
    return "UNKNOWN", f"Phase {phase}"


def _service_details(obj: Obj) -> Obj:
    spec = _dict(obj.get("spec"))
    selector = {
        str(k): str(v) for k, v in _dict(spec.get("selector")).items() if v is not None
    }
    return {
        "type": str(spec.get("type") or "ClusterIP"),
        "cluster_ip": spec.get("clusterIP"),
        "selector": selector or None,
        "ports": [
            {
                "name": p.get("name"),
                "port": _int(p.get("port")),
                "target_port": str(p["targetPort"]) if "targetPort" in p else None,
                "protocol": str(p.get("protocol") or "TCP"),
            }
            for p in map(_dict, _list(spec.get("ports")))
        ],
    }


def _endpoint_conditions(endpoint: Obj) -> Obj:
    conditions = _dict(endpoint.get("conditions"))
    # Per the API, an unset `ready` means ready (unknown state is treated as ready).
    ready = conditions.get("ready")
    return {
        "ready": ready is not False,
        "serving": conditions.get("serving"),
        "terminating": conditions.get("terminating"),
    }


def _slice_details(obj: Obj) -> Obj:
    endpoints = [_dict(e) for e in _list(obj.get("endpoints"))]
    return {
        "address_type": obj.get("addressType"),
        "endpoints": len(endpoints),
        "ready": sum(_endpoint_conditions(e)["ready"] for e in endpoints),
        "ports": [
            {
                "name": p.get("name"),
                "port": _int(p.get("port")),
                "protocol": str(p.get("protocol") or "TCP"),
            }
            for p in map(_dict, _list(obj.get("ports")))
        ],
    }


def _node_details(obj: Obj) -> Obj:
    labels = _labels(obj)
    info = _dict(_dict(obj.get("status")).get("nodeInfo"))
    return {
        "ready": _condition(obj, "Ready"),
        "roles": sorted(
            k.split("/", 1)[1]
            for k in labels
            if k.startswith("node-role.kubernetes.io/") and "/" in k
        ),
        "unschedulable": _dict(obj.get("spec")).get("unschedulable") is True,
        "kubelet_version": info.get("kubeletVersion"),
        "os_image": info.get("osImage"),
        "architecture": info.get("architecture"),
    }


def _ready_health(ready: int, total: int, what: str) -> tuple[str, str]:
    if total == 0:
        return "UNAVAILABLE", f"No {what}"
    if ready >= total:
        return "HEALTHY", f"{ready}/{total} {what} ready"
    return ("DEGRADED" if ready else "UNAVAILABLE"), f"{ready}/{total} {what} ready"


class _Builder:
    def __init__(
        self,
        snapshot: ClusterSnapshot,
        namespaces: list[str] | None,
        excluded: frozenset[str],
        cluster: Obj,
    ) -> None:
        self.snapshot = snapshot
        self.scope = set(namespaces) if namespaces is not None else None
        self.excluded = excluded
        self.cluster = cluster
        self.nodes: dict[str, Obj] = {}
        self.edges: dict[str, Obj] = {}
        self.unknowns: list[Obj] = []
        self.by_uid: dict[str, str] = {}
        self.raw: dict[str, Obj] = {}
        self.failed = {e.resource for e in snapshot.errors}

    # --- helpers ----------------------------------------------------------------

    def in_scope(self, namespace: Any) -> bool:
        return (
            isinstance(namespace, str)
            and namespace not in self.excluded
            and (self.scope is None or namespace in self.scope)
        )

    def unknown(
        self,
        type_: str,
        detail: str,
        subject: str | None = None,
        resource: str | None = None,
        namespace: str | None = None,
    ) -> None:
        self.unknowns.append(
            {
                "type": type_,
                "subject": subject,
                "resource": resource,
                "namespace": namespace,
                "detail": detail,
            }
        )

    def edge(
        self,
        type_: str,
        source: str,
        target: str,
        provenance: str,
        detail: str,
        attributes: Obj | None = None,
    ) -> None:
        edge_id = f"{type_}:{source}->{target}"
        self.edges.setdefault(
            edge_id,
            {
                "id": edge_id,
                "type": type_,
                "source": source,
                "target": target,
                "provenance": {"source": provenance, "detail": detail},
                "attributes": attributes or {},
            },
        )

    # --- nodes ------------------------------------------------------------------

    def add_objects(self) -> None:
        for resource in NAMESPACED:
            for obj in self.snapshot.objects.get(resource, []):
                meta = _meta(obj)
                name, namespace = meta.get("name"), meta.get("namespace")
                if not isinstance(name, str) or not isinstance(namespace, str):
                    self.unknown(
                        "malformed_object",
                        f"A {KINDS[resource]} without a name or namespace was skipped",
                        resource=resource,
                    )
                    continue
                if self.in_scope(namespace):
                    self.add_node(KINDS[resource], obj, namespace, name)

    def add_node(self, kind: str, obj: Obj, namespace: str | None, name: str) -> str:
        meta = _meta(obj)
        nid = node_id(kind, namespace, name)
        node: Obj = {
            "id": nid,
            "kind": kind,
            "namespace": namespace,
            "name": name,
            "uid": meta.get("uid"),
            "labels": _labels(obj),
            "created_at": meta.get("creationTimestamp"),
            "health": "UNKNOWN",
            "health_reason": "",
            "replicas": None,
            "pod": None,
            "service": None,
            "endpoint_slice": None,
            "node": None,
            "experiment_target": None,
            "events": [],
        }
        if kind in ("Deployment", "StatefulSet", "ReplicaSet"):
            replicas = _replicas(obj, kind)
            node["replicas"] = replicas
            node["health"] = health(replicas["desired"], replicas["ready"])
            node["health_reason"] = (
                f"{replicas['ready']}/{replicas['desired']} ready (controller status)"
            )
        elif kind == "Pod":
            node["pod"] = _pod_details(obj)
            node["health"], node["health_reason"] = _pod_health(node["pod"])
        elif kind == "Service":
            node["service"] = _service_details(obj)
        elif kind == "EndpointSlice":
            node["endpoint_slice"] = details = _slice_details(obj)
            node["health"], node["health_reason"] = _ready_health(
                details["ready"], details["endpoints"], "endpoints"
            )
        elif kind == "Node":
            node["node"] = details = _node_details(obj)
            node["health"], node["health_reason"] = {
                "True": ("HEALTHY", "Ready"),
                "False": ("UNAVAILABLE", "NotReady"),
            }.get(details["ready"] or "", ("UNKNOWN", "Ready condition unknown"))
        if kind in WORKLOAD_KINDS:
            node["experiment_target"] = self.target_support()
        self.nodes[nid] = node
        self.raw[nid] = obj
        if isinstance(meta.get("uid"), str):
            self.by_uid[meta["uid"]] = nid
        return nid

    def target_support(self) -> Obj:
        if not self.cluster["chaos_permitted"]:
            return {
                "supported": False,
                "reason": "Read-only discovery cluster: chaos execution is not "
                "granted here. Experiments run only on the engine's execution context.",
            }
        return {
            "supported": True,
            "reason": "Supported kind on the execution cluster; safety validation "
            "decides whether an experiment may run.",
        }

    def add_cluster_nodes(self) -> None:
        """Nodes that host in-scope Pods (other cluster nodes are out of scope)."""
        wanted: dict[str, list[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            if node["kind"] == "Pod" and node["pod"]["node_name"]:
                wanted[str(node["pod"]["node_name"])].append(nid)
        observed = {
            _meta(o).get("name"): o for o in self.snapshot.objects.get("nodes", [])
        }
        for name, pods in sorted(wanted.items()):
            obj = observed.get(name)
            if obj is None:
                if "nodes" in self.failed:
                    reason = "Nodes could not be listed with the granted access"
                else:
                    reason = f"Node {name} is not in the cluster's node list"
                for pod in pods:
                    self.unknown(
                        "node_not_observed",
                        f"{reason}; the Pod reports spec.nodeName={name}",
                        subject=pod,
                    )
                continue
            nid = self.add_node("Node", obj, None, name)
            for pod in pods:
                self.edge(
                    "scheduled_on",
                    pod,
                    nid,
                    "spec.nodeName",
                    f"Pod spec.nodeName is {name}",
                )

    # --- edges ------------------------------------------------------------------

    def add_ownership(self) -> None:
        for nid, obj in list(self.raw.items()):
            for ref in map(_dict, _list(_meta(obj).get("ownerReferences"))):
                if ref.get("controller") is not True:
                    continue
                kind, name, uid = ref.get("kind"), ref.get("name"), ref.get("uid")
                owner = self.by_uid.get(uid) if isinstance(uid, str) else None
                if owner is not None and self.nodes[owner]["kind"] == kind:
                    self.edge(
                        "owns",
                        owner,
                        nid,
                        "metadata.ownerReferences",
                        f"Controller owner reference to {kind} {name} (UID verified)",
                    )
                    continue
                namespace = self.nodes[nid]["namespace"]
                same_name = node_id(str(kind), namespace, str(name))
                if same_name in self.nodes:
                    self.unknown(
                        "owner_uid_mismatch",
                        f"Owner reference names {kind} {name}, but the observed object "
                        "with that name has a different UID (recreated?)",
                        subject=nid,
                    )
                elif kind in KIND_ORDER and _resource_of(str(kind)) in self.failed:
                    self.unknown(
                        "owner_not_observed",
                        f"Owned by {kind} {name}, which could not be listed",
                        subject=nid,
                    )
                else:
                    self.unknown(
                        "owner_not_observed",
                        f"Owned by {kind} {name}; {kind} is not part of the topology"
                        if kind not in KIND_ORDER
                        else f"Owned by {kind} {name}, which was not observed",
                        subject=nid,
                    )

    def add_selectors(self) -> None:
        pods_by_ns: dict[str, list[str]] = defaultdict(list)
        for nid, node in self.nodes.items():
            if node["kind"] == "Pod":
                pods_by_ns[node["namespace"]].append(nid)
        for nid, node in self.nodes.items():
            if node["kind"] != "Service":
                continue
            details = node["service"]
            if details["type"] == "ExternalName":
                self.unknown(
                    "service_without_selector",
                    "ExternalName Service: resolves to an external DNS name, "
                    "no Pods or endpoints",
                    subject=nid,
                )
                continue
            selector = details["selector"]
            if not selector:
                self.unknown(
                    "service_without_selector",
                    "No spec.selector: its endpoints are managed outside Kubernetes "
                    "selectors, so no Pods are linked by selector",
                    subject=nid,
                )
                continue
            text = ",".join(f"{k}={v}" for k, v in sorted(selector.items()))
            for pod in pods_by_ns[node["namespace"]]:
                labels = self.nodes[pod]["labels"]
                if all(labels.get(k) == v for k, v in selector.items()):
                    self.edge(
                        "selects",
                        nid,
                        pod,
                        "spec.selector",
                        f"Service selector {text} matches the Pod's labels",
                    )

    def add_endpoints(self) -> None:
        for nid, node in list(self.nodes.items()):
            if node["kind"] != "EndpointSlice":
                continue
            obj = self.raw[nid]
            service = node["labels"].get(SERVICE_NAME_LABEL)
            if service:
                svc = node_id("Service", node["namespace"], service)
                owned = any(
                    e["type"] == "owns" and e["target"] == nid and e["source"] == svc
                    for e in self.edges.values()
                )
                if svc in self.nodes and not owned:
                    self.edge(
                        "slice_for",
                        nid,
                        svc,
                        f"label {SERVICE_NAME_LABEL}",
                        f"EndpointSlice label {SERVICE_NAME_LABEL}={service}",
                    )
            for endpoint in map(_dict, _list(obj.get("endpoints"))):
                ref = _dict(endpoint.get("targetRef"))
                if not ref:
                    continue
                if ref.get("kind") != "Pod":
                    self.unknown(
                        "endpoint_target_not_observed",
                        f"Endpoint targets {ref.get('kind')} {ref.get('name')}, "
                        "which is not part of the topology",
                        subject=nid,
                    )
                    continue
                pod = self.by_uid.get(str(ref.get("uid")))
                if pod is None or self.nodes[pod]["kind"] != "Pod":
                    self.unknown(
                        "endpoint_target_not_observed",
                        f"Endpoint targets Pod {ref.get('name')}, which was not "
                        "observed (deleted since, or outside the scope)",
                        subject=nid,
                    )
                    continue
                self.edge(
                    "endpoint",
                    nid,
                    pod,
                    "endpoints.targetRef",
                    f"Endpoint targetRef is Pod {ref.get('name')} (UID verified)",
                    _endpoint_conditions(endpoint),
                )

    def service_health(self) -> None:
        slices: dict[str, list[str]] = defaultdict(list)
        for e in self.edges.values():
            if (
                e["type"] == "owns"
                and self.nodes[e["target"]]["kind"] == "EndpointSlice"
            ):
                slices[e["source"]].append(e["target"])
            elif e["type"] == "slice_for":
                slices[e["target"]].append(e["source"])
        for nid, node in self.nodes.items():
            if node["kind"] != "Service":
                continue
            if node["service"]["type"] == "ExternalName":
                node["health_reason"] = "ExternalName: no endpoints to inspect"
                continue
            if "endpointslices" in self.failed:
                node["health_reason"] = "EndpointSlices could not be listed"
                continue
            details = [self.nodes[s]["endpoint_slice"] for s in slices[nid]]
            node["health"], node["health_reason"] = _ready_health(
                sum(d["ready"] for d in details),
                sum(d["endpoints"] for d in details),
                "endpoints",
            )

    # --- events -----------------------------------------------------------------

    def attach_events(self) -> None:
        by_object: dict[str, list[Obj]] = defaultdict(list)
        for event in self.snapshot.objects.get("events", []):
            involved = _dict(event.get("involvedObject"))
            kind, name = involved.get("kind"), involved.get("name")
            if not isinstance(kind, str) or not isinstance(name, str):
                continue
            target = node_id(
                kind, involved.get("namespace") if kind != "Node" else None, name
            )
            node = self.nodes.get(target)
            if node is None:
                continue
            if involved.get("uid") and node["uid"] and involved["uid"] != node["uid"]:
                continue  # about an earlier object with the same name
            by_object[target].append(
                {
                    "type": str(event.get("type") or "Normal"),
                    "reason": str(event.get("reason") or ""),
                    "message": str(event.get("message") or "")[:MESSAGE_LIMIT],
                    "count": _int(event.get("count")) or 1,
                    "last_seen": event.get("lastTimestamp")
                    or event.get("eventTime")
                    or _meta(event).get("creationTimestamp"),
                }
            )
        for target, events in by_object.items():
            events.sort(
                key=lambda e: (str(e["last_seen"] or ""), e["reason"], e["message"]),
                reverse=True,
            )
            self.nodes[target]["events"] = events[:EVENTS_PER_NODE]

    # --- listing problems ---------------------------------------------------------

    def report_listings(self, errors: Iterable[ListingError]) -> None:
        for e in errors:
            if e.namespace is not None and not self.in_scope(e.namespace):
                continue
            where = f" in namespace {e.namespace}" if e.namespace else ""
            forbidden = e.status in (401, 403)
            self.unknown(
                "listing_forbidden" if forbidden else "listing_failed",
                (
                    f"Not permitted to list {e.resource}{where} ({e.status}); "
                    f"{e.resource} and their relationships are missing"
                    if forbidden
                    else f"Listing {e.resource}{where} failed"
                    + (f" ({e.status})" if e.status else "")
                    + f": {e.reason}"
                ),
                resource=e.resource,
                namespace=e.namespace,
            )
        for resource, namespace in self.snapshot.truncated:
            where = f" in namespace {namespace}" if namespace else ""
            self.unknown(
                "listing_truncated",
                f"More {resource}{where} exist than one listing returns; "
                "the rest are not shown",
                resource=resource,
                namespace=namespace,
            )

    def build(self) -> Obj:
        self.add_objects()
        self.add_ownership()
        self.add_cluster_nodes()
        self.add_selectors()
        self.add_endpoints()
        self.service_health()
        self.attach_events()
        self.report_listings(self.snapshot.errors)
        nodes = sorted(
            self.nodes.values(),
            key=lambda n: (
                KIND_ORDER.index(n["kind"]),
                n["namespace"] or "",
                n["name"],
            ),
        )
        counts: dict[str, int] = defaultdict(int)
        for n in nodes:
            counts[n["kind"]] += 1
        return {
            "schema": SCHEMA,
            "observed_at": self.snapshot.observed_at,
            "cluster": self.cluster,
            "scope": {
                "namespaces": sorted(self.scope) if self.scope is not None else None,
                "excluded_namespaces": sorted(self.excluded),
            },
            "nodes": nodes,
            "edges": sorted(self.edges.values(), key=lambda e: e["id"]),
            "unknowns": sorted(
                self.unknowns,
                key=lambda u: tuple(str(u[k] or "") for k in UNKNOWN_SORT),
            ),
            "counts": dict(counts),
            "traffic": {
                "observed": False,
                "detail": "Edges are relationships declared in the Kubernetes API "
                "(ownership, selectors, endpoints, scheduling). They show where "
                "traffic can go, not traffic that was measured.",
            },
        }


def _resource_of(kind: str) -> str:
    return next(r for r, k in KINDS.items() if k == kind)


def build_topology(
    snapshot: ClusterSnapshot,
    *,
    namespaces: list[str] | None,
    excluded: frozenset[str],
    cluster: Obj,
) -> Obj:
    """`namespaces=None`: every namespace not in `excluded`."""
    return _Builder(snapshot, namespaces, excluded, cluster).build()
