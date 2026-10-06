"""Services: discovered Kubernetes workloads with their resilience history (read-only)."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_kubernetes_adapter
from app.db.session import get_db
from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.integrations.kubernetes_adapter import (
    ClusterUnavailableError,
    KubernetesAdapter,
)
from app.schemas.services import ServiceDetail, ServiceList
from app.services.analysis.services import (
    is_system_namespace,
    list_services,
    service_detail,
)

router = APIRouter(tags=["services"])

DbSession = Annotated[Session, Depends(get_db)]
Kubernetes = Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)]


@router.get("/services", response_model=ServiceList)
def get_services(db: DbSession, kubernetes: Kubernetes) -> ServiceList:
    """Deployments and StatefulSets outside system namespaces, with experiment history.

    Replica counts are the controllers' own status (as `kubectl get` shows them).
    """
    try:
        workloads = kubernetes.list_workloads()
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return ServiceList.model_validate(list_services(db, workloads))


@router.get("/services/{namespace}/{kind}/{name}", response_model=ServiceDetail)
def get_service(
    db: DbSession,
    kubernetes: Kubernetes,
    namespace: Annotated[str, Path(max_length=63)],
    kind: WorkloadKind,
    name: Annotated[str, Path(max_length=253)],
) -> ServiceDetail:
    """Live pod health plus this workload's experiments, scores and tested faults.

    If the cluster cannot be queried, history is still returned with
    health UNKNOWN and the error in `cluster_error`.
    """
    if is_system_namespace(namespace):
        raise HTTPException(
            status_code=404, detail=f"'{namespace}' is a system namespace"
        )
    target = ExperimentTarget(namespace, kind, name)
    status, cluster_error = None, None
    try:
        status = kubernetes.get_workload_status(target)
    except ClusterUnavailableError as exc:
        cluster_error = str(exc)
    detail = service_detail(db, target, status, cluster_error)
    if detail is None:
        raise HTTPException(
            status_code=404,
            detail=f"{kind.value} {namespace}/{name} is not in the cluster "
            "and has no experiments",
        )
    return ServiceDetail.model_validate(detail)
