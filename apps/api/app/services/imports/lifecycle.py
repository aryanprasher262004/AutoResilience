"""Import lifecycle: PLANNED -> DEPLOYING -> READY | FAILED -> REMOVING -> REMOVED.

    PLANNED    reviewed and saved; nothing exists in the cluster
    DEPLOYING  the user approved the exact plan (digest); objects applied, waiting
               for every workload to report ready (clients poll /refresh)
    READY      healthy; an Application (topology view) is linked; its workloads may
               become experiment targets (validation still decides each run)
    FAILED     a persistent failure or the timeout; retry (deploy again) or remove
    REMOVING   the user confirmed removal; the owned namespace is being deleted
    REMOVED    the namespace is gone; the record is kept until forgotten

Every cluster change needs an explicit request: nothing deploys on save, nothing
retries by itself, nothing is removed without the typed confirmation.
"""

import uuid
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AppImport, Application
from app.domain.safety_policy import SYSTEM_NAMESPACES
from app.integrations.app_provisioner import (
    OwnershipError,
    ProvisionerError,
    ProvisionerUnavailableError,
)
from app.integrations.kubernetes_adapter import ClusterSnapshot
from app.schemas.imports import (
    DeploymentPlan,
    DeploymentStatus,
    ImportRead,
    ImportRequest,
    ImportSpec,
)
from app.services.imports.health import RECOVERY, assess, verdict
from app.services.imports.plan import LOADGEN_NAME, is_import_namespace, preview
from app.services.topology.graph import build_topology

DEPLOYABLE = {"PLANNED", "FAILED"}
REMOVABLE = {"PLANNED", "DEPLOYING", "READY", "FAILED", "REMOVING"}


class LifecycleError(Exception):
    """The request does not fit the import's state (HTTP 409); safe to show."""


class Provisioner(Protocol):
    @property
    def configured(self) -> bool: ...

    def verify(self) -> None: ...

    def cluster_fingerprint(self) -> str | None: ...

    def apply(
        self, namespace: str, import_id: str, objects: list[dict[str, Any]]
    ) -> list[dict[str, str]]: ...

    def remove(self, namespace: str, import_id: str) -> dict[str, Any]: ...

    def namespace_phase(self, namespace: str) -> str: ...


class Reader(Protocol):
    def snapshot(self, namespaces: list[str] | None) -> ClusterSnapshot: ...

    def cluster_fingerprint(self) -> str | None: ...


def to_read(imp: AppImport) -> ImportRead:
    return ImportRead.model_validate(
        {
            "id": imp.id,
            "name": imp.name,
            "source": imp.source,
            "filename": imp.filename,
            "status": imp.status,
            "namespace": imp.namespace,
            "spec": imp.spec,
            "findings": imp.findings,
            "plan": imp.plan,
            "deployment": imp.deployment or {},
            "application_id": imp.application_id,
            "created_at": imp.created_at,
            "updated_at": imp.updated_at,
        }
    )


def create(db: Session, request: ImportRequest, loadgen_image: str) -> AppImport:
    """Save a reviewed, deployable import (status PLANNED). Raises ValueError."""
    existing = db.scalars(
        select(AppImport).where(AppImport.name == request.name)
    ).first()
    if existing is not None:
        if existing.status != "REMOVED":
            raise LifecycleError(f"An import named {request.name!r} exists")
        db.delete(existing)
        db.flush()
    import_id = uuid.uuid4()
    result = preview(request, import_id=str(import_id), loadgen_image=loadgen_image)
    if not result.deployable or result.plan is None or result.spec is None:
        raise ValueError("The import has blocking findings; fix them first")
    imp = AppImport(
        id=import_id,
        name=request.name,
        source=request.source.kind,
        filename=request.source.filename,
        status="PLANNED",
        namespace=result.plan.namespace,
        spec=result.spec.model_dump(mode="json"),
        findings=[f.model_dump(mode="json") for f in result.findings],
        plan=result.plan.model_dump(mode="json"),
        plan_digest=result.plan.digest,
        deployment=DeploymentStatus().model_dump(mode="json"),
    )
    db.add(imp)
    db.commit()
    db.refresh(imp)
    return imp


