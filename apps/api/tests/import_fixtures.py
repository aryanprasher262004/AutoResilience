"""Inputs for import tests (P7), and a fake cluster snapshot of a deployed plan."""

from pathlib import Path
from typing import Any

from app.integrations.kubernetes_adapter import ClusterSnapshot
from app.schemas.imports import DeploymentPlan
from tests.topology_fixtures import OBSERVED_AT

REPO = Path(__file__).resolve().parents[3]
RESILIENCEMART_COMPOSE = (REPO / "examples/resiliencemart/compose.yaml").read_text()
RESILIENCEMART_MANIFESTS = (
    REPO / "examples/resiliencemart/k8s/resiliencemart.yaml"
).read_text()
UNSAFE_COMPOSE = (REPO / "examples/resiliencemart/unsafe-compose.yaml").read_text()

ENV_SECRET = "s3cr3t-value-never-copied"

COMPOSE = f"""
services:
  web:
    image: nginx:1.27-alpine
    ports: ["8080:80"]
    deploy: {{replicas: 2}}
    depends_on: [api]
    environment:
      DB_PASSWORD: {ENV_SECRET}
      MODE: test
  api:
    image: ghcr.io/stefanprodan/podinfo:6.7.1
    command: ["./podinfo", "--port=9898"]
    expose: ["9898"]
    healthcheck:
      test: ["CMD", "podcli", "check", "http", "localhost:9898/readyz"]
      interval: 5s
"""


def request(
    content: str = COMPOSE, kind: str = "compose", **extra: Any
) -> dict[str, Any]:
    return {
        "name": extra.pop("name", "shop"),
        "source": {"kind": kind, "content": content, "filename": "compose.yaml"},
        **extra,
    }


def _owner(kind: str, name: str, uid: str) -> dict[str, Any]:
    return {
        "apiVersion": "apps/v1",
        "kind": kind,
        "name": name,
        "uid": uid,
        "controller": True,
    }


def deployed(
    plan: DeploymentPlan,
    *,
    ready: bool = True,
    reason: str | None = None,
    only: set[str] | None = None,
) -> ClusterSnapshot:
    """The plan's workloads as the API server would report them once applied.

    `ready=False` leaves Pods running but not ready; `reason` sets a waiting reason
    (e.g. ImagePullBackOff) on every container; `only` limits which workloads exist.
    """
    objects: dict[str, list[dict[str, Any]]] = {
        r: []
        for r in (
            "deployments",
            "replicasets",
            "statefulsets",
            "pods",
            "services",
            "endpointslices",
            "events",
            "nodes",
        )
    }
    ns = plan.namespace
    for obj in plan.objects:
        if obj.kind not in ("Deployment", "StatefulSet"):
            continue
        name = obj.name
        if only is not None and name not in only:
            continue
        manifest = obj.manifest
        desired = manifest["spec"]["replicas"]
        labels = manifest["spec"]["template"]["metadata"]["labels"]
        uid = f"uid-{name}"
        ready_count = desired if ready and reason is None else 0
        workload = {
            "metadata": {
                "name": name,
                "namespace": ns,
                "uid": uid,
                "labels": manifest["metadata"]["labels"],
            },
            "spec": {"replicas": desired, "selector": manifest["spec"]["selector"]},
            "status": {
                "replicas": desired,
                "readyReplicas": ready_count,
                "availableReplicas": ready_count,
                "updatedReplicas": desired,
            },
        }
        objects["deployments" if obj.kind == "Deployment" else "statefulsets"].append(
            workload
        )
        owner_uid = uid
        if obj.kind == "Deployment":
            rs_uid = f"uid-{name}-rs"
            objects["replicasets"].append(
                {
                    "metadata": {
                        "name": f"{name}-rs",
                        "namespace": ns,
                        "uid": rs_uid,
                        "labels": labels,
                        "ownerReferences": [_owner("Deployment", name, uid)],
                    },
                    "spec": {
                        "replicas": desired,
                        "selector": manifest["spec"]["selector"],
                    },
                    "status": {"replicas": desired, "readyReplicas": ready_count},
                }
            )
            owner_kind, owner_name, owner_uid = "ReplicaSet", f"{name}-rs", rs_uid
        else:
            owner_kind, owner_name = "StatefulSet", name
        image = manifest["spec"]["template"]["spec"]["containers"][0]["image"]
        for i in range(desired):
            state: dict[str, Any] = (
                {"waiting": {"reason": reason}} if reason else {"running": {}}
            )
            objects["pods"].append(
                {
                    "metadata": {
                        "name": f"{name}-{i}",
                        "namespace": ns,
                        "uid": f"uid-{name}-pod-{i}",
                        "labels": labels,
                        "ownerReferences": [_owner(owner_kind, owner_name, owner_uid)],
                    },
                    "spec": {"nodeName": "autoresilience-control-plane"},
                    "status": {
                        "phase": "Pending" if reason else "Running",
                        "conditions": [
                            {
                                "type": "Ready",
                                "status": "True" if ready_count else "False",
                            }
                        ],
                        "containerStatuses": [
                            {
                                "name": name,
                                "image": image,
                                "ready": bool(ready_count),
                                "restartCount": 3
                                if reason == "CrashLoopBackOff"
                                else 0,
                                "state": state,
                            }
                        ],
                    },
                }
            )
    for obj in plan.objects:
        if obj.kind == "Service":
            objects["services"].append(
                {
                    "metadata": {
                        "name": obj.name,
                        "namespace": ns,
                        "uid": f"uid-svc-{obj.name}",
                        "labels": obj.manifest["metadata"]["labels"],
                    },
                    "spec": obj.manifest["spec"],
                }
            )
    return ClusterSnapshot(observed_at=OBSERVED_AT, objects=objects)
