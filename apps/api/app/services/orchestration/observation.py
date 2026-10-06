"""OBSERVING -> RECOVERING -> COMPLETED | UNKNOWN, one bounded step per call.

Each call reads Litmus/Prometheus/Kubernetes once and persists what it saw, so the
flow survives API restarts and no request blocks for the length of a fault.
Deadlines are computed from persisted timestamps.

UNKNOWN always carries a `cause` so platform problems are never reported as
application behaviour:
  platform              Litmus/Prometheus state unreadable, errored, or data gaps
  application           data was reliable but the target did not recover in time
  conflicting_evidence  Litmus verdict Fail although the metrics show recovery
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.state_machine import (
    ExperimentState,
    InvalidTransitionError,
    transition,
)
from app.integrations.chaos_provider import ChaosProviderError, FaultStatus
from app.integrations.kubernetes_adapter import ClusterUnavailableError, WorkloadStatus
from app.integrations.prometheus_client import PrometheusError, Sample, Series
from app.services.orchestration.recovery import (
    PodTimes,
    RecoveryFinding,
    RecoveryRule,
    error_check,
    find_recovery,
    observation_queries,
    window_request_queries,
)


class Chaos(Protocol):
    def get_status(self, namespace: str, name: str) -> FaultStatus: ...
    def get_result(self, namespace: str, name: str) -> dict[str, str | None]: ...
    def stop(self, namespace: str, name: str) -> None: ...


class Metrics(Protocol):
    def query(self, promql: str, at: datetime) -> list[Sample]: ...
    def query_value(self, promql: str, at: datetime) -> float | None: ...
    def query_raw(self, promql: str, at: datetime) -> list[Series]: ...


class Cluster(Protocol):
    def get_workload_status(self, target: Any) -> WorkloadStatus | None: ...
    def live_pod_names(self, namespace: str, names: list[str]) -> set[str]: ...


@dataclass(frozen=True)
class ObservationConfig:
    # Litmus must finish within duration + this, else the run is stopped.
    observation_grace_seconds: float
    # After Litmus finishes, how long recovery may take before giving up.
    recovery_timeout_seconds: float
    rule: RecoveryRule


class Cause(StrEnum):
    PLATFORM = "platform"
    APPLICATION = "application"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class _Unknown(Exception):
    def __init__(self, code: str, reason: str, cause: Cause) -> None:
        super().__init__(reason)
        self.code, self.reason, self.cause = code, reason, cause


def _iso(ts: float | None) -> str | None:
    return datetime.fromtimestamp(ts, UTC).isoformat() if ts is not None else None


def advance_observation(
    db: Session,
    experiment: Experiment,
    chaos: Chaos,
    metrics: Metrics,
    kubernetes: Cluster,
    config: ObservationConfig,
    now: datetime,
) -> None:
    """Raises InvalidTransitionError (no change) unless OBSERVING or RECOVERING."""
    if experiment.state not in (ExperimentState.OBSERVING, ExperimentState.RECOVERING):
        raise InvalidTransitionError(experiment.state, ExperimentState.RECOVERING)

    record: dict[str, Any] = dict(experiment.observation or {})
    record.setdefault("rule", config.rule.describe())
    record["evaluations"] = record.get("evaluations", 0) + 1
    record["updated_at"] = now.isoformat()
    record["result"] = {"status": "IN_PROGRESS", "reason_code": None}
    try:
        if experiment.state is ExperimentState.OBSERVING and _observe_litmus(
            experiment, record, chaos, config, now
        ):
            experiment.state = transition(experiment.state, ExperimentState.RECOVERING)
        if experiment.state is ExperimentState.RECOVERING and _evaluate_recovery(
            experiment, record, metrics, kubernetes, config, now
        ):
            experiment.state = transition(experiment.state, ExperimentState.COMPLETED)
            record["result"] = {
                "status": "COMPLETED",
                "reason_code": "RECOVERED",
                "reason": record["recovery"]["message"],
                "cause": None,
            }
    except _Unknown as exc:
        experiment.state = transition(experiment.state, ExperimentState.UNKNOWN)
        record["result"] = {
            "status": "UNKNOWN",
            "reason_code": exc.code,
            "reason": exc.reason,
            "cause": exc.cause,
        }
    experiment.observation = record  # new dict each call: SQLAlchemy sees the change
    db.commit()


# --- OBSERVING: wait for Litmus to finish ------------------------------------


def _observe_litmus(
    experiment: Experiment,
    record: dict[str, Any],
    chaos: Chaos,
    config: ObservationConfig,
    now: datetime,
) -> bool:
    """Returns True when the Litmus run reached a usable terminal outcome."""
    run = experiment.chaos or {}
    namespace, engine = run["namespace"], run["engine_name"]
    fault_start = datetime.fromisoformat(run["created_at"])
    deadline = (
        fault_start.timestamp()
        + run["duration_seconds"]
        + config.observation_grace_seconds
    )
    litmus: dict[str, Any] = dict(record.get("litmus") or {})

    try:
        status = chaos.get_status(namespace, engine)
    except ChaosProviderError as exc:
        litmus["last_error"] = str(exc)
        record["litmus"] = litmus
        if now.timestamp() > deadline:
            _stop(chaos, namespace, engine, litmus)
            raise _Unknown(
                "LITMUS_UNREADABLE", f"Litmus state unreadable: {exc}", Cause.PLATFORM
            ) from exc
        return False

    litmus.update(status.to_dict())
    litmus["last_error"] = None
    record["litmus"] = litmus

    if status.engine_status == "stopped" or status.verdict in ("Error", "Stopped"):
        raise _Unknown(
            "LITMUS_ERROR",
            f"Litmus run did not complete normally (engine={status.engine_status}, "
            f"verdict={status.verdict})",
            Cause.PLATFORM,
        )
    if status.experiment_status == "Completed" and status.verdict in ("Pass", "Fail"):
        litmus["finished_at"] = now.isoformat()
        try:
            litmus["chaos_result"] = chaos.get_result(namespace, engine)
        except ChaosProviderError as exc:  # evidence only; the engine verdict decides
            litmus["chaos_result"] = {"error": str(exc)}
        return True
    if now.timestamp() > deadline:
        _stop(chaos, namespace, engine, litmus)
        raise _Unknown(
            "LITMUS_TIMEOUT",
            f"Litmus did not finish within duration + "
            f"{config.observation_grace_seconds:g}s (status={status.experiment_status})",
            Cause.PLATFORM,
        )
    return False


def _stop(chaos: Chaos, namespace: str, engine: str, litmus: dict[str, Any]) -> None:
    try:
        chaos.stop(namespace, engine)
        litmus["stopped"] = True
    except ChaosProviderError as exc:
        litmus["stopped"] = False
        litmus["stop_error"] = str(exc)


# --- RECOVERING: apply the recovery rule --------------------------------------


def _evaluate_recovery(
    experiment: Experiment,
    record: dict[str, Any],
    metrics: Metrics,
    kubernetes: Cluster,
    config: ObservationConfig,
    now: datetime,
) -> bool:
    run = experiment.chaos or {}
    litmus = record.get("litmus") or {}
    fault_start = datetime.fromisoformat(run["created_at"]).timestamp()
    finished_at = datetime.fromisoformat(litmus["finished_at"]).timestamp()
    timed_out = now.timestamp() > finished_at + config.recovery_timeout_seconds
    baseline = experiment.baseline or {}
    desired = int(baseline["availability"]["values"]["desired_replicas"])
    target = experiment.target

    try:
        finding, impact = _measure(
            metrics,
            target,
            fault_start,
            desired,
            experiment.affected_replicas,
            config,
            now,
        )
    except PrometheusError as exc:
        record["last_error"] = str(exc)
        if timed_out:
            raise _Unknown(
                "PROMETHEUS_UNAVAILABLE",
                f"Recovery could not be measured: {exc}",
                Cause.PLATFORM,
            ) from exc
        return False
    record["last_error"] = None
    record["impact"] = impact
    recovery = _finding_dict(finding)

    if finding.recovered:
        ok, message = _check_requests(
            metrics, target, baseline, finding, config, recovery
        )
        recovery["message"] = message
        if not ok:
            recovery["status"] = "NOT_RECOVERED"
            finding = RecoveryFinding(
                False, message, max_observed_gap=finding.max_observed_gap
            )
    record["recovery"] = recovery

    if finding.recovered:
        record["target"] = _target_evidence(kubernetes, experiment, run)
        if litmus.get("verdict") != "Pass":
            raise _Unknown(
                "LITMUS_VERDICT_FAIL",
                f"Litmus verdict {litmus.get('verdict')} (failStep: "
                f"{(litmus.get('chaos_result') or {}).get('fail_step')}) conflicts with "
                "observed recovery",
                Cause.CONFLICTING_EVIDENCE,
            )
        return True

    if timed_out:
        _raise_not_recovered(finding, impact, config)
    return False


def _measure(
    metrics: Metrics,
    target: Any,
    fault_start: float,
    desired: int,
    affected: int,
    config: ObservationConfig,
    now: datetime,
) -> tuple[RecoveryFinding, dict[str, Any]]:
    window = int(now.timestamp() - fault_start) + 1
    q = observation_queries(target, window)
    series = metrics.query_raw(q["availability_raw"], now)
    availability = series[0].samples if series else []
    created = {
        s.labels.get("pod", ""): s.value for s in metrics.query(q["pod_created"], now)
    }
    ready = {
        s.labels.get("pod", ""): s.value
        for s in metrics.query(q["pod_ready_time"], now)
    }
    pods = [PodTimes(name, ts, ready.get(name)) for name, ts in sorted(created.items())]

    finding = find_recovery(
        fault_start=fault_start,
        affected_replicas=affected,
        desired_replicas=desired,
        pods=pods,
        availability=availability,
        rule=config.rule,
    )
    after = [v for t, v in availability if t >= fault_start]
    requests = metrics.query_value(q["requests_in_window"], now)
    errors = metrics.query_value(q["errors_in_window"], now)
    restarts = metrics.query_value(q["restarts_in_window"], now)
    impact = {
        "window_seconds": window,
        "availability_samples": len(after),
        "min_available_replicas": int(min(after)) if after else None,
        "availability_dip_observed": bool(after) and min(after) < desired,
        "restarts_in_window": int(restarts) if restarts is not None else None,
        "requests_in_window": round(requests, 2) if requests is not None else None,
        "errors_in_window": round(errors or 0.0, 2) if requests is not None else None,
        "replacement_pods": [
            {
                "pod": p.name,
                "created_at": _iso(p.created_at),
                "ready_at": _iso(p.ready_at),
            }
            for p in pods
            if p.created_at >= int(fault_start)
        ],
    }
    return finding, impact


def _check_requests(
    metrics: Metrics,
    target: Any,
    baseline: dict[str, Any],
    finding: RecoveryFinding,
    config: ObservationConfig,
    recovery: dict[str, Any],
) -> tuple[bool, str]:
    requests_baseline = baseline.get("requests") or {}
    values = requests_baseline.get("values") or {}
    if requests_baseline.get("status") != "OK" or not values.get("request_rate_rps"):
        recovery["error_check"] = {"applicable": False}
        return True, finding.message
    assert finding.recovered_at is not None and finding.confirmed_at is not None
    seconds = max(1, int(finding.confirmed_at - finding.recovered_at))
    q = window_request_queries(target, seconds)
    at = datetime.fromtimestamp(finding.confirmed_at, UTC)
    ok, message, ratio = error_check(
        requests=metrics.query_value(q["requests"], at),
        errors=metrics.query_value(q["errors"], at),
        baseline_error_ratio=values.get("error_ratio") or 0.0,
        rule=config.rule,
    )
    recovery["error_check"] = {
        "applicable": True,
        "ok": ok,
        "message": message,
        "error_ratio": ratio,
        "window_seconds": seconds,
    }
    return ok, f"{finding.message}; {message}" if ok else message


def _finding_dict(finding: RecoveryFinding) -> dict[str, Any]:
    ttr = finding.time_to_recovery_seconds
    return {
        "status": "RECOVERED" if finding.recovered else "NOT_RECOVERED",
        "message": finding.message,
        "fault_observed_at": _iso(finding.fault_observed_at),
        "recovered_at": _iso(finding.recovered_at),
        "confirmed_at": _iso(finding.confirmed_at),
        "time_to_recovery_seconds": round(ttr, 3) if ttr is not None else None,
        "stable_streak": [[_iso(t), v] for t, v in finding.streak],
        "max_sample_gap_seconds": round(finding.max_observed_gap, 3)
        if finding.max_observed_gap is not None
        else None,
    }


def _target_evidence(
    kubernetes: Cluster, experiment: Experiment, run: dict[str, Any]
) -> dict[str, Any]:
    """Kubernetes' own view at recovery time (evidence only; never decides)."""
    deleted = list(run.get("target_pods") or [])
    try:
        still_present = sorted(kubernetes.live_pod_names(run["namespace"], deleted))
        status = kubernetes.get_workload_status(experiment.target)
    except ClusterUnavailableError as exc:
        return {"deleted_pods": deleted, "error": str(exc)}
    return {
        "deleted_pods": deleted,
        "deleted_pods_still_present": still_present,
        "ready_pods_now": list(status.ready_pod_names) if status else [],
        "desired_replicas_now": status.desired_replicas if status else None,
    }


def _raise_not_recovered(
    finding: RecoveryFinding, impact: dict[str, Any], config: ObservationConfig
) -> None:
    gap = finding.max_observed_gap
    if not impact["availability_samples"]:
        raise _Unknown(
            "INSUFFICIENT_DATA",
            "No availability samples since the fault started",
            Cause.PLATFORM,
        )
    if gap is not None and gap > config.rule.max_gap_seconds:
        raise _Unknown(
            "INSUFFICIENT_DATA",
            f"Availability data has gaps up to {gap:.0f}s "
            f"(> {config.rule.max_gap_seconds:g}s); recovery cannot be established",
            Cause.PLATFORM,
        )
    raise _Unknown(
        "RECOVERY_NOT_OBSERVED",
        f"Target did not meet the recovery rule within "
        f"{config.recovery_timeout_seconds:g}s after Litmus finished: {finding.message}",
        Cause.APPLICATION,
    )
