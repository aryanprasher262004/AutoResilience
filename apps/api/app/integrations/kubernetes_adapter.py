"""Read-only access to the target cluster.

Only get/list calls are made here; nothing in this module may create, patch or delete.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from kubernetes import client, config
from kubernetes.client.exceptions import ApiException
from kubernetes.config.config_exception import ConfigException
from urllib3.exceptions import HTTPError

from app.domain.experiment import ExperimentTarget, WorkloadKind


@dataclass(frozen=True)
class WorkloadStatus:
    desired_replicas: int
    running_pods: int
    # Running, Ready and not terminating: the pods actually serving traffic.
    ready_pods: int
    # The workload's pod selector and its ready pods (used to scope fault injection).
    selector: str = ""
    ready_pod_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class WorkloadSummary:
    """A Deployment/StatefulSet as its controller reports it (what `kubectl get` shows)."""

    namespace: str
    kind: WorkloadKind
    name: str
    desired_replicas: int
    # status.replicas: pods the controller currently has, ready or not.
    current_replicas: int
    ready_replicas: int
    available_replicas: int
    created_at: datetime | None


class ClusterUnavailableError(Exception):
    """Kubernetes data could not be obtained (config, network, auth or server error)."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        # HTTP status from the API server; None when it was not reached at all.
        self.status = status


# Resources a topology snapshot lists, in this order. Namespaced unless noted.
SNAPSHOT_RESOURCES = (
    "deployments",
    "replicasets",
    "statefulsets",
    "pods",
    "services",
    "endpointslices",
    "events",
    "nodes",  # cluster-scoped
)
# Per listing; anything beyond is reported as truncated, never silently dropped.
SNAPSHOT_LIMIT = 2000
EVENT_LIMIT = 500


@dataclass(frozen=True)
class ListingError:
    """One resource listing the API server refused or failed (the rest may be fine)."""

    resource: str
    namespace: str | None
    status: int | None
    reason: str


@dataclass(frozen=True)
class ClusterSnapshot:
    """Raw Kubernetes JSON objects (as `kubectl get -o json` returns them) per resource.

    Only the topology builder reads these, through an explicit field allowlist.
    """

    observed_at: datetime
    objects: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    errors: list[ListingError] = field(default_factory=list)
    # Resources (and namespace, None for all) that had more objects than the limit.
    truncated: list[tuple[str, str | None]] = field(default_factory=list)


