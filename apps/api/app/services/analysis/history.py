"""Experiment history queries and dashboard aggregation (read-only).

Everything is derived from persisted experiments; nothing is estimated. Score
statistics only use the current methodology version, because mixing versions
would compare different formulas.
"""

from collections import Counter
from statistics import median
from typing import Any, Literal

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import FaultType
from app.domain.state_machine import ExperimentState
from app.services.scoring.resilience_score import CURRENT_VERSION

S = ExperimentState
TERMINAL = {S.COMPLETED, S.UNKNOWN, S.ABORTED, S.VALIDATION_FAILED, S.INJECTION_FAILED}

SortKey = Literal["created_at", "updated_at", "name", "score"]
Order = Literal["asc", "desc"]


def _get(data: Any, *path: str) -> Any:
    for key in path:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _num(value: Any) -> float | None:
    return (
        float(value)
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def outcome_reason(e: Experiment) -> str | None:
    """Why the experiment ended where it did, from whichever stage decided it."""
    for reason in (
        _get(e.observation, "result", "reason"),
        _get(e.orchestration, "result", "reason"),
        _get(e.chaos, "failure_reason"),
        _get(e.orchestration, "abort", "reason"),
    ):
        if isinstance(reason, str) and reason:
            return reason
    validation = e.validation_result or {}
    if validation and not validation.get("passed"):
        failed = [
            c.get("message")
            for c in (validation.get("static_checks") or [])
            + (validation.get("cluster_checks") or [])
            if isinstance(c, dict) and c.get("status") in ("FAILED", "ERROR")
        ]
        return "; ".join(m for m in failed if m) or None
    return None


def summarize(e: Experiment) -> dict[str, Any]:
    score = e.score or None
    outage = _get(e.observation, "impact", "client", "outage")
    return {
        "id": e.id,
        "name": e.name,
        "target": e.target,
        "fault_type": e.fault_type,
        "pod_delete_mode": e.pod_delete_mode,
        "affected_replicas": e.affected_replicas,
        "duration_seconds": e.duration_seconds,
        "state": e.state,
        "auto": _get(e.orchestration, "mode") == "auto",
        "has_baseline": e.baseline is not None,
        "score": (
            {
                "score": _num(score.get("score")),
                "rating": score.get("rating"),
                "status": score.get("status"),
                "version": score.get("version"),
            }
            if score
            else None
        ),
        "time_to_recovery_seconds": _num(
            _get(e.observation, "recovery", "time_to_recovery_seconds")
        )
        if e.state is S.COMPLETED
        else None,
        "client_outage_seconds": _num(_get(outage, "outage_seconds"))
        if _get(outage, "status") == "OK"
        else None,
        "outcome_reason": outcome_reason(e),
        "created_at": e.created_at,
        "updated_at": e.updated_at,
    }


def query_history(
    db: Session,
    *,
    q: str | None = None,
    states: list[ExperimentState] | None = None,
    fault_types: list[FaultType] | None = None,
    namespaces: list[str] | None = None,
    sort: SortKey = "created_at",
    order: Order = "desc",
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[Experiment], int]:
    stmt = select(Experiment)
    if q:
        pattern = f"%{q.strip().lower()}%"
        stmt = stmt.where(
            or_(
                func.lower(Experiment.name).like(pattern),
                func.lower(Experiment.target_name).like(pattern),
                func.lower(Experiment.target_namespace).like(pattern),
            )
        )
    if states:
        stmt = stmt.where(Experiment.state.in_(states))
    if fault_types:
        stmt = stmt.where(Experiment.fault_type.in_(fault_types))
    if namespaces:
        stmt = stmt.where(Experiment.target_namespace.in_(namespaces))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    column: Any = {
        "created_at": Experiment.created_at,
        "updated_at": Experiment.updated_at,
        "name": func.lower(Experiment.name),
        "score": Experiment.score["score"].as_float(),
    }[sort]
    ordered = column.asc() if order == "asc" else column.desc()
    stmt = stmt.order_by(ordered.nulls_last(), Experiment.created_at.desc())
    items = list(db.scalars(stmt.limit(limit).offset(offset)))
    return items, int(total)


def _distribution(values: list[float]) -> dict[str, Any]:
    return {
        "count": len(values),
        "median": round(median(values), 3) if values else None,
        "minimum": round(min(values), 3) if values else None,
        "maximum": round(max(values), 3) if values else None,
    }


def dashboard_summary(db: Session, recent_limit: int = 8) -> dict[str, Any]:
    experiments = list(db.scalars(select(Experiment).order_by(Experiment.created_at)))
    by_state = Counter(e.state.value for e in experiments)

    scored = []
    not_scored = other_versions = not_recovered = 0
    for e in experiments:
        score = e.score or {}
        if not score:
            continue
        if score.get("status") == "NOT_SCORED":
            not_scored += 1
            continue
        if score.get("version") != CURRENT_VERSION or _num(score.get("score")) is None:
            other_versions += 1
            continue
        not_recovered += score.get("status") == "SCORED_NOT_RECOVERED"
        scored.append(e)
    values = [float(e.score["score"]) for e in scored if e.score]
    points = sorted(scored, key=lambda e: e.updated_at)

    recovery = [
        s["time_to_recovery_seconds"]
        for s in map(summarize, experiments)
        if s["time_to_recovery_seconds"] is not None
    ]
    outage = [
        s["client_outage_seconds"]
        for s in map(summarize, experiments)
        if s["client_outage_seconds"] is not None
    ]

    namespaces: dict[str, dict[str, Any]] = {}
    for e in experiments:
        ns = namespaces.setdefault(
            e.target_namespace,
            {
                "namespace": e.target_namespace,
                "total": 0,
                "completed": 0,
                "last_activity": e.updated_at,
            },
        )
        ns["total"] += 1
        ns["completed"] += e.state is S.COMPLETED
        ns["last_activity"] = max(ns["last_activity"], e.updated_at)

    recent = sorted(experiments, key=lambda e: e.created_at, reverse=True)[
        :recent_limit
    ]
    return {
        "total": len(experiments),
        "by_state": {
            state.value: by_state.get(state.value, 0) for state in ExperimentState
        },
        "outcomes": {
            "active": sum(1 for e in experiments if e.state not in TERMINAL),
            "completed": by_state.get(S.COMPLETED.value, 0),
            "failed": by_state.get(S.VALIDATION_FAILED.value, 0)
            + by_state.get(S.INJECTION_FAILED.value, 0),
            "aborted": by_state.get(S.ABORTED.value, 0),
            "undetermined": by_state.get(S.UNKNOWN.value, 0),
        },
        "scores": {
            "version": CURRENT_VERSION,
            "count": len(values),
            "average": round(sum(values) / len(values), 1) if values else None,
            "minimum": min(values) if values else None,
            "maximum": max(values) if values else None,
            "by_rating": dict(
                Counter(str((e.score or {}).get("rating")) for e in scored)
            ),
            "not_recovered": not_recovered,
            "not_scored": not_scored,
            "other_versions": other_versions,
        },
        "recovery_time_seconds": _distribution(recovery),
        "client_outage_seconds": _distribution(outage),
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
            for e in points
        ],
        "namespaces": sorted(
            namespaces.values(), key=lambda n: n["last_activity"], reverse=True
        ),
        "recent": [summarize(e) for e in recent],
    }
