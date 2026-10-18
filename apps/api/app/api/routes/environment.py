"""GET /environment: what the engine is connected to (database, cluster, Prometheus)."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_kubernetes_adapter, get_prometheus_client
from app.core.config import Settings, get_settings
from app.db.session import get_db
from app.integrations.kubernetes_adapter import KubernetesAdapter
from app.integrations.prometheus_client import PrometheusClient
from app.schemas.environment import Environment
from app.services.environment import environment

router = APIRouter(tags=["health"])


@router.get("/environment", response_model=Environment)
def get_environment(
    db: Annotated[Session, Depends(get_db)],
    kubernetes: Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)],
    prometheus: Annotated[PrometheusClient, Depends(get_prometheus_client)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Environment:
    """Always 200; each check says whether that dependency answered.

    Probes are read-only (list workloads, Prometheus build info) and bounded by the
    configured request timeouts.
    """
    return Environment.model_validate(environment(db, kubernetes, prometheus, settings))
