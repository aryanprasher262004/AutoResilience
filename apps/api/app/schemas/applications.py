import re
import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.schemas.topology import ClusterRef

_NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class ApplicationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    # None: the engine's execution cluster. Otherwise a context from GET /clusters.
    context: str | None = Field(default=None, max_length=253)
    namespaces: list[str] = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def _strip(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()

    @field_validator("namespaces")
    @classmethod
    def _namespaces(cls, values: list[str]) -> list[str]:
        for value in values:
            if len(value) > 63 or not _NAMESPACE.match(value):
                raise ValueError(f"{value!r} is not a namespace name")
        return sorted(set(values))


class ApplicationRead(BaseModel):
    id: uuid.UUID
    name: str
    context: str | None
    namespaces: list[str]
    # The cluster as currently authorized; None if the context no longer is
    # (KUBE_CONTEXT or DISCOVERY_CLUSTERS changed since onboarding).
    cluster: ClusterRef | None
    created_at: datetime
    updated_at: datetime


class ApplicationList(BaseModel):
    items: list[ApplicationRead]
