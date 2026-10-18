"""Application imports (P7, docs/imports.md).

Preview is stateless. Saving stores the reviewed plan; only `deploy` (with the
reviewed plan's digest) and `remove` (with the typed name) change the cluster, through
the dedicated provisioner identity. `refresh` reads health with the engine's
read-only access.
"""

import uuid
from functools import lru_cache
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.routes.experiments import Now, get_kubernetes_adapter
from app.core.config import get_settings
from app.db.models import AppImport
from app.db.session import get_db
from app.integrations.app_provisioner import (
    ImportProvisioner,
    ProvisionerError,
    ProvisionerUnavailableError,
)
from app.integrations.kubernetes_adapter import (
    ClusterUnavailableError,
    KubernetesAdapter,
)
from app.schemas.imports import (
    DeployRequest,
    ImportCapabilities,
    ImportList,
    ImportPreview,
    ImportRead,
    ImportRequest,
    ProvisionerInfo,
    RemoveRequest,
)
from app.services.imports import lifecycle
from app.services.imports.common import MAX_REPLICAS, MAX_WORKLOADS
from app.services.imports.compose import SUPPORTED_KEYS
from app.services.imports.manifests import SUPPORTED_KINDS
from app.services.imports.plan import NAMESPACE_PREFIX, preview
from app.services.imports.safe_yaml import MAX_BYTES, MAX_DOCUMENTS

router = APIRouter(prefix="/imports", tags=["imports"])


@lru_cache
def get_provisioner() -> ImportProvisioner:
    settings = get_settings()
    return ImportProvisioner(
        settings.provisioner_kubeconfig,
        settings.provisioner_context,
        settings.kube_request_timeout_seconds,
    )


DbSession = Annotated[Session, Depends(get_db)]
Provisioner = Annotated[ImportProvisioner, Depends(get_provisioner)]
Reader = Annotated[KubernetesAdapter, Depends(get_kubernetes_adapter)]


def _get(db: Session, import_id: uuid.UUID) -> AppImport:
    imp = db.get(AppImport, import_id)
    if imp is None:
        raise HTTPException(status_code=404, detail="Import not found")
    return imp


@router.get("/capabilities", response_model=ImportCapabilities)
def get_capabilities(provisioner: Provisioner, reader: Reader) -> ImportCapabilities:
    """What can be imported, and whether deployment is available here."""
    settings = get_settings()
    configured, detail = provisioner.configured, ""
    if not configured:
        detail = (
            "No provisioner identity configured: imports can be reviewed and saved, "
            "not deployed. Development: scripts/dev-provisioner.sh; local stack: ar install."
        )
    else:
        try:
            provisioner.verify()
            lifecycle.check_same_cluster(provisioner, reader)
            detail = "Dedicated provisioner identity verified on the execution cluster."
        except (
            ProvisionerUnavailableError,
            ProvisionerError,
            ClusterUnavailableError,
        ) as exc:
            configured, detail = False, str(exc)
    return ImportCapabilities(
        provisioner=ProvisionerInfo(
            configured=configured, context=settings.provisioner_context, detail=detail
        ),
        execution_context=settings.kube_context,
        max_bytes=MAX_BYTES,
        max_documents=MAX_DOCUMENTS,
        max_workloads=MAX_WORKLOADS,
        max_replicas=MAX_REPLICAS,
        namespace_prefix=NAMESPACE_PREFIX,
        compose_keys=SUPPORTED_KEYS,
        manifest_kinds=SUPPORTED_KINDS,
    )


@router.post("/preview", response_model=ImportPreview)
def post_preview(payload: ImportRequest) -> ImportPreview:
    """Parse, validate and plan; stores nothing and contacts no cluster."""
    return preview(payload, import_id=None, loadgen_image=get_settings().loadgen_image)


@router.post("", response_model=ImportRead, status_code=status.HTTP_201_CREATED)
def create_import(payload: ImportRequest, db: DbSession) -> ImportRead:
    """Save a reviewed import (PLANNED). Nothing is deployed."""
    try:
        imp = lifecycle.create(db, payload, get_settings().loadgen_image)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return lifecycle.to_read(imp)


@router.get("", response_model=ImportList)
def list_imports(db: DbSession) -> ImportList:
    rows = db.scalars(select(AppImport).order_by(AppImport.created_at.desc()))
    return ImportList(items=[lifecycle.to_read(i) for i in rows])


@router.get("/{import_id}", response_model=ImportRead)
def get_import(import_id: uuid.UUID, db: DbSession) -> ImportRead:
    return lifecycle.to_read(_get(db, import_id))


@router.post("/{import_id}/deploy", response_model=ImportRead)
def deploy_import(
    import_id: uuid.UUID,
    payload: DeployRequest,
    db: DbSession,
    provisioner: Provisioner,
    reader: Reader,
    now: Now,
) -> ImportRead:
    """Apply the reviewed plan (explicit approval: its digest and confirm=true)."""
    imp = _get(db, import_id)
    try:
        lifecycle.deploy(db, imp, payload.plan_digest, provisioner, reader, now)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProvisionerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return lifecycle.to_read(imp)


@router.post("/{import_id}/refresh", response_model=ImportRead)
def refresh_import(
    import_id: uuid.UUID,
    db: DbSession,
    provisioner: Provisioner,
    reader: Reader,
    now: Now,
) -> ImportRead:
    """One read-only health check; moves DEPLOYING on, and REMOVING to REMOVED."""
    imp = _get(db, import_id)
    settings = get_settings()
    try:
        lifecycle.refresh(
            db,
            imp,
            reader,
            provisioner,
            now,
            settings.import_deploy_timeout_seconds,
            settings.kube_context,
        )
    except ClusterUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return lifecycle.to_read(imp)


@router.post("/{import_id}/remove", response_model=ImportRead)
def remove_import(
    import_id: uuid.UUID,
    payload: RemoveRequest,
    db: DbSession,
    provisioner: Provisioner,
    now: Now,
) -> ImportRead:
    """Delete the import's namespace after verifying it owns it (typed confirmation)."""
    imp = _get(db, import_id)
    try:
        lifecycle.remove(db, imp, payload.confirm_name, provisioner, now)
    except lifecycle.LifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ProvisionerUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ProvisionerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return lifecycle.to_read(imp)


@router.delete("/{import_id}", status_code=status.HTTP_204_NO_CONTENT)
def forget_import(import_id: uuid.UUID, db: DbSession) -> Response:
    """Forget a removed (or never deployed) import's record."""
    try:
        lifecycle.forget(db, _get(db, import_id))
    except lifecycle.LifecycleError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