def _status(imp: AppImport) -> DeploymentStatus:
    return DeploymentStatus.model_validate(imp.deployment or {})


def _save(
    db: Session, imp: AppImport, status: DeploymentStatus, state: str | None = None
) -> None:
    imp.deployment = status.model_dump(mode="json")
    if state is not None:
        imp.status = state
    db.commit()
    db.refresh(imp)


def check_same_cluster(provisioner: Provisioner, reader: Reader) -> None:
    """The provisioner must reach the execution cluster, the one the engine reads."""
    try:
        theirs = provisioner.cluster_fingerprint()
    except ProvisionerError as exc:
        raise ProvisionerUnavailableError(str(exc)) from exc
    ours = reader.cluster_fingerprint()
    if not theirs or theirs != ours:
        raise ProvisionerUnavailableError(
            "The provisioner kubeconfig reaches a different cluster than the engine's "
            "execution context (KUBE_CONTEXT); refusing to deploy there"
        )


def deploy(
    db: Session,
    imp: AppImport,
    digest: str,
    provisioner: Provisioner,
    reader: Reader,
    now: datetime,
) -> AppImport:
    """Apply the approved plan. Raises LifecycleError, ProvisionerUnavailableError."""
    if imp.status not in DEPLOYABLE:
        raise LifecycleError(f"Cannot deploy an import that is {imp.status}")
    if digest != imp.plan_digest:
        raise LifecycleError(
            "The plan changed since it was reviewed; review it again before deploying"
        )
    if imp.namespace in SYSTEM_NAMESPACES or not is_import_namespace(imp.namespace):
        raise LifecycleError(f"{imp.namespace!r} is not an import namespace")
    provisioner.verify()
    check_same_cluster(provisioner, reader)
    plan = DeploymentPlan.model_validate(imp.plan)
    status = _status(imp)
    status.attempts += 1
    status.started_at = now
    status.checked_at = None
    status.finished_at = None
    status.error = None
    status.recovery = None
    status.failing_since = None
    status.workloads = []
    imp.status = "DEPLOYING"
    _save(db, imp, status)
    try:
        status.applied = provisioner.apply(
            imp.namespace, str(imp.id), [o.manifest for o in plan.objects]
        )
    except OwnershipError as exc:
        status.error = str(exc)
        status.recovery = (
            "Nothing that belongs to someone else was changed. Remove the conflicting "
            "objects yourself, or import under another name."
        )
        status.finished_at = now
        _save(db, imp, status, "FAILED")
        return imp
    except (ProvisionerError, ProvisionerUnavailableError) as exc:
        status.error = str(exc)
        status.recovery = (
            "Fix the cause, then retry the deployment, or remove the import."
        )
        status.finished_at = now
        _save(db, imp, status, "FAILED")
        return imp
    _save(db, imp, status)
    return imp


