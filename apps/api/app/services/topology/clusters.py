"""Which clusters this engine may read, and what it may do there.

Exactly two sources, both operator configuration outside the API:
  - the execution context (KUBE_CONTEXT): discovery in every non-system namespace,
    and the only cluster experiments ever run on;
  - DISCOVERY_CLUSTERS: further contexts, read-only, limited to listed namespaces.

The API can only choose among these; it cannot add a context or a namespace.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.core.config import Settings
from app.domain.safety_policy import SYSTEM_NAMESPACES
from app.integrations.kubernetes_adapter import (
    ClusterSnapshot,
    ClusterUnavailableError,
    KubernetesAdapter,
    WorkloadSummary,
)
from app.services.topology.graph import build_topology

Role = Literal["execution", "discovery"]


class ClusterReader(Protocol):
    def list_workloads(self, namespace: str | None = None) -> list[WorkloadSummary]: ...

    def list_namespaces(self) -> list[str]: ...

    def snapshot(self, namespaces: list[str] | None) -> ClusterSnapshot: ...


class UnknownClusterError(Exception):
    """The context is not one this engine was configured to read."""


class ScopeError(Exception):
    """A namespace outside what this cluster's access allows."""


@dataclass(frozen=True)
class ClusterAccess:
    # None only in development, when KUBE_CONTEXT is unset (current-context fallback).
    context: str | None
    role: Role
    # None: every namespace outside SYSTEM_NAMESPACES.
    namespaces: tuple[str, ...] | None

    @property
    def chaos_permitted(self) -> bool:
        return self.role == "execution"

    def describe(self) -> dict[str, Any]:
        return {
            "context": self.context,
            "role": self.role,
            "chaos_permitted": self.chaos_permitted,
            "namespaces": list(self.namespaces)
            if self.namespaces is not None
            else None,
        }


class ClusterRegistry:
    def __init__(
        self,
        settings: Settings,
        execution: ClusterReader,
        factory: Callable[[str], ClusterReader] | None = None,
    ) -> None:
        self.execution = ClusterAccess(settings.kube_context, "execution", None)
        self.discovery = [
            ClusterAccess(c.context, "discovery", tuple(c.namespaces))
            for c in settings.discovery_clusters
        ]
        self._readers: dict[str | None, ClusterReader] = {
            settings.kube_context: execution
        }
        timeout = settings.kube_request_timeout_seconds
        self._factory = factory or (lambda ctx: KubernetesAdapter(ctx, timeout))

    def clusters(self) -> list[ClusterAccess]:
        return [self.execution, *self.discovery]

    def resolve(self, context: str | None) -> ClusterAccess:
        """None or the execution context name: the execution cluster."""
        if context is None or context == self.execution.context:
            return self.execution
        for access in self.discovery:
            if access.context == context:
                return access
        raise UnknownClusterError(
            f"Context {context!r} is not authorized for this engine "
            "(KUBE_CONTEXT or DISCOVERY_CLUSTERS)"
        )

    def reader(self, access: ClusterAccess) -> ClusterReader:
        if access.context not in self._readers:
            assert access.context is not None
            self._readers[access.context] = self._factory(access.context)
        return self._readers[access.context]


def check_scope(access: ClusterAccess, namespaces: list[str]) -> list[str] | None:
    """The namespaces to read, or None for all permitted ones. Raises ScopeError."""
    for namespace in namespaces:
        if namespace in SYSTEM_NAMESPACES:
            raise ScopeError(f"{namespace!r} is a system namespace")
        if access.namespaces is not None and namespace not in access.namespaces:
            raise ScopeError(
                f"{namespace!r} is not among the namespaces granted for context "
                f"{access.context!r}: {', '.join(access.namespaces)}"
            )
    if namespaces:
        return sorted(set(namespaces))
    return list(access.namespaces) if access.namespaces is not None else None


def list_namespaces(access: ClusterAccess, reader: ClusterReader) -> dict[str, Any]:
    """Namespaces offered for onboarding, each with its workload count or access error.

    Raises ClusterUnavailableError when the cluster cannot be reached at all.
    """
    items: list[dict[str, Any]] = []
    if access.namespaces is not None:
        source = "configured"
        for namespace in access.namespaces:
            try:
                count: int | None = len(reader.list_workloads(namespace))
                status, detail = "readable", f"{count} workloads"
            except ClusterUnavailableError as exc:
                if exc.status is None:
                    raise
                count = None
                status = "forbidden" if exc.status in (401, 403) else "error"
                detail = str(exc)
            items.append(_namespace(namespace, count, status, detail))
        return _namespaces(access, source, items)

    workloads = reader.list_workloads()
    per_namespace: dict[str, int] = {}
    for w in workloads:
        per_namespace[w.namespace] = per_namespace.get(w.namespace, 0) + 1
    try:
        names = reader.list_namespaces()
        source = "namespaces"
    except ClusterUnavailableError as exc:
        if exc.status not in (401, 403):
            raise
        # Older engine grants cannot list namespaces: offer those with workloads.
        names = sorted(per_namespace)
        source = "workloads"
    for namespace in names:
        if namespace in SYSTEM_NAMESPACES:
            continue
        count = per_namespace.get(namespace, 0)
        items.append(_namespace(namespace, count, "readable", f"{count} workloads"))
    return _namespaces(access, source, items)


def _namespace(
    name: str, count: int | None, status: str, detail: str
) -> dict[str, Any]:
    return {"name": name, "workloads": count, "access": status, "detail": detail}


def _namespaces(
    access: ClusterAccess, source: str, items: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "cluster": access.describe(),
        "source": source,
        "items": items,
        "excluded_namespaces": sorted(SYSTEM_NAMESPACES),
    }


def topology(
    access: ClusterAccess, reader: ClusterReader, namespaces: list[str]
) -> dict[str, Any]:
    """Raises ScopeError or ClusterUnavailableError."""
    scope = check_scope(access, namespaces)
    snapshot = reader.snapshot(scope)
    return build_topology(
        snapshot,
        namespaces=scope,
        excluded=SYSTEM_NAMESPACES,
        cluster=access.describe(),
    )
