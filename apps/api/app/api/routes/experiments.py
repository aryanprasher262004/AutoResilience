import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Experiment
from app.db.session import get_db
from app.domain.safety_policy import SafetyPolicy, policy_for_namespace
from app.domain.state_machine import InvalidTransitionError
from app.integrations.chaos_provider import LitmusChaosProvider
from app.integrations.kubernetes_adapter import KubernetesAdapter
from app.integrations.prometheus_client import PrometheusClient
from app.schemas.experiment import (
    AbortRequest,
    ExperimentCreate,
    ExperimentRead,
    ScoreRead,
)
from app.services.orchestration.baseline import run_baseline
from app.services.orchestration.injection import StartWait, run_injection
from app.services.orchestration.observation import (
    ObservationConfig,
    advance_observation,
)
from app.services.orchestration.orchestrator import (
    OrchestrationError,
    abort_experiment,
    experiment_lock,
    is_auto,
    request_auto_run,
)
from app.services.orchestration.preflight import run_validation
from app.services.orchestration.recovery import RecoveryRule
from app.services.scoring.resilience_score import SUPPORTED_VERSIONS, score_experiment

router = APIRouter(prefix="/experiments", tags=["experiments"])


PolicyResolver = Callable[[str], SafetyPolicy]


def get_policy_resolver() -> PolicyResolver:
    """Namespace -> policy. Only the experiment's target namespace selects it."""
    return policy_for_namespace


@lru_cache
def get_kubernetes_adapter() -> KubernetesAdapter:
    settings = get_settings()
    return KubernetesAdapter(
        settings.kube_context, settings.kube_request_timeout_seconds
    )


@lru_cache
def get_prometheus_client() -> PrometheusClient:
    settings = get_settings()
    return PrometheusClient(
        settings.prometheus_url, settings.prometheus_timeout_seconds
    )


def get_baseline_window_seconds() -> int:
    return get_settings().baseline_window_seconds


@lru_cache
def get_chaos_provider() -> LitmusChaosProvider:
    settings = get_settings()
    return LitmusChaosProvider(
        settings.kube_context, settings.kube_request_timeout_seconds
    )


def get_start_wait() -> StartWait:
    settings = get_settings()
    return StartWait(
        timeout_seconds=settings.chaos_start_timeout_seconds,
        poll_interval_seconds=settings.chaos_poll_interval_seconds,
        sleep=time.sleep,
    )


def get_observation_config() -> ObservationConfig:
    settings = get_settings()
    return ObservationConfig(
        observation_grace_seconds=settings.observation_grace_seconds,
        recovery_timeout_seconds=settings.recovery_timeout_seconds,
        rule=RecoveryRule(
            stable_samples=settings.recovery_stable_samples,
            max_gap_seconds=settings.recovery_max_sample_gap_seconds,
            error_ratio_tolerance=settings.recovery_error_ratio_tolerance,
        ),
    )


def get_now() -> datetime:
    return datetime.now(UTC)


DbSession = Annotated[Session, Depends(get_db)]
Policies = Annotated[PolicyResolver, Depends(get_policy_resolver)]
Kubernetes = Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)]
Prometheus = Annotated[PrometheusClient, Depends(get_prometheus_client)]
BaselineWindow = Annotated[int, Depends(get_baseline_window_seconds)]
ChaosProvider = Annotated[LitmusChaosProvider, Depends(get_chaos_provider)]
Wait = Annotated[StartWait, Depends(get_start_wait)]
ObserveConfig = Annotated[ObservationConfig, Depends(get_observation_config)]
Now = Annotated[datetime, Depends(get_now)]


def _manual_only(experiment: Experiment) -> None:
    if is_auto(experiment):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Experiment is driven by the orchestrator (POST /run); "
            "use GET to follow it or POST /abort to stop it",
        )


def _get_or_404(db: Session, experiment_id: uuid.UUID) -> Experiment:
    experiment = db.get(Experiment, experiment_id)
    if experiment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Experiment not found"
        )
    return experiment


@router.post("", response_model=ExperimentRead, status_code=status.HTTP_201_CREATED)
def create_experiment(payload: ExperimentCreate, db: DbSession) -> Experiment:
    experiment = Experiment(
        name=payload.name,
        description=payload.description,
        target_namespace=payload.target.namespace,
        target_kind=payload.target.kind,
        target_name=payload.target.name,
        fault_type=payload.fault_type,
        duration_seconds=payload.duration_seconds,
        affected_replicas=payload.affected_replicas,
        pod_delete_mode=payload.pod_delete_mode,
    )
    db.add(experiment)
    db.commit()
    db.refresh(experiment)
    return experiment


@router.get("", response_model=list[ExperimentRead])
def list_experiments(db: DbSession) -> list[Experiment]:
    return list(db.scalars(select(Experiment).order_by(Experiment.created_at.desc())))


@router.get("/{experiment_id}", response_model=ExperimentRead)
def get_experiment(experiment_id: uuid.UUID, db: DbSession) -> Experiment:
    return _get_or_404(db, experiment_id)


