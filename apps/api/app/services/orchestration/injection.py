"""INJECTING -> OBSERVING | INJECTION_FAILED: start the pod-delete fault via Litmus.

OBSERVING is entered only once Litmus reports the experiment running and the chosen
pods are actually gone from the cluster. Any failure, or no deletion within the
start timeout, stops the ChaosEngine so chaos cannot begin after we gave up.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import FaultType
from app.domain.safety_policy import SafetyPolicy
from app.domain.state_machine import (
    ExperimentState,
    InvalidTransitionError,
    can_transition,
    transition,
)
from app.integrations.chaos_provider import (
    ChaosEngineExistsError,
    ChaosProviderError,
    FaultPhase,
    FaultStatus,
    PodDeleteRequest,
    engine_name,
)
from app.integrations.kubernetes_adapter import ClusterUnavailableError, WorkloadStatus
from app.services.orchestration.baseline import BaselineStatus
from app.services.safety.policy_evaluator import evaluate_cluster


class Cluster(Protocol):
    def get_workload_status(self, target: Any) -> WorkloadStatus | None: ...
    def live_pod_names(self, namespace: str, names: list[str]) -> set[str]: ...


class Chaos(Protocol):
    def start_pod_delete(self, request: PodDeleteRequest) -> str: ...
    def get_status(self, namespace: str, name: str) -> FaultStatus: ...
    def stop(self, namespace: str, name: str) -> None: ...


@dataclass(frozen=True)
class StartWait:
    timeout_seconds: float
    poll_interval_seconds: float
    sleep: Callable[[float], None]

    @property
    def max_polls(self) -> int:
        return max(1, math.ceil(self.timeout_seconds / self.poll_interval_seconds))


class _InjectionFailed(Exception):
    pass


def run_injection(
    db: Session,
    experiment: Experiment,
    policy: SafetyPolicy,
    kubernetes: Cluster,
    chaos: Chaos,
    wait: StartWait,
) -> None:
    """Blocking injection for the manual /inject endpoint: start, then poll until
    the target pods are gone (-> OBSERVING) or it fails/times out.

    Raises InvalidTransitionError (before any change) if not in INJECTING.
    """
    if not can_transition(experiment.state, ExperimentState.OBSERVING):
        raise InvalidTransitionError(experiment.state, ExperimentState.OBSERVING)
    if not start_injection(db, experiment, policy, kubernetes, chaos):
        return
    for attempt in range(wait.max_polls):
        if attempt:
            wait.sleep(wait.poll_interval_seconds)
        last = attempt == wait.max_polls - 1
        if advance_injection(
            db, experiment, kubernetes, chaos, wait.timeout_seconds, force_deadline=last
        ):
            return


def start_injection(
    db: Session,
    experiment: Experiment,
    policy: SafetyPolicy,
    kubernetes: Cluster,
    chaos: Chaos,
    now: datetime | None = None,
) -> bool:
    """Create the ChaosEngine and persist its identity; the state stays INJECTING.

    Returns False (and moves to INJECTION_FAILED) if it could not be started. Never
    creates a second engine: if one is already recorded it returns True untouched.
    """
    if experiment.state is not ExperimentState.INJECTING:
        raise InvalidTransitionError(experiment.state, ExperimentState.OBSERVING)
    if (experiment.chaos or {}).get("engine_name"):
        return True
    try:
        request = _prepare(experiment, policy, kubernetes)
        try:
            engine = chaos.start_pod_delete(request)
        except ChaosEngineExistsError as exc:
            # Deterministic name ar-<id>: an engine from an interrupted earlier attempt.
            # Never run twice; stop it and fail explicitly.
            existing = engine_name(str(experiment.id))
            record = {"engine_name": existing, "namespace": request.target.namespace}
            _stop_quietly(chaos, request.target.namespace, existing, record)
            experiment.chaos = {
                "provider": "litmus",
                "experiment": "pod-delete",
                **record,
            }
            raise _InjectionFailed(
                f"{exc}; an earlier attempt may have been interrupted, so it was "
                "stopped rather than run twice"
            ) from exc
        except ChaosProviderError as exc:
            raise _InjectionFailed(str(exc)) from exc
    except _InjectionFailed as exc:
        _fail(db, experiment, str(exc))
        return False

    experiment.chaos = {
        "provider": "litmus",
        "experiment": "pod-delete",
        "pod_delete_mode": request.mode.value,
        "safety_policy": policy.name,
        "engine_name": engine,
        "namespace": request.target.namespace,
        "target_pods": list(request.target_pods),
        "duration_seconds": request.duration_seconds,
        "created_at": (now or datetime.now(UTC)).isoformat(),
        "injected_at": None,
        "status": None,
        "failure_reason": None,
    }
    db.commit()
    return True


def advance_injection(
    db: Session,
    experiment: Experiment,
    kubernetes: Cluster,
    chaos: Chaos,
    timeout_seconds: float,
    now: datetime | None = None,
    force_deadline: bool = False,
) -> bool:
    """One poll of a started injection. Returns True once the state left INJECTING.

    OBSERVING once Litmus runs and the target pods are gone; INJECTION_FAILED (engine
    stopped) if Litmus fails, status cannot be read, or `timeout_seconds` after the
    engine was created the pods are still there.
    """
    record = dict(experiment.chaos or {})
    namespace, engine = record["namespace"], record["engine_name"]
    now = now or datetime.now(UTC)
    created = datetime.fromisoformat(record["created_at"])
    timed_out = force_deadline or (now - created).total_seconds() > timeout_seconds
    try:
        confirmed = _poll_deletion(record, kubernetes, chaos)
        if not confirmed and timed_out:
            raise _InjectionFailed(
                f"Target pods not deleted within {timeout_seconds:g}s "
                f"(last Litmus status: {record['status']})"
            )
    except _InjectionFailed as exc:
        _stop_quietly(chaos, namespace, engine, record)
        experiment.chaos = record
        _fail(db, experiment, str(exc))
        return True
    if not confirmed:
        experiment.chaos = record
        db.commit()
        return False
    record["injected_at"] = now.isoformat()
    experiment.chaos = record
    experiment.state = transition(experiment.state, ExperimentState.OBSERVING)
    db.commit()
    return True


def _fail(db: Session, experiment: Experiment, reason: str) -> None:
    record = dict(
        experiment.chaos or {"provider": "litmus", "experiment": "pod-delete"}
    )
    record["failure_reason"] = reason
    experiment.chaos = record
    experiment.state = transition(experiment.state, ExperimentState.INJECTION_FAILED)
    db.commit()


def _prepare(
    experiment: Experiment, policy: SafetyPolicy, kubernetes: Cluster
) -> PodDeleteRequest:
    # Guards against state the state machine should already prevent.
    if not (experiment.validation_result or {}).get("passed"):
        raise _InjectionFailed("Experiment has no passing validation result")
    if (experiment.baseline or {}).get("status") != BaselineStatus.CAPTURED:
        raise _InjectionFailed("Experiment has no captured baseline")
    validated_with = ((experiment.validation_result or {}).get("policy") or {}).get(
        "name"
    )
    if validated_with != policy.name:
        raise _InjectionFailed(
            f"Safety policy changed since validation ({validated_with} -> {policy.name})"
        )
    if experiment.fault_type is not FaultType.POD_DELETE:
        raise _InjectionFailed(f"Fault type '{experiment.fault_type}' is not supported")

    # Re-check the blast radius against the cluster right before injecting.
    spec = experiment.spec
    try:
        status = kubernetes.get_workload_status(spec.target)
    except ClusterUnavailableError as exc:
        raise _InjectionFailed(f"Pre-injection cluster check failed: {exc}") from exc
    failed = [c.message for c in evaluate_cluster(spec, policy, status) if not c.passed]
    if failed or status is None:
        raise _InjectionFailed(
            "Pre-injection cluster check failed: " + "; ".join(failed)
        )

    return PodDeleteRequest(
        experiment_id=str(experiment.id),
        target=spec.target,
        label_selector=status.selector,
        # Deterministic choice: the first N ready pods by name.
        target_pods=status.ready_pod_names[: spec.affected_replicas],
        duration_seconds=spec.duration_seconds,
        mode=spec.pod_delete_mode,
    )


def _poll_deletion(record: dict[str, Any], kubernetes: Cluster, chaos: Chaos) -> bool:
    """True once Litmus runs and every target pod is gone or terminating."""
    namespace, engine = record["namespace"], record["engine_name"]
    try:
        status = chaos.get_status(namespace, engine)
    except ChaosProviderError as exc:
        raise _InjectionFailed(str(exc)) from exc
    record["status"] = status.to_dict()
    if status.phase is FaultPhase.FAILED:
        raise _InjectionFailed(
            f"Litmus reported failure (engine={status.engine_status}, "
            f"experiment={status.experiment_status}, verdict={status.verdict})"
        )
    if status.phase not in (FaultPhase.RUNNING, FaultPhase.COMPLETED):
        return False
    try:
        still_live = kubernetes.live_pod_names(namespace, list(record["target_pods"]))
    except ClusterUnavailableError as exc:
        raise _InjectionFailed(f"Could not confirm pod deletion: {exc}") from exc
    if not still_live:
        return True
    if status.phase is FaultPhase.COMPLETED:
        raise _InjectionFailed(
            f"Litmus completed but target pods still exist: {sorted(still_live)}"
        )
    return False


def _stop_quietly(
    chaos: Chaos, namespace: str, engine: str, record: dict[str, Any]
) -> None:
    try:
        chaos.stop(namespace, engine)
        record["stopped"] = True
    except ChaosProviderError as exc:
        record["stopped"] = False
        record["stop_error"] = str(exc)
