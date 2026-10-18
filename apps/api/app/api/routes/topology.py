"""Clusters, namespaces, topology and onboarded applications (read-only on clusters).

Only `POST`/`DELETE /applications` write, and only to the database.
"""

import uuid
from functools import lru_cache
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.routes.experiments import get_kubernetes_adapter
from app.core.config import get_settings
from app.db.models import AppImport, Application
from app.db.session import get_db
from app.integrations.kubernetes_adapter import ClusterUnavailableError
from app.schemas.applications import ApplicationCreate, ApplicationList, ApplicationRead
from app.schemas.topology import ClusterList, NamespaceList, Topology
from app.services.imports.overlay import annotate, overlay
from app.services.topology.clusters import (
    ClusterAccess,
    ClusterRegistry,
    ScopeError,
    UnknownClusterError,
    check_scope,
    list_namespaces,
    topology,
)

router = APIRouter(tags=["topology"])


@lru_cache
def get_cluster_registry() -> ClusterRegistry:
    return ClusterRegistry(get_settings(), get_kubernetes_adapter())


DbSession = Annotated[Session, Depends(get_db)]
Registry = Annotated[ClusterRegistry, Depends(get_cluster_registry)]
ContextParam = Annotated[
    str | None,
    Query(max_length=253, description="Omit for the engine's execution cluster"),
]


def _resolve(registry: ClusterRegistry, context: str | None) -> ClusterAccess:
    try:
        return registry.resolve(context)
    except UnknownClusterError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _field_error(field: str, message: str) -> HTTPException:
    """422 in FastAPI's validation shape, so clients map it onto the field."""
    return HTTPException(
        status_code=422,
        detail=[{"loc": ["body", field], "msg": message, "type": "value_error"}],
    )


@router.get("/clusters", response_model=ClusterList)
def get_clusters(registry: Registry) -> ClusterList:
    """Contexts this engine was configured to read. No cluster is contacted."""
    return ClusterList.model_validate(
        {"items": [c.describe() for c in registry.clusters()]}
    )


@router.get("/clusters/namespaces", response_model=NamespaceList)
def get_namespaces(registry: Registry, context: ContextParam = None) -> NamespaceList:
    """Namespaces offered for onboarding, with workload counts and access status."""
    access = _resolve(registry, context)
    try:
        body = list_namespaces(access, registry.reader(access))
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return NamespaceList.model_validate(body)


def _topology(
    registry: ClusterRegistry, access: ClusterAccess, namespaces: list[str]
) -> dict[str, Any]:
    try:
        return topology(access, registry.reader(access), namespaces)
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/topology", response_model=Topology)
def get_topology(
    registry: Registry,
    db: DbSession,
    context: ContextParam = None,
    namespace: Annotated[list[str] | None, Query(max_length=50)] = None,
) -> Topology:
    """Nodes and edges read from the cluster now (see docs/topology.md).

    Without `namespace`: every namespace the cluster's access allows.
    """
    access = _resolve(registry, context)
    try:
        check_scope(access, namespace or [])
    except ScopeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    body = _topology(registry, access, namespace or [])
    return Topology.model_validate(annotate(db, body))


# --- applications ---------------------------------------------------------------------


def _current_cluster(
    registry: ClusterRegistry, app: Application
) -> ClusterAccess | None:
    """The app's cluster if it and all its namespaces are still authorized."""
    try:
        access = registry.resolve(app.kube_context)
        check_scope(access, app.namespaces)
    except (UnknownClusterError, ScopeError):
        return None
    return access


def _read(registry: ClusterRegistry, app: Application) -> ApplicationRead:
    access = _current_cluster(registry, app)
    return ApplicationRead.model_validate(
        {
            "id": app.id,
            "name": app.name,
            "context": app.kube_context,
            "namespaces": app.namespaces,
            "cluster": access.describe() if access else None,
            "created_at": app.created_at,
            "updated_at": app.updated_at,
        }
    )


def _get(db: Session, application_id: uuid.UUID) -> Application:
    app = db.get(Application, application_id)
    if app is None:
        raise HTTPException(status_code=404, detail="Application not found")
    return app


@router.get("/applications", response_model=ApplicationList)
def get_applications(db: DbSession, registry: Registry) -> ApplicationList:
    apps = db.scalars(select(Application).order_by(Application.name))
    return ApplicationList(items=[_read(registry, a) for a in apps])


@router.post(
    "/applications",
    response_model=ApplicationRead,
    status_code=status.HTTP_201_CREATED,
)
def create_application(
    payload: ApplicationCreate, db: DbSession, registry: Registry
) -> ApplicationRead:
    """Record a namespace-scoped view of an authorized cluster.

    The namespaces must be readable now. Nothing is written to the cluster.
    """
    try:
        access = registry.resolve(payload.context)
    except UnknownClusterError as exc:
        raise _field_error("context", str(exc)) from exc
    try:
        check_scope(access, payload.namespaces)
    except ScopeError as exc:
        raise _field_error("namespaces", str(exc)) from exc
    try:
        offered = list_namespaces(access, registry.reader(access))
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    readable = {n["name"] for n in offered["items"] if n["access"] == "readable"}
    missing = [n for n in payload.namespaces if n not in readable]
    if missing:
        raise _field_error(
            "namespaces",
            f"Not found or not readable with the engine's access: {', '.join(missing)}",
        )
    app = Application(
        name=payload.name, kube_context=access.context, namespaces=payload.namespaces
    )
    db.add(app)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail=f"An application named {payload.name!r} exists"
        ) from exc
    db.refresh(app)
    return _read(registry, app)


@router.get("/applications/{application_id}", response_model=ApplicationRead)
def get_application(
    application_id: uuid.UUID, db: DbSession, registry: Registry
) -> ApplicationRead:
    return _read(registry, _get(db, application_id))


@router.delete("/applications/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_application(application_id: uuid.UUID, db: DbSession) -> Response:
    """Forget the application. The cluster and experiment history are unchanged."""
    app = _get(db, application_id)
    if db.scalars(select(AppImport).where(AppImport.application_id == app.id)).first():
        raise HTTPException(
            status_code=409,
            detail="This application was created by an import; remove the import instead",
        )
    db.delete(app)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/applications/{application_id}/topology", response_model=Topology)
def get_application_topology(
    application_id: uuid.UUID, db: DbSession, registry: Registry
) -> Topology:
    app = _get(db, application_id)
    access = _current_cluster(registry, app)
    if access is None:
        raise HTTPException(
            status_code=409,
            detail=f"Context {app.kube_context!r} or its namespaces are no longer "
            "authorized for this engine; onboard the application again",
        )
    body = annotate(db, _topology(registry, access, app.namespaces))
    imp = db.scalars(
        select(AppImport).where(AppImport.application_id == app.id)
    ).first()
    return Topology.model_validate(
        {
            **body,
            "application_id": app.id,
            "imported": overlay(imp, body) if imp is not None else None,
        }
    )
