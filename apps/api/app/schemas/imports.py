"""Application imports (P7, docs/imports.md): input, findings, normalized spec, plan.

Responses never contain environment values, file contents beyond what the plan
deploys, or anything read from the host: the API receives file text in the request
body and never opens a path.
"""

import re
import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.services.imports.safe_yaml import MAX_BYTES

# Lowercase DNS label, short enough for the namespace prefix (ar-imp-<name>).
IMPORT_NAME = re.compile(r"^[a-z]([-a-z0-9]{0,28}[a-z0-9])?$")
SOURCE_NAME = re.compile(r"^[A-Za-z0-9._ -]{1,100}$")
# An absolute path of plain segments: no query, fragment, credentials or "..".
HTTP_PATH = re.compile(r"^/(?:[A-Za-z0-9._~-]+/?)*$")

SourceKind = Literal["compose", "manifests", "image"]
Severity = Literal["blocking", "warning", "info"]
ImportStatus = Literal["PLANNED", "DEPLOYING", "READY", "FAILED", "REMOVING", "REMOVED"]


class ImageSource(BaseModel):
    """One container image, deployed as a Deployment (+ a Service when `port` is set)."""

    image: str = Field(min_length=1, max_length=255)
    port: int | None = Field(default=None, ge=1, le=65535)
    replicas: int = Field(default=2, ge=1, le=5)


class ImportSource(BaseModel):
    kind: SourceKind
    # Shown only (sanitized); the API never opens it.
    filename: str | None = Field(default=None, max_length=255)
    # compose / manifests: the file's text.
    content: str | None = Field(default=None, max_length=MAX_BYTES)
    image: ImageSource | None = None

    @field_validator("filename")
    @classmethod
    def _basename(cls, value: str | None) -> str | None:
        if value is None:
            return None
        # A browser sends a bare name; anything path-like keeps only its last part.
        base = re.split(r"[\\/]", value)[-1].strip()
        return base if SOURCE_NAME.match(base) else None


class TrafficTarget(BaseModel):
    """A load-generator endpoint: a Service of this import, one of its ports, a path."""

    service: str = Field(min_length=1, max_length=63)
    port: int = Field(ge=1, le=65535)
    path: str = Field(default="/", max_length=200)

    @field_validator("path")
    @classmethod
    def _path(cls, value: str) -> str:
        if not HTTP_PATH.match(value) or ".." in value.split("/"):
            raise ValueError(
                "must be an absolute path like /healthz (letters, digits, . _ ~ - and /)"
            )
        return value


class ImportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=30)
    source: ImportSource
    traffic: list[TrafficTarget] = Field(default_factory=list, max_length=5)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not IMPORT_NAME.match(value):
            raise ValueError(
                "use 1-30 lowercase letters, digits and '-', starting with a letter"
            )
        return value


class Finding(BaseModel):
    severity: Severity
    # Stable machine code, e.g. "host_path_volume".
    code: str
    # What it is about, e.g. "service web" or "Deployment api".
    subject: str | None = None
    # Where in the input, e.g. "services.web.volumes[0]".
    path: str | None = None
    message: str
    hint: str | None = None


class PortSpec(BaseModel):
    container_port: int
    protocol: Literal["TCP", "UDP"] = "TCP"
    name: str | None = None


class ProbeSpec(BaseModel):
    type: Literal["exec", "http", "tcp", "grpc"]
    command: list[str] | None = None
    path: str | None = None
    port: int | str | None = None
    initial_delay_seconds: int = 0
    period_seconds: int = 10
    timeout_seconds: int = 1
    failure_threshold: int = 3
    # Added by AutoResilience (no check was declared), not taken from the input.
    generated: bool = False


class Resources(BaseModel):
    cpu_request: str
    memory_request: str
    cpu_limit: str
    memory_limit: str


class VolumeSpec(BaseModel):
    """Always an emptyDir: nothing on the host, data lost when the Pod goes."""

    name: str
    mount_path: str
    read_only: bool = False
    memory: bool = False


