"""Raw Kubernetes JSON (as the API server returns it) for topology tests.

Shaped after `kubectl get -o json` on the kind cluster's `shop` namespace, plus the
awkward cases a real cluster has: a Job-owned Pod, a selector-less Service, an
ExternalName Service, a Pod on a node that is not listed, an endpoint whose Pod is
gone, system-namespace objects, and a Pod carrying an inline secret in its env.
"""

import copy
from datetime import UTC, datetime
from typing import Any

from app.integrations.kubernetes_adapter import ClusterSnapshot, ListingError

OBSERVED_AT = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)
SECRET_VALUE = "hunter2-do-not-leak"
NODE = "autoresilience-control-plane"

Obj = dict[str, Any]


def meta(name: str, namespace: str | None, uid: str, **extra: Any) -> Obj:
    m: Obj = {"name": name, "uid": uid, "creationTimestamp": "2026-10-18T10:00:00Z"}
    if namespace is not None:
        m["namespace"] = namespace
    m.update(extra)
    return m


def owner(kind: str, name: str, uid: str, controller: bool = True) -> Obj:
    return {
        "apiVersion": "apps/v1",
        "kind": kind,
        "name": name,
        "uid": uid,
        "controller": controller,
    }


def deployment(name: str, uid: str, desired: int, ready: int, ns: str = "shop") -> Obj:
    return {
        "metadata": meta(
            name,
            ns,
            uid,
            labels={"app": name},
            annotations={"kubectl.kubernetes.io/last-applied-configuration": "{…}"},
        ),
        "spec": {"replicas": desired, "selector": {"matchLabels": {"app": name}}},
        "status": {
            "replicas": desired,
            "readyReplicas": ready,
            "availableReplicas": ready,
            "updatedReplicas": desired,
        },
    }


def replicaset(
    name: str, uid: str, deploy: Obj, desired: int, ready: int, revision: str
) -> Obj:
    rs = deployment(name, uid, desired, ready, deploy["metadata"]["namespace"])
    rs["metadata"]["ownerReferences"] = [
        owner("Deployment", deploy["metadata"]["name"], deploy["metadata"]["uid"])
    ]
    rs["metadata"]["annotations"] = {"deployment.kubernetes.io/revision": revision}
    rs["metadata"]["labels"] = {"app": deploy["metadata"]["name"]}
    return rs


def pod(
    name: str,
    uid: str,
    labels: dict[str, str],
    owner_ref: Obj | None,
    *,
    ns: str = "shop",
    ready: bool = True,
    phase: str = "Running",
    node: str | None = NODE,
    restarts: int = 0,
    env: list[Obj] | None = None,
) -> Obj:
    m = meta(name, ns, uid, labels=labels)
    if owner_ref:
        m["ownerReferences"] = [owner_ref]
    return {
        "metadata": m,
        "spec": {
            "nodeName": node,
            "containers": [{"name": "app", "image": "podinfo:6", "env": env or []}],
        },
        "status": {
            "phase": phase,
            "podIP": "10.244.0.10",
            "startTime": "2026-10-18T10:00:05Z",
            "conditions": [{"type": "Ready", "status": "True" if ready else "False"}],
            "containerStatuses": [
                {
                    "name": "app",
                    "image": "podinfo:6",
                    "ready": ready,
                    "restartCount": restarts,
                    "state": {"running": {}}
                    if ready
                    else {"waiting": {"reason": "CrashLoopBackOff"}},
                }
            ],
        },
    }


def service(
    name: str, uid: str, selector: dict[str, str] | None, type_: str = "ClusterIP"
) -> Obj:
    spec: Obj = {
        "type": type_,
        "clusterIP": "10.96.0.20",
        "ports": [{"name": "http", "port": 80, "targetPort": 9898, "protocol": "TCP"}],
    }
    if selector is not None:
        spec["selector"] = selector
    return {"metadata": meta(name, "shop", uid), "spec": spec}


def endpoint(pod_obj: Obj, ready: bool = True) -> Obj:
    return {
        "addresses": ["10.244.0.10"],
        "conditions": {"ready": ready, "serving": ready, "terminating": False},
        "targetRef": {
            "kind": "Pod",
            "name": pod_obj["metadata"]["name"],
            "namespace": "shop",
            "uid": pod_obj["metadata"]["uid"],
        },
    }


def endpoint_slice(
    name: str, uid: str, svc: Obj, endpoints: list[Obj], owned: bool = True
) -> Obj:
    m = meta(
        name,
        "shop",
        uid,
        labels={"kubernetes.io/service-name": svc["metadata"]["name"]},
    )
    if owned:
        m["ownerReferences"] = [
            {**owner("Service", svc["metadata"]["name"], svc["metadata"]["uid"])}
        ]
    return {
        "metadata": m,
        "addressType": "IPv4",
        "endpoints": endpoints,
        "ports": [{"name": "http", "port": 9898, "protocol": "TCP"}],
    }