@router.get("/{experiment_id}/score", response_model=ScoreRead)
def get_experiment_score(
    experiment_id: uuid.UUID,
    db: DbSession,
    version: Annotated[str | None, Query(pattern="^v[0-9]+$")] = None,
) -> dict[str, Any]:
    """The persisted Resilience Score (or the reason it was not scored).

    `?version=v1` recomputes that methodology from the same stored evidence
    (deterministic; not persisted). 404 until the experiment has finished.
    """
    experiment = _get_or_404(db, experiment_id)
    if experiment.score is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No score: experiment is {experiment.state} (scored when finished)",
        )
    if version is None or version == experiment.score.get("version"):
        return experiment.score
    if version not in SUPPORTED_VERSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown scoring version {version}; supported: {list(SUPPORTED_VERSIONS)}",
        )
    return score_experiment(
        experiment.state,
        experiment.baseline,
        experiment.observation,
        version=version,
        chaos=experiment.chaos,
    )


@router.post("/{experiment_id}/validate", response_model=ExperimentRead)
def validate_experiment(
    experiment_id: uuid.UUID, db: DbSession, policies: Policies, kubernetes: Kubernetes
) -> Experiment:
    """Run static then cluster safety checks.

    The outcome is the resulting state (BASELINING / VALIDATION_FAILED), not the HTTP status.
    """
    experiment = _get_or_404(db, experiment_id)
    _manual_only(experiment)
    try:
        run_validation(
            db, experiment, policies(experiment.target_namespace), kubernetes
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(experiment)
    return experiment


@router.post("/{experiment_id}/baseline", response_model=ExperimentRead)
def capture_experiment_baseline(
    experiment_id: uuid.UUID,
    db: DbSession,
    prometheus: Prometheus,
    window_seconds: BaselineWindow,
) -> Experiment:
    """Capture a steady-state baseline from Prometheus.

    Success moves BASELINING -> INJECTING; a failed capture is recorded and the
    experiment stays in BASELINING so it can be retried. No fault is injected.
    """
    experiment = _get_or_404(db, experiment_id)
    _manual_only(experiment)
    try:
        run_baseline(db, experiment, prometheus, window_seconds, datetime.now(UTC))
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(experiment)
    return experiment


@router.post("/{experiment_id}/inject", response_model=ExperimentRead)
def inject_fault(
    experiment_id: uuid.UUID,
    db: DbSession,
    policies: Policies,
    kubernetes: Kubernetes,
    chaos: ChaosProvider,
    wait: Wait,
) -> Experiment:
    """Start the pod-delete fault via LitmusChaos (INJECTING experiments only).

    Blocks until the target pods are confirmed deleted (-> OBSERVING) or the start
    fails/times out (-> INJECTION_FAILED, ChaosEngine stopped).
    """
    experiment = _get_or_404(db, experiment_id)
    _manual_only(experiment)
    try:
        run_injection(
            db,
            experiment,
            policies(experiment.target_namespace),
            kubernetes,
            chaos,
            wait,
        )
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(experiment)
    return experiment


@router.post("/{experiment_id}/observe", response_model=ExperimentRead)
def observe_experiment(
    experiment_id: uuid.UUID,
    db: DbSession,
    chaos: ChaosProvider,
    prometheus: Prometheus,
    kubernetes: Kubernetes,
    config: ObserveConfig,
    now: Now,
) -> Experiment:
    """Advance observation by one bounded step (call repeatedly while in progress).

    OBSERVING -> RECOVERING once Litmus finishes; RECOVERING -> COMPLETED when the
    recovery rule holds; -> UNKNOWN (with reason and cause) when it cannot be
    established. Read-only except stopping our own ChaosEngine on a Litmus timeout.
    """
    experiment = _get_or_404(db, experiment_id)
    _manual_only(experiment)
    try:
        advance_observation(db, experiment, chaos, prometheus, kubernetes, config, now)
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(experiment)
    return experiment


@router.post(
    "/{experiment_id}/run",
    response_model=ExperimentRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def run_experiment(experiment_id: uuid.UUID, db: DbSession, now: Now) -> Experiment:
    """Start the automatic lifecycle (idempotent).

    Accepts a CREATED experiment, or one that passed POST /validate and has not
    started (BASELINING without a baseline). The orchestrator then drives it to
    COMPLETED/UNKNOWN and cleans up; follow it with GET /experiments/{id}.
    """
    with experiment_lock(experiment_id):
        experiment = _get_or_404(db, experiment_id)
        db.refresh(experiment)
        try:
            request_auto_run(db, experiment, now)
        except OrchestrationError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc
        db.refresh(experiment)
        return experiment


@router.post("/{experiment_id}/abort", response_model=ExperimentRead)
def abort(
    experiment_id: uuid.UUID,
    payload: AbortRequest,
    db: DbSession,
    chaos: ChaosProvider,
    now: Now,
) -> Experiment:
    """Stop an active experiment: its own ChaosEngine only, then ABORTED."""
    with experiment_lock(experiment_id):
        experiment = _get_or_404(db, experiment_id)
        db.refresh(experiment)
        try:
            abort_experiment(db, experiment, chaos, payload.reason, now)
        except InvalidTransitionError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Experiment is {experiment.state}; nothing to abort",
            ) from exc
        db.refresh(experiment)
        return experiment