class KubernetesAdapter:
    def __init__(self, context: str | None, request_timeout: float) -> None:
        self._context = context
        self._timeout = request_timeout
        self._api_client: Any = None

    def get_workload_status(self, target: ExperimentTarget) -> WorkloadStatus | None:
        """Return the workload's replica/pod status, or None if it does not exist."""
        try:
            workload = self._read_workload(target)
            if workload is None:
                return None
            selector = label_selector_to_string(workload.spec.selector)
            pods = client.CoreV1Api(self._client()).list_namespaced_pod(
                target.namespace,
                label_selector=selector,
                _request_timeout=self._timeout,
            )
        except ApiException as exc:
            raise ClusterUnavailableError(
                f"Kubernetes API error {exc.status}: {exc.reason}"
            ) from exc
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc

        ready = sorted(p.metadata.name for p in pods.items if _is_ready(p))
        return WorkloadStatus(
            desired_replicas=workload.spec.replicas or 0,
            running_pods=sum(1 for p in pods.items if _is_running(p)),
            ready_pods=len(ready),
            selector=selector,
            ready_pod_names=tuple(ready),
        )

    def list_workloads(self, namespace: str | None = None) -> list[WorkloadSummary]:
        """Deployments and StatefulSets, from controller status.

        All namespaces by default; with `namespace`, only that one (what a
        namespace-scoped, read-only identity is allowed to list).
        """
        apps = client.AppsV1Api(self._client())
        if namespace is None:
            listings: tuple[tuple[WorkloadKind, Callable[..., Any]], ...] = (
                (WorkloadKind.DEPLOYMENT, apps.list_deployment_for_all_namespaces),
                (WorkloadKind.STATEFULSET, apps.list_stateful_set_for_all_namespaces),
            )
            args: tuple[str, ...] = ()
        else:
            listings = (
                (WorkloadKind.DEPLOYMENT, apps.list_namespaced_deployment),
                (WorkloadKind.STATEFULSET, apps.list_namespaced_stateful_set),
            )
            args = (namespace,)
        try:
            return [
                _summary(kind, item)
                for kind, list_fn in listings
                for item in list_fn(*args, _request_timeout=self._timeout).items
            ]
        except ApiException as exc:
            raise ClusterUnavailableError(
                f"Kubernetes API error {exc.status}: {exc.reason}", exc.status
            ) from exc
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc

    def list_namespaces(self) -> list[str]:
        """Names of all namespaces (needs cluster-wide list on namespaces)."""
        try:
            items = (
                client.CoreV1Api(self._client())
                .list_namespace(_request_timeout=self._timeout)
                .items
            )
        except ApiException as exc:
            raise ClusterUnavailableError(
                f"Kubernetes API error {exc.status}: {exc.reason}", exc.status
            ) from exc
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc
        return sorted(item.metadata.name for item in items)

    def snapshot(self, namespaces: list[str] | None) -> ClusterSnapshot:
        """Read-only listing of everything the topology shows.

        `namespaces=None` lists across all namespaces; otherwise each namespace is
        listed on its own. A refused listing (e.g. 403) is recorded and the others
        continue; an unreachable API server raises ClusterUnavailableError.
        """
        api = self._client()
        apps, core = client.AppsV1Api(api), client.CoreV1Api(api)
        discovery = client.DiscoveryV1Api(api)
        listers: dict[str, tuple[Callable[..., Any], Callable[..., Any]]] = {
            "deployments": (
                apps.list_namespaced_deployment,
                apps.list_deployment_for_all_namespaces,
            ),
            "replicasets": (
                apps.list_namespaced_replica_set,
                apps.list_replica_set_for_all_namespaces,
            ),
            "statefulsets": (
                apps.list_namespaced_stateful_set,
                apps.list_stateful_set_for_all_namespaces,
            ),
            "pods": (core.list_namespaced_pod, core.list_pod_for_all_namespaces),
            "services": (
                core.list_namespaced_service,
                core.list_service_for_all_namespaces,
            ),
            "endpointslices": (
                discovery.list_namespaced_endpoint_slice,
                discovery.list_endpoint_slice_for_all_namespaces,
            ),
            "events": (core.list_namespaced_event, core.list_event_for_all_namespaces),
        }
        snapshot = ClusterSnapshot(observed_at=datetime.now(UTC))
        for resource in SNAPSHOT_RESOURCES:
            snapshot.objects[resource] = []
            limit = EVENT_LIMIT if resource == "events" else SNAPSHOT_LIMIT
            if resource == "nodes":
                calls: list[tuple[str | None, Callable[..., Any], tuple[str, ...]]] = [
                    (None, core.list_node, ())
                ]
            elif namespaces is None:
                calls = [(None, listers[resource][1], ())]
            else:
                calls = [(ns, listers[resource][0], (ns,)) for ns in namespaces]
            for namespace, list_fn, args in calls:
                self._list_raw(snapshot, resource, namespace, list_fn, args, limit)
        return snapshot

    def _list_raw(
        self,
        snapshot: ClusterSnapshot,
        resource: str,
        namespace: str | None,
        list_fn: Callable[..., Any],
        args: tuple[str, ...],
        limit: int,
    ) -> None:
        try:
            response = list_fn(
                *args,
                limit=limit,
                _request_timeout=self._timeout,
                _preload_content=False,
            )
            body = json.loads(response.data)
        except ApiException as exc:
            snapshot.errors.append(
                ListingError(resource, namespace, exc.status, str(exc.reason))
            )
            return
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc
        except ValueError as exc:  # not JSON: record, do not guess
            snapshot.errors.append(
                ListingError(resource, namespace, None, f"unreadable response: {exc}")
            )
            return
        items = body.get("items") if isinstance(body, dict) else None
        if not isinstance(items, list):
            snapshot.errors.append(
                ListingError(resource, namespace, None, "response has no item list")
            )
            return
        snapshot.objects[resource].extend(i for i in items if isinstance(i, dict))
        if (body.get("metadata") or {}).get("continue"):
            snapshot.truncated.append((resource, namespace))

    def live_pod_names(self, namespace: str, names: list[str]) -> set[str]:
        """Which of the named pods still exist and are not terminating."""
        try:
            pods = client.CoreV1Api(self._client()).list_namespaced_pod(
                namespace, _request_timeout=self._timeout
            )
        except ApiException as exc:
            raise ClusterUnavailableError(
                f"Kubernetes API error {exc.status}: {exc.reason}"
            ) from exc
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc
        wanted = set(names)
        return {
            p.metadata.name
            for p in pods.items
            if p.metadata.name in wanted and p.metadata.deletion_timestamp is None
        }

    def _read_workload(self, target: ExperimentTarget) -> Any:
        apps = client.AppsV1Api(self._client())
        read = {
            WorkloadKind.DEPLOYMENT: apps.read_namespaced_deployment,
            WorkloadKind.STATEFULSET: apps.read_namespaced_stateful_set,
        }[target.kind]
        try:
            return read(target.name, target.namespace, _request_timeout=self._timeout)
        except ApiException as exc:
            if exc.status == 404:
                return None
            raise

    def _client(self) -> Any:
        # Loaded lazily so the API starts (and tests run) without a kubeconfig.
        if self._api_client is None:
            self._api_client = config.new_client_from_config(context=self._context)
        return self._api_client


def label_selector_to_string(selector: Any) -> str:
    parts = [f"{k}={v}" for k, v in sorted((selector.match_labels or {}).items())]
    for expr in selector.match_expressions or []:
        values = ",".join(sorted(expr.values or []))
        parts.append(
            {
                "In": f"{expr.key} in ({values})",
                "NotIn": f"{expr.key} notin ({values})",
                "Exists": expr.key,
                "DoesNotExist": f"!{expr.key}",
            }[expr.operator]
        )
    if not parts:
        # An empty selector would match every pod in the namespace.
        raise ClusterUnavailableError("Workload has an empty pod selector")
    return ",".join(parts)


def _summary(kind: WorkloadKind, item: Any) -> WorkloadSummary:
    status = item.status
    return WorkloadSummary(
        namespace=item.metadata.namespace,
        kind=kind,
        name=item.metadata.name,
        desired_replicas=item.spec.replicas or 0,
        current_replicas=(status and status.replicas) or 0,
        ready_replicas=(status and status.ready_replicas) or 0,
        available_replicas=(status and status.available_replicas) or 0,
        created_at=item.metadata.creation_timestamp,
    )


def _is_running(pod: Any) -> bool:
    return pod.status.phase == "Running" and pod.metadata.deletion_timestamp is None


def _is_ready(pod: Any) -> bool:
    return _is_running(pod) and any(
        c.type == "Ready" and c.status == "True" for c in pod.status.conditions or []
    )
