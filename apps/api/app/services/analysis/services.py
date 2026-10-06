"""Services: live Kubernetes workloads joined with their experiment history (read-only).

Workloads come from the cluster; everything else comes from persisted experiments
matched on the exact target (namespace, kind, name). Nothing is estimated.
"""

from collections import defaultdict
from collections.abc import Iterable
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import ExperimentTarget
from app.domain.safety_policy import SYSTEM_NAMESPACES
from app.integrations.kubernetes_adapter import WorkloadStatus, WorkloadSummary
from app.services.analysis.history import S, _num, summarize
from app.services.scoring.resilience_score import CURRENT_VERSION

Key = tuple[str, str, str]  # namespace, kind, name


def is_system_namespace(namespace: str) -> bool:
    return namespace in SYSTEM_NAMESPACES


def health(desired: int, ready: int) -> str:
    if desired == 0:
        return "SCALED_TO_ZERO"
    if ready >= desired:
        return "HEALTHY"
    return "DEGRADED" if ready else "UNAVAILABLE"


def _key(e: Experiment) -> Key:
    return (e.target_namespace, e.target_kind.value, e.target_name)


def latest_score(experiments: Iterable[Experiment]) -> dict[str, Any] | None:
    """Most recent numeric score (any methodology version; the version is reported)."""
    for e in experiments:  # newest first
        score = e.score or {}
        value = _num(score.get("score"))
        if value is not None:
            return {
                "experiment_id": e.id,
                "score": value,
                "rating": score.get("rating"),
                "status": score.get("status"),
                "version": score.get("version"),
                "at": e.updated_at,
            }
    return None


def _experiments(db: Session, namespaces: set[str]) -> dict[Key, list[Experiment]]:
    """Experiments per exact target, newest first."""
    grouped: dict[Key, list[Experiment]] = defaultdict(list)
    if not namespaces:
        return grouped
    query = (
        select(Experiment)
        .where(Experiment.target_namespace.in_(namespaces))
        .order_by(Experiment.created_at.desc())
    )
    for e in db.scalars(query):
        grouped[_key(e)].append(e)
    return grouped


def list_services(db: Session, workloads: list[WorkloadSummary]) -> dict[str, Any]:
    visible = [w for w in workloads if not is_system_namespace(w.namespace)]
    history = _experiments(db, {w.namespace for w in visible})
    items = []
    for w in sorted(visible, key=lambda w: (w.namespace, w.name, w.kind.value)):
        runs = history.get((w.namespace, w.kind.value, w.name), [])
        items.append(
            {
                "namespace": w.namespace,
                "kind": w.kind,
                "name": w.name,
                "desired_replicas": w.desired_replicas,
                "current_replicas": w.current_replicas,
                "ready_replicas": w.ready_replicas,
                "available_replicas": w.available_replicas,
                "health": health(w.desired_replicas, w.ready_replicas),
                "created_at": w.created_at,
                "experiment_count": len(runs),
                "latest_experiment": summarize(runs[0]) if runs else None,
                "latest_score": latest_score(runs),
            }
        )
    return {"items": items, "excluded_namespaces": sorted(SYSTEM_NAMESPACES)}


def service_detail(
    db: Session,
    target: ExperimentTarget,
    status: WorkloadStatus | None,
    cluster_error: str | None,
    limit: int = 50,
) -> dict[str, Any] | None:
    """None if the workload is neither in the cluster nor in experiment history."""
    runs = _experiments(db, {target.namespace}).get(
        (target.namespace, target.kind.value, target.name), []
    )
    if status is None and cluster_error is None and not runs:
        return None

    faults: dict[tuple[str, str], list[Experiment]] = defaultdict(list)
    for e in runs:
        faults[(e.fault_type.value, e.pod_delete_mode.value)].append(e)

    scored = [
        e
        for e in runs
        if (e.score or {}).get("version") == CURRENT_VERSION
        and _num((e.score or {}).get("score")) is not None
    ]
    if cluster_error is not None:
        state = "UNKNOWN"
    elif status is None:
        state = "NOT_FOUND"
    else:
        state = health(status.desired_replicas, status.ready_pods)
    return {
        "namespace": target.namespace,
        "kind": target.kind,
        "name": target.name,
        "health": state,
        "live": None
        if status is None
        else {
            "desired_replicas": status.desired_replicas,
            "running_pods": status.running_pods,
            "ready_pods": status.ready_pods,
            "ready_pod_names": list(status.ready_pod_names),
        },
        "cluster_error": cluster_error,
        "experiment_count": len(runs),
        "latest_score": latest_score(runs),
        "faults": [
            {
                "fault_type": fault_type,
                "pod_delete_mode": mode,
                "runs": len(group),
                "completed": sum(e.state is S.COMPLETED for e in group),
                "last_run_at": group[0].created_at,
                "latest_score": latest_score(group),
            }
            for (fault_type, mode), group in sorted(faults.items())
        ],
        "score_version": CURRENT_VERSION,
        "score_history": [
            {
                "experiment_id": e.id,
                "name": e.name,
                "namespace": e.target_namespace,
                "workload": e.target_name,
                "at": e.updated_at,
                "score": float((e.score or {})["score"]),
                "rating": (e.score or {}).get("rating"),
            }
            for e in sorted(scored, key=lambda e: e.updated_at)
        ],
        "experiments": [summarize(e) for e in runs[:limit]],
    }