class WorkloadSpec(BaseModel):
    name: str
    kind: Literal["Deployment", "StatefulSet"] = "Deployment"
    image: str
    replicas: int
    command: list[str] | None = None
    args: list[str] | None = None
    working_dir: str | None = None
    ports: list[PortSpec] = []
    readiness: ProbeSpec | None = None
    liveness: ProbeSpec | None = None
    startup: ProbeSpec | None = None
    resources: Resources
    volumes: list[VolumeSpec] = []
    read_only_root: bool = False
    drop_all_capabilities: bool = False
    run_as_non_root: bool | None = None
    run_as_user: int | None = None
    termination_grace_seconds: int | None = None
    # Pod labels (validated); the import's ownership labels are added on top.
    labels: dict[str, str]
    # The workload's selector (a subset of `labels`).
    selector: dict[str, str]
    # StatefulSets: the governing Service.
    service_name: str | None = None
    # Declared in the input but not set in the test deployment (values never kept).
    env_names: list[str] = []


class ServicePortSpec(BaseModel):
    name: str | None = None
    port: int
    target_port: int | str
    protocol: Literal["TCP", "UDP"] = "TCP"


class ServiceSpec(BaseModel):
    name: str
    # The workload whose Pods it selects (exactly one).
    workload: str
    headless: bool = False
    ports: list[ServicePortSpec]


class DeclaredRelation(BaseModel):
    """A relationship the input file states. Never verified, never traffic."""

    source: str
    target: str
    type: Literal["depends_on", "network"]
    detail: str


class ImportSpec(BaseModel):
    source: SourceKind
    workloads: list[WorkloadSpec]
    services: list[ServiceSpec]
    declared: list[DeclaredRelation] = []
    networks: list[str] = []


class PlannedObject(BaseModel):
    api_version: str
    kind: str
    name: str
    namespace: str | None
    # Why it is created, in a sentence.
    purpose: str
    # application | isolation | chaos | load-generator
    group: Literal["application", "isolation", "chaos", "load-generator"]
    manifest: dict[str, Any]


class DeploymentPlan(BaseModel):
    namespace: str
    objects: list[PlannedObject]
    # sha256 of the canonical JSON of the manifests; the deploy call must quote it.
    digest: str
    # What deploying will do, and what it will never do.
    actions: list[str]
    guarantees: list[str]
    traffic: list[TrafficTarget]


class ImportPreview(BaseModel):
    name: str
    source: SourceKind
    filename: str | None
    spec: ImportSpec | None
    findings: list[Finding]
    deployable: bool
    plan: DeploymentPlan | None


class WorkloadHealth(BaseModel):
    name: str
    kind: str
    # READY | PROGRESSING | IMAGE_PULL_FAILED | CRASH_LOOP | CONFIG_ERROR | MISSING
    state: str
    ready: int
    desired: int
    detail: str


class DeploymentStatus(BaseModel):
    attempts: int = 0
    started_at: datetime | None = None
    checked_at: datetime | None = None
    finished_at: datetime | None = None
    # When the current failure state was first seen (a short blip is no verdict).
    failing_since: datetime | None = None
    # Why it failed, in a sentence, and what to do.
    error: str | None = None
    recovery: str | None = None
    workloads: list[WorkloadHealth] = []
    applied: list[dict[str, str]] = []
    removal: dict[str, Any] | None = None


class ImportRead(BaseModel):
    id: uuid.UUID
    name: str
    source: SourceKind
    filename: str | None
    status: ImportStatus
    namespace: str
    spec: ImportSpec
    findings: list[Finding]
    plan: DeploymentPlan
    deployment: DeploymentStatus
    # The onboarded application (topology view), once the deployment is healthy.
    application_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class ImportList(BaseModel):
    items: list[ImportRead]


class DeployRequest(BaseModel):
    # The digest of the plan the user reviewed; a changed plan is refused.
    plan_digest: str = Field(min_length=64, max_length=64)
    confirm: Literal[True]


class RemoveRequest(BaseModel):
    # Typed by the user: the import's name.
    confirm_name: str = Field(min_length=1, max_length=30)


class ProvisionerInfo(BaseModel):
    configured: bool
    context: str | None
    detail: str


class ImportCapabilities(BaseModel):
    provisioner: ProvisionerInfo
    # The execution cluster, where imports are deployed.
    execution_context: str | None
    max_bytes: int
    max_documents: int
    max_workloads: int
    max_replicas: int
    namespace_prefix: str
    compose_keys: list[str]
    manifest_kinds: list[str]