def refresh(
    db: Session,
    imp: AppImport,
    reader: Reader,
    provisioner: Provisioner | None,
    now: datetime,
    timeout_seconds: float,
    execution_context: str | None,
) -> AppImport:
    """One bounded health check (read-only); advances DEPLOYING and REMOVING."""
    status = _status(imp)
    if imp.status == "REMOVING":
        if provisioner is not None and provisioner.configured:
            try:
                phase = provisioner.namespace_phase(imp.namespace)
            except (ProvisionerError, ProvisionerUnavailableError):
                return imp
            status.checked_at = now
            if phase == "absent":
                status.finished_at = now
                _save(db, imp, status, "REMOVED")
            else:
                _save(db, imp, status)
        return imp
    if imp.status not in ("DEPLOYING", "READY"):
        return imp
    plan = DeploymentPlan.model_validate(imp.plan)
    snapshot = reader.snapshot([imp.namespace])
    topology = build_topology(
        snapshot,
        namespaces=[imp.namespace],
        excluded=SYSTEM_NAMESPACES,
        cluster={
            "context": execution_context,
            "role": "execution",
            "chaos_permitted": True,
            "namespaces": None,
        },
    )
    assessment = assess(plan, topology)
    status.workloads = assessment.workloads
    status.checked_at = now
    if imp.status == "READY":
        _save(db, imp, status)
        return imp
    # A failure state must persist for a while before it is a verdict.
    if assessment.failure is None:
        status.failing_since = None
    elif status.failing_since is None:
        status.failing_since = now
    state, failure = verdict(
        assessment, status.started_at or now, status.failing_since, now, timeout_seconds
    )
    if state == "READY":
        status.finished_at = now
        imp.application_id = _link_application(db, imp, execution_context)
        _save(db, imp, status, "READY")
    elif state == "FAILED":
        status.finished_at = now
        detail = next(
            (w.detail for w in assessment.workloads if w.state == failure), ""
        )
        status.error = (
            f"{(failure or 'FAILED').replace('_', ' ').capitalize()}: {detail}".strip()
        )
        status.recovery = RECOVERY.get(failure or "", RECOVERY["PROGRESSING"])
        _save(db, imp, status, "FAILED")
    else:
        _save(db, imp, status)
    return imp


def _link_application(db: Session, imp: AppImport, context: str | None) -> uuid.UUID:
    if imp.application_id is not None:
        existing = db.get(Application, imp.application_id)
        if existing is not None:
            return existing.id
    name = imp.name
    taken = set(db.scalars(select(Application.name)))
    if name in taken:
        name = f"{imp.name} (imported)"
    app = Application(name=name, kube_context=context, namespaces=[imp.namespace])
    db.add(app)
    db.flush()
    return app.id


def remove(
    db: Session,
    imp: AppImport,
    confirm_name: str,
    provisioner: Provisioner,
    now: datetime,
) -> AppImport:
    if confirm_name != imp.name:
        raise LifecycleError("Type the import's name to confirm removal")
    if imp.status not in REMOVABLE:
        raise LifecycleError(f"Cannot remove an import that is {imp.status}")
    status = _status(imp)
    if imp.status == "PLANNED" and status.attempts == 0:
        status.removal = {"namespace": "never-created"}
        status.finished_at = now
        _save(db, imp, status, "REMOVED")
        return imp
    provisioner.verify()
    try:
        result = provisioner.remove(imp.namespace, str(imp.id))
    except OwnershipError as exc:
        status.removal = {"refused": str(exc)}
        _save(db, imp, status)
        raise LifecycleError(str(exc)) from exc
    status.removal = {**result, "requested_at": now.isoformat()}
    if imp.application_id is not None:
        app = db.get(Application, imp.application_id)
        if app is not None:
            db.delete(app)
        imp.application_id = None
    _save(db, imp, status, "REMOVED" if result["namespace"] == "absent" else "REMOVING")
    return imp


def forget(db: Session, imp: AppImport) -> None:
    if imp.status not in ("REMOVED", "PLANNED") or (
        imp.status == "PLANNED" and _status(imp).attempts > 0
    ):
        raise LifecycleError("Remove the deployment first")
    db.delete(imp)
    db.commit()


def target_gate(db: Session, namespace: str, name: str) -> str | None:
    """Why an experiment may not target this workload yet (None: no objection).

    Applies only to import namespaces; validation still runs for every experiment.
    """
    if not is_import_namespace(namespace):
        return None
    imp = db.scalars(select(AppImport).where(AppImport.namespace == namespace)).first()
    if imp is None:
        return f"{namespace} is reserved for imported applications and has no import"
    if imp.status != "READY":
        return (
            f"Import {imp.name} is {imp.status}: imported workloads become experiment "
            "targets only once their deployment is healthy"
        )
    if name == LOADGEN_NAME:
        return "This is AutoResilience's load generator, not part of the application"
    spec = ImportSpec.model_validate(imp.spec)
    if name not in {w.name for w in spec.workloads}:
        return f"{name} is not a workload of import {imp.name}"
    return None