def node(name: str = NODE) -> Obj:
    return {
        "metadata": meta(
            name, None, "node-uid", labels={"node-role.kubernetes.io/control-plane": ""}
        ),
        "spec": {},
        "status": {
            "conditions": [{"type": "Ready", "status": "True"}],
            "nodeInfo": {
                "kubeletVersion": "v1.33.1",
                "osImage": "Debian GNU/Linux 12",
                "architecture": "arm64",
            },
        },
    }


def event(kind: str, name: str, uid: str, reason: str, when: str, **extra: Any) -> Obj:
    return {
        "metadata": meta(f"{name}.{reason}", "shop", f"ev-{reason}-{when}"),
        "involvedObject": {"kind": kind, "name": name, "namespace": "shop", "uid": uid},
        "type": extra.get("type", "Warning"),
        "reason": reason,
        "message": extra.get("message", f"{reason} happened"),
        "count": extra.get("count", 1),
        "lastTimestamp": when,
    }


def shop() -> dict[str, list[Obj]]:
    checkout = deployment("checkout", "d-checkout", 2, 1)
    rs = replicaset("checkout-7d9", "rs-new", checkout, 2, 1, "2")
    old_rs = replicaset("checkout-5c4", "rs-old", checkout, 0, 0, "1")
    rs_owner = owner("ReplicaSet", "checkout-7d9", "rs-new")
    p1 = pod(
        "checkout-7d9-a",
        "p-a",
        {"app": "checkout"},
        rs_owner,
        env=[{"name": "DB_PASSWORD", "value": SECRET_VALUE}],
    )
    p2 = pod(
        "checkout-7d9-b", "p-b", {"app": "checkout"}, rs_owner, ready=False, restarts=4
    )
    redis = deployment("cart-redis", "s-redis", 1, 1)
    redis_pod = pod(
        "cart-redis-0",
        "p-redis",
        {"app": "cart-redis"},
        owner("StatefulSet", "cart-redis", "s-redis"),
    )
    job_pod = pod(
        "migrate-x1",
        "p-job",
        {"job-name": "migrate"},
        owner("Job", "migrate", "j-1"),
        phase="Succeeded",
        ready=False,
    )
    lost_pod = pod("orphan", "p-orphan", {"app": "orphan"}, None, node="worker-gone")
    svc = service("checkout", "svc-checkout", {"app": "checkout"})
    gone = {
        **endpoint(p1),
        "targetRef": {"kind": "Pod", "name": "checkout-old", "uid": "p-deleted"},
    }
    slice_ = endpoint_slice(
        "checkout-abc", "es-1", svc, [endpoint(p1), endpoint(p2, ready=False), gone]
    )
    manual = service("legacy-db", "svc-legacy", None)
    external = service("payments", "svc-ext", None, type_="ExternalName")
    system_pod = pod(
        "coredns-1", "p-dns", {"k8s-app": "kube-dns"}, None, ns="kube-system"
    )
    system_deploy = deployment("coredns", "d-dns", 2, 2, ns="kube-system")
    other_ns_pod = pod(
        "checkout-copy", "p-copy", {"app": "checkout"}, None, ns="staging"
    )
    return {
        "deployments": [checkout, system_deploy],
        "replicasets": [rs, old_rs],
        "statefulsets": [redis],
        "pods": [p1, p2, redis_pod, job_pod, lost_pod, system_pod, other_ns_pod],
        "services": [svc, manual, external],
        "endpointslices": [slice_],
        "events": [
            event("Pod", "checkout-7d9-b", "p-b", "BackOff", "2026-10-18T11:59:00Z"),
            event("Pod", "checkout-7d9-b", "p-b", "Unhealthy", "2026-10-18T11:58:00Z"),
            # About an earlier pod with the same name: must not be attached.
            event(
                "Pod", "checkout-7d9-b", "p-earlier", "Killing", "2026-10-18T09:00:00Z"
            ),
        ],
        "nodes": [node()],
    }


def snapshot(
    objects: dict[str, list[Obj]] | None = None,
    errors: list[ListingError] | None = None,
    truncated: list[tuple[str, str | None]] | None = None,
) -> ClusterSnapshot:
    return ClusterSnapshot(
        observed_at=OBSERVED_AT,
        objects=copy.deepcopy(objects if objects is not None else shop()),
        errors=errors or [],
        truncated=truncated or [],
    )
