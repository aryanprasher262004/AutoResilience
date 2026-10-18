"""Deployment health of an import, from a read-only topology of its namespace (pure).

A workload is READY when its controller reports every desired replica ready; until
then it is PROGRESSING unless a Pod shows a failure Kubernetes will not fix by itself
soon (image pull, crash loop, invalid configuration). Nothing is inferred beyond what
the controller and Pod statuses say.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas.imports import DeploymentPlan, WorkloadHealth

IMAGE_REASONS = {
    "ErrImagePull",
    "ImagePullBackOff",
    "InvalidImageName",
    "ErrImageNeverPull",
}
CRASH_REASONS = {"CrashLoopBackOff", "Error", "OOMKilled", "RunContainerError"}
CONFIG_REASONS = {"CreateContainerConfigError", "CreateContainerError"}
FAILED_STATES = {"IMAGE_PULL_FAILED", "CRASH_LOOP", "CONFIG_ERROR"}
# How long a failure state may persist before the deployment is reported FAILED
# (Kubernetes retries pulls and restarts; a short blip is not a verdict).
FAILURE_GRACE_SECONDS = 45.0

RECOVERY = {
    "IMAGE_PULL_FAILED": "Check that the image name and tag exist and are public (the "
    "node pulls them; private registries are not supported). Fix the file, import it "
    "again, or retry if the registry was unreachable.",
    "CRASH_LOOP": "The container starts and exits. It may need configuration that was "
    "not copied (environment values, files) or more memory. Check its logs with "
    "kubectl logs, then fix the image or the file and import it again.",
    "CONFIG_ERROR": "Kubernetes could not create the container from the plan; the "
    "event message says why.",
    "PROGRESSING": "Still starting after the deployment timeout. Large images can take "
    "a while to pull: retry, or remove the import.",
    "MISSING": "A planned workload does not exist. Retry the deployment.",
}


@dataclass(frozen=True)
class Assessment:
    workloads: list[WorkloadHealth]
    ready: bool
    # The first failure state found, if any.
    failure: str | None


def assess(plan: DeploymentPlan, topology: dict[str, Any]) -> Assessment:
    nodes = {n["id"]: n for n in topology.get("nodes", [])}
    owned_by: dict[str, list[str]] = {}
    for e in topology.get("edges", []):
        if e["type"] == "owns":
            owned_by.setdefault(e["source"], []).append(e["target"])

    def pods_of(nid: str) -> list[dict[str, Any]]:
        out = []
        for child in owned_by.get(nid, []):
            node = nodes[child]
            if node["kind"] == "Pod":
                out.append(node)
            elif node["kind"] == "ReplicaSet":
                out.extend(
                    nodes[p]
                    for p in owned_by.get(child, [])
                    if nodes[p]["kind"] == "Pod"
                )
        return out

    results: list[WorkloadHealth] = []
    for obj in plan.objects:
        if obj.kind not in ("Deployment", "StatefulSet"):
            continue
        nid = f"{obj.kind}:{plan.namespace}/{obj.name}"
        node = nodes.get(nid)
        desired = int(obj.manifest["spec"]["replicas"])
        if node is None:
            results.append(
                WorkloadHealth(
                    name=obj.name,
                    kind=obj.kind,
                    state="MISSING",
                    ready=0,
                    desired=desired,
                    detail="Not found",
                )
            )
            continue
        replicas = node.get("replicas") or {}
        ready = int(replicas.get("ready", 0))
        state, detail = "PROGRESSING", f"{ready}/{desired} ready"
        if ready >= desired and int(replicas.get("updated", 0)) >= desired:
            state = "READY"
        else:
            for pod in pods_of(nid):
                for c in (pod.get("pod") or {}).get("containers", []):
                    reason = c.get("reason")
                    if reason in IMAGE_REASONS:
                        state, detail = (
                            "IMAGE_PULL_FAILED",
                            f"{reason}: {c.get('image')}",
                        )
                    elif reason in CRASH_REASONS and c.get("restart_count", 0) > 0:
                        state = "CRASH_LOOP"
                        detail = f"{reason}, restarted {c.get('restart_count')} time(s)"
                    elif reason in CONFIG_REASONS:
                        state, detail = "CONFIG_ERROR", str(reason)
                if state != "PROGRESSING":
                    message = next(
                        (
                            ev["message"]
                            for ev in pod.get("events", [])
                            if ev["type"] == "Warning"
                        ),
                        None,
                    )
                    if message:
                        detail = f"{detail}. {message[:300]}"
                    break
            if state == "PROGRESSING":
                warning = next(
                    (ev for ev in node.get("events", []) if ev["type"] == "Warning"),
                    None,
                )
                if warning and warning["reason"] in ("FailedCreate",):
                    state, detail = "CONFIG_ERROR", warning["message"][:300]
        results.append(
            WorkloadHealth(
                name=obj.name,
                kind=obj.kind,
                state=state,
                ready=ready,
                desired=desired,
                detail=detail,
            )
        )
    failure = next((r.state for r in results if r.state in FAILED_STATES), None)
    return Assessment(
        workloads=results,
        ready=bool(results) and all(r.state == "READY" for r in results),
        failure=failure,
    )


def verdict(
    assessment: Assessment,
    started_at: datetime,
    failing_since: datetime | None,
    now: datetime,
    timeout_seconds: float,
) -> tuple[str, str | None]:
    """("READY" | "DEPLOYING" | "FAILED", failure state)."""
    if assessment.ready:
        return "READY", None
    if (
        assessment.failure
        and failing_since is not None
        and (now - failing_since).total_seconds() >= FAILURE_GRACE_SECONDS
    ):
        return "FAILED", assessment.failure
    if (now - started_at).total_seconds() >= timeout_seconds:
        missing = any(w.state == "MISSING" for w in assessment.workloads)
        return "FAILED", assessment.failure or ("MISSING" if missing else "PROGRESSING")
    return "DEPLOYING", None
