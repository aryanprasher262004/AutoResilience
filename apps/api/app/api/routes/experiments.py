import uuid
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
from app.integrations.kubernetes_adapter import KubernetesAdapter
from app.schemas.experiment import ExperimentCreate, ExperimentRead
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


DbSession = Annotated[Session, Depends(get_db)]
Policy = Annotated[SafetyPolicy, Depends(get_safety_policy)]
Kubernetes = Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)]


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
