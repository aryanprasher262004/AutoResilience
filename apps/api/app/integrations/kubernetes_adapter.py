"""Read-only access to the target cluster.

Only get/list calls are made here; nothing in this module may create, patch or delete.
"""

from dataclasses import dataclass
from datetime import datetime
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

    def list_workloads(self) -> list[WorkloadSummary]:
        """Every Deployment and StatefulSet in the cluster, from controller status."""
        apps = client.AppsV1Api(self._client())
        listings = (
            (WorkloadKind.DEPLOYMENT, apps.list_deployment_for_all_namespaces),
            (WorkloadKind.STATEFULSET, apps.list_stateful_set_for_all_namespaces),
        )
        try:
            return [
                _summary(kind, item)
                for kind, list_all in listings
                for item in list_all(_request_timeout=self._timeout).items
            ]
        except ApiException as exc:
            raise ClusterUnavailableError(
                f"Kubernetes API error {exc.status}: {exc.reason}"
            ) from exc
        except (ConfigException, HTTPError, OSError) as exc:
            raise ClusterUnavailableError(f"Kubernetes API unreachable: {exc}") from exc

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
