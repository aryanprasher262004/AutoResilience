from types import SimpleNamespace as NS
from typing import Any
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import MaxRetryError

from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.integrations import kubernetes_adapter
from app.integrations.kubernetes_adapter import (
    ClusterUnavailableError,
    KubernetesAdapter,
    WorkloadStatus,
    label_selector_to_string,
)

DEPLOYMENT = ExperimentTarget("shop", WorkloadKind.DEPLOYMENT, "frontend")
STATEFULSET = ExperimentTarget("shop", WorkloadKind.STATEFULSET, "cart-redis")


def workload(replicas: int = 3, labels: dict[str, str] | None = None) -> NS:
    selector = NS(match_labels=labels or {"app": "frontend"}, match_expressions=None)
    return NS(spec=NS(replicas=replicas, selector=selector))


def pod(phase: str = "Running", ready: bool = True, terminating: bool = False) -> NS:
    return NS(
        metadata=NS(deletion_timestamp="2026-01-01T00:00:00Z" if terminating else None),
        status=NS(
            phase=phase,
            conditions=[NS(type="Ready", status="True" if ready else "False")],
        ),
    )


@pytest.fixture
def apis(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    apps, core = MagicMock(), MagicMock()
    monkeypatch.setattr(
        kubernetes_adapter.config, "new_client_from_config", MagicMock()
    )
    monkeypatch.setattr(kubernetes_adapter.client, "AppsV1Api", lambda _: apps)
    monkeypatch.setattr(kubernetes_adapter.client, "CoreV1Api", lambda _: core)
    return apps, core


def adapter() -> KubernetesAdapter:
    return KubernetesAdapter(context="kind-autoresilience", request_timeout=5)


def assert_read_only(*mocks: MagicMock) -> None:
    for mock in mocks:
        for name, _, _ in mock.method_calls:
            assert name.startswith(("read_", "list_")), f"non read-only call: {name}"


def test_counts_running_and_ready_pods(apis: tuple[MagicMock, MagicMock]) -> None:
    apps, core = apis
    apps.read_namespaced_deployment.return_value = workload(replicas=4)
    core.list_namespaced_pod.return_value = NS(
        items=[
            pod(),
            pod(),
            pod(ready=False),  # running, not ready
            pod(terminating=True),  # being deleted
            pod(phase="Pending", ready=False),
        ]
    )

    status = adapter().get_workload_status(DEPLOYMENT)

    assert status == WorkloadStatus(desired_replicas=4, running_pods=3, ready_pods=2)
    apps.read_namespaced_deployment.assert_called_once_with(
        "frontend", "shop", _request_timeout=5
    )
    core.list_namespaced_pod.assert_called_once_with(
        "shop", label_selector="app=frontend", _request_timeout=5
    )
    assert_read_only(apps, core)


def test_statefulset_uses_statefulset_api(apis: tuple[MagicMock, MagicMock]) -> None:
    apps, core = apis
    apps.read_namespaced_stateful_set.return_value = workload(1, {"app": "cart-redis"})
    core.list_namespaced_pod.return_value = NS(items=[pod()])

    assert adapter().get_workload_status(STATEFULSET) == WorkloadStatus(1, 1, 1)
    apps.read_namespaced_deployment.assert_not_called()


def test_not_found_returns_none(apis: tuple[MagicMock, MagicMock]) -> None:
    apps, core = apis
    apps.read_namespaced_deployment.side_effect = ApiException(status=404, reason="NF")

    assert adapter().get_workload_status(DEPLOYMENT) is None
    core.list_namespaced_pod.assert_not_called()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ApiException(status=403, reason="Forbidden"), "Kubernetes API error 403"),
        (ApiException(status=500, reason="Internal"), "Kubernetes API error 500"),
        (MaxRetryError(None, "/apis", "refused"), "Kubernetes API unreachable"),  # type: ignore[arg-type]
        (ConnectionRefusedError("refused"), "Kubernetes API unreachable"),
    ],
)
def test_api_failures_raise_cluster_unavailable(
    apis: tuple[MagicMock, MagicMock], error: Exception, expected: str
) -> None:
    apps, _ = apis
    apps.read_namespaced_deployment.side_effect = error

    with pytest.raises(ClusterUnavailableError, match=expected):
        adapter().get_workload_status(DEPLOYMENT)


def test_pod_list_failure_raises_cluster_unavailable(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    apps, core = apis
    apps.read_namespaced_deployment.return_value = workload()
    core.list_namespaced_pod.side_effect = ApiException(
        status=503, reason="Unavailable"
    )

    with pytest.raises(ClusterUnavailableError, match="503"):
        adapter().get_workload_status(DEPLOYMENT)


def test_missing_kubeconfig_context_raises_cluster_unavailable() -> None:
    bad = KubernetesAdapter(context="no-such-context-for-tests", request_timeout=1)
    with pytest.raises(ClusterUnavailableError, match="unreachable"):
        bad.get_workload_status(DEPLOYMENT)


def expr(key: str, operator: str, values: list[str] | None = None) -> Any:
    return NS(key=key, operator=operator, values=values)


def test_label_selector_to_string() -> None:
    selector = NS(
        match_labels={"tier": "web", "app": "shop"},
        match_expressions=[
            expr("env", "In", ["prod", "dev"]),
            expr("canary", "NotIn", ["true"]),
            expr("team", "Exists"),
            expr("legacy", "DoesNotExist"),
        ],
    )
    assert label_selector_to_string(selector) == (
        "app=shop,tier=web,env in (dev,prod),canary notin (true),team,!legacy"
    )


def test_empty_selector_is_rejected() -> None:
    with pytest.raises(ClusterUnavailableError, match="empty pod selector"):
        label_selector_to_string(NS(match_labels=None, match_expressions=None))
