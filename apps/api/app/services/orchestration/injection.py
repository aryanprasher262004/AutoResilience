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
    ChaosProviderError,
    FaultPhase,
    FaultStatus,
    PodDeleteRequest,
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
    """Raises InvalidTransitionError (before any change) if not in INJECTING."""
    if not can_transition(experiment.state, ExperimentState.OBSERVING):
        raise InvalidTransitionError(experiment.state, ExperimentState.OBSERVING)

    try:
        request = _prepare(experiment, policy, kubernetes)
        _start_and_confirm(
            db, experiment, request, kubernetes, chaos, wait, policy.name
        )
    except _InjectionFailed as exc:
        record = dict(
            experiment.chaos or {"provider": "litmus", "experiment": "pod-delete"}
        )
        record["failure_reason"] = str(exc)
        experiment.chaos = record
        experiment.state = transition(
            experiment.state, ExperimentState.INJECTION_FAILED
        )
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


def _start_and_confirm(
    db: Session,
    experiment: Experiment,
    request: PodDeleteRequest,
    kubernetes: Cluster,
    chaos: Chaos,
    wait: StartWait,
    policy_name: str,
) -> None:
    namespace = request.target.namespace
    try:
        engine = chaos.start_pod_delete(request)
    except ChaosProviderError as exc:
        raise _InjectionFailed(str(exc)) from exc

    record: dict[str, Any] = {
        "provider": "litmus",
        "experiment": "pod-delete",
        "pod_delete_mode": request.mode.value,
        "safety_policy": policy_name,
        "engine_name": engine,
        "namespace": namespace,
        "target_pods": list(request.target_pods),
        "duration_seconds": request.duration_seconds,
        "created_at": datetime.now(UTC).isoformat(),
        "injected_at": None,
        "status": None,
        "failure_reason": None,
    }
    # Persist the engine identity immediately, before waiting on it. Always assign
    # copies: SQLAlchemy only writes JSON columns when the assigned value changes.
    experiment.chaos = dict(record)
    db.commit()

    try:
        _wait_for_deletion(record, request, kubernetes, chaos, wait)
    except _InjectionFailed:
        _stop_quietly(chaos, namespace, engine, record)
        experiment.chaos = dict(record)
        raise

    record["injected_at"] = datetime.now(UTC).isoformat()
    experiment.chaos = dict(record)
    experiment.state = transition(experiment.state, ExperimentState.OBSERVING)
    db.commit()


def _wait_for_deletion(
    record: dict[str, Any],
    request: PodDeleteRequest,
    kubernetes: Cluster,
    chaos: Chaos,
    wait: StartWait,
) -> None:
    namespace, engine = request.target.namespace, record["engine_name"]
    targets = list(request.target_pods)
    for attempt in range(wait.max_polls):
        if attempt:
            wait.sleep(wait.poll_interval_seconds)
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
        if status.phase in (FaultPhase.RUNNING, FaultPhase.COMPLETED):
            try:
                still_live = kubernetes.live_pod_names(namespace, targets)
            except ClusterUnavailableError as exc:
                raise _InjectionFailed(
                    f"Could not confirm pod deletion: {exc}"
                ) from exc
            if not still_live:
                return
            if status.phase is FaultPhase.COMPLETED:
                raise _InjectionFailed(
                    f"Litmus completed but target pods still exist: {sorted(still_live)}"
                )
    raise _InjectionFailed(
        f"Target pods not deleted within {wait.timeout_seconds:g}s "
        f"(last Litmus status: {record['status']})"
    )


def _stop_quietly(
    chaos: Chaos, namespace: str, engine: str, record: dict[str, Any]
) -> None:
    try:
        chaos.stop(namespace, engine)
        record["stopped"] = True
    except ChaosProviderError as exc:
        record["stopped"] = False
        record["stop_error"] = str(exc)
