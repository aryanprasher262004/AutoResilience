import time
import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Experiment
from app.db.session import get_db
from app.domain.safety_policy import DEFAULT_SAFETY_POLICY, SafetyPolicy
from app.domain.state_machine import InvalidTransitionError
from app.integrations.chaos_provider import LitmusChaosProvider
from app.integrations.kubernetes_adapter import KubernetesAdapter
from app.integrations.prometheus_client import PrometheusClient
from app.schemas.experiment import ExperimentCreate, ExperimentRead
from app.services.orchestration.baseline import run_baseline
from app.services.orchestration.injection import StartWait, run_injection
from app.services.orchestration.preflight import run_validation

router = APIRouter(prefix="/experiments", tags=["experiments"])


def get_safety_policy() -> SafetyPolicy:
    return DEFAULT_SAFETY_POLICY


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


DbSession = Annotated[Session, Depends(get_db)]
Policy = Annotated[SafetyPolicy, Depends(get_safety_policy)]
Kubernetes = Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)]
Prometheus = Annotated[PrometheusClient, Depends(get_prometheus_client)]
BaselineWindow = Annotated[int, Depends(get_baseline_window_seconds)]
ChaosProvider = Annotated[LitmusChaosProvider, Depends(get_chaos_provider)]
Wait = Annotated[StartWait, Depends(get_start_wait)]


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


@router.post("/{experiment_id}/validate", response_model=ExperimentRead)
def validate_experiment(
    experiment_id: uuid.UUID, db: DbSession, policy: Policy, kubernetes: Kubernetes
) -> Experiment:
    """Run static then cluster safety checks.

    The outcome is the resulting state (BASELINING / VALIDATION_FAILED), not the HTTP status.
    """
    experiment = _get_or_404(db, experiment_id)
    try:
        run_validation(db, experiment, policy, kubernetes)
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
    policy: Policy,
    kubernetes: Kubernetes,
    chaos: ChaosProvider,
    wait: Wait,
) -> Experiment:
    """Start the pod-delete fault via LitmusChaos (INJECTING experiments only).

    Blocks until the target pods are confirmed deleted (-> OBSERVING) or the start
    fails/times out (-> INJECTION_FAILED, ChaosEngine stopped).
    """
    experiment = _get_or_404(db, experiment_id)
    try:
        run_injection(db, experiment, policy, kubernetes, chaos, wait)
    except InvalidTransitionError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    db.refresh(experiment)
    return experiment
