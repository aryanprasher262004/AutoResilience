import json
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
    WorkloadSummary,
    label_selector_to_string,
)

DEPLOYMENT = ExperimentTarget("shop", WorkloadKind.DEPLOYMENT, "frontend")
STATEFULSET = ExperimentTarget("shop", WorkloadKind.STATEFULSET, "cart-redis")


def workload(replicas: int = 3, labels: dict[str, str] | None = None) -> NS:
    selector = NS(match_labels=labels or {"app": "frontend"}, match_expressions=None)
    return NS(spec=NS(replicas=replicas, selector=selector))


def pod(
    phase: str = "Running",
    ready: bool = True,
    terminating: bool = False,
    name: str = "frontend-abc-12345",
) -> NS:
    return NS(
        metadata=NS(
            name=name,
            deletion_timestamp="2026-01-01T00:00:00Z" if terminating else None,
        ),
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
            pod(name="frontend-b"),
            pod(name="frontend-a"),
            pod(ready=False, name="frontend-c"),  # running, not ready
            pod(terminating=True, name="frontend-d"),  # being deleted
            pod(phase="Pending", ready=False, name="frontend-e"),
        ]
    )

    status = adapter().get_workload_status(DEPLOYMENT)

    assert status == WorkloadStatus(
        desired_replicas=4,
        running_pods=3,
        ready_pods=2,
        selector="app=frontend",
        ready_pod_names=("frontend-a", "frontend-b"),
    )
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

    status = adapter().get_workload_status(STATEFULSET)
    assert status is not None
    assert (status.desired_replicas, status.ready_pods) == (1, 1)
    assert status.selector == "app=cart-redis"
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


def test_live_pod_names_excludes_missing_and_terminating(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    apps, core = apis
    core.list_namespaced_pod.return_value = NS(
        items=[
            pod(name="checkout-a"),
            pod(name="checkout-b", terminating=True),
            pod(name="other"),
        ]
    )

    live = adapter().live_pod_names("shop", ["checkout-a", "checkout-b", "checkout-c"])

    assert live == {"checkout-a"}
    assert_read_only(apps, core)


def test_live_pod_names_failure_raises(apis: tuple[MagicMock, MagicMock]) -> None:
    _, core = apis
    core.list_namespaced_pod.side_effect = ApiException(status=500, reason="boom")
    with pytest.raises(ClusterUnavailableError, match="500"):
        adapter().live_pod_names("shop", ["x"])


def listed(namespace: str, name: str, replicas: int, status: NS | None) -> NS:
    return NS(
        metadata=NS(namespace=namespace, name=name, creation_timestamp=None),
        spec=NS(replicas=replicas),
        status=status,
    )


def test_list_workloads_reads_controller_status(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    apps, core = apis
    apps.list_deployment_for_all_namespaces.return_value = NS(
        items=[
            listed(
                "shop",
                "checkout",
                2,
                NS(replicas=3, ready_replicas=1, available_replicas=1),
            ),
            # Fresh/scaled-down controllers leave status fields unset.
            listed(
                "shop",
                "idle",
                0,
                NS(replicas=None, ready_replicas=None, available_replicas=None),
            ),
        ]
    )
    apps.list_stateful_set_for_all_namespaces.return_value = NS(
        items=[listed("shop", "cart-redis", 1, None)]
    )

    workloads = adapter().list_workloads()

    assert workloads == [
        WorkloadSummary("shop", WorkloadKind.DEPLOYMENT, "checkout", 2, 3, 1, 1, None),
        WorkloadSummary("shop", WorkloadKind.DEPLOYMENT, "idle", 0, 0, 0, 0, None),
        WorkloadSummary(
            "shop", WorkloadKind.STATEFULSET, "cart-redis", 1, 0, 0, 0, None
        ),
    ]
    apps.list_deployment_for_all_namespaces.assert_called_once_with(_request_timeout=5)
    assert_read_only(apps, core)


def test_list_workloads_unreachable(apis: tuple[MagicMock, MagicMock]) -> None:
    apps, _ = apis
    apps.list_deployment_for_all_namespaces.side_effect = ApiException(403, "Forbidden")

    with pytest.raises(ClusterUnavailableError, match="403"):
        adapter().list_workloads()


# --- topology reads (P6) ------------------------------------------------------------


@pytest.fixture
def all_apis(
    monkeypatch: pytest.MonkeyPatch, apis: tuple[MagicMock, MagicMock]
) -> tuple[MagicMock, MagicMock, MagicMock]:
    discovery = MagicMock()
    monkeypatch.setattr(
        kubernetes_adapter.client, "DiscoveryV1Api", lambda _: discovery
    )
    apps, core = apis
    for mock in (apps, core, discovery):
        mock.configure_mock(
            **{
                f"{name}.return_value": raw([])
                for name in (
                    "list_namespaced_deployment",
                    "list_deployment_for_all_namespaces",
                    "list_namespaced_replica_set",
                    "list_replica_set_for_all_namespaces",
                    "list_namespaced_stateful_set",
                    "list_stateful_set_for_all_namespaces",
                    "list_namespaced_pod",
                    "list_pod_for_all_namespaces",
                    "list_namespaced_service",
                    "list_service_for_all_namespaces",
                    "list_namespaced_endpoint_slice",
                    "list_endpoint_slice_for_all_namespaces",
                    "list_namespaced_event",
                    "list_event_for_all_namespaces",
                    "list_node",
                )
            }
        )
    return apps, core, discovery


def raw(items: list[dict[str, Any]], more: bool = False) -> NS:
    body = {"items": items, "metadata": {"continue": "abc" if more else ""}}
    return NS(data=json.dumps(body).encode())


def test_snapshot_lists_every_resource_read_only(
    all_apis: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    apps, core, discovery = all_apis
    core.list_pod_for_all_namespaces.return_value = raw([{"metadata": {"name": "p"}}])
    snap = adapter().snapshot(None)
    assert snap.objects["pods"] == [{"metadata": {"name": "p"}}]
    assert set(snap.objects) == set(kubernetes_adapter.SNAPSHOT_RESOURCES)
    assert snap.errors == [] and snap.truncated == []
    core.list_pod_for_all_namespaces.assert_called_once_with(
        limit=2000, _request_timeout=5, _preload_content=False
    )
    core.list_event_for_all_namespaces.assert_called_once_with(
        limit=500, _request_timeout=5, _preload_content=False
    )
    assert_read_only(apps, core, discovery)


def test_snapshot_lists_each_namespace_separately(
    all_apis: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    apps, core, discovery = all_apis
    adapter().snapshot(["shop", "payments"])
    assert [c.args for c in core.list_namespaced_pod.call_args_list] == [
        ("shop",),
        ("payments",),
    ]
    discovery.list_endpoint_slice_for_all_namespaces.assert_not_called()
    core.list_pod_for_all_namespaces.assert_not_called()
    assert_read_only(apps, core, discovery)


def test_snapshot_records_refused_listings_and_continues(
    all_apis: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, core, discovery = all_apis
    core.list_node.side_effect = ApiException(status=403, reason="Forbidden")
    discovery.list_namespaced_endpoint_slice.side_effect = ApiException(404, "NF")
    core.list_namespaced_pod.return_value = raw([{"metadata": {}}], more=True)
    snap = adapter().snapshot(["shop"])
    assert snap.errors == [
        kubernetes_adapter.ListingError("endpointslices", "shop", 404, "NF"),
        kubernetes_adapter.ListingError("nodes", None, 403, "Forbidden"),
    ]
    assert snap.truncated == [("pods", "shop")]
    assert snap.objects["pods"] == [{"metadata": {}}]


def test_snapshot_records_unreadable_responses(
    all_apis: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    _, core, _ = all_apis
    core.list_namespaced_service.return_value = NS(data=b"<html>proxy</html>")
    core.list_namespaced_pod.return_value = NS(data=b'{"kind": "Status"}')
    snap = adapter().snapshot(["shop"])
    assert [(e.resource, e.status) for e in snap.errors] == [
        ("pods", None),
        ("services", None),
    ]


def test_snapshot_unreachable_raises(
    all_apis: tuple[MagicMock, MagicMock, MagicMock],
) -> None:
    apps, _, _ = all_apis
    apps.list_deployment_for_all_namespaces.side_effect = MaxRetryError(
        MagicMock(), "https://127.0.0.1:6443"
    )
    with pytest.raises(ClusterUnavailableError) as info:
        adapter().snapshot(None)
    assert info.value.status is None


def test_list_workloads_in_one_namespace(apis: tuple[MagicMock, MagicMock]) -> None:
    apps, core = apis
    apps.list_namespaced_deployment.return_value = NS(items=[])
    apps.list_namespaced_stateful_set.return_value = NS(items=[])
    assert adapter().list_workloads("shop") == []
    apps.list_namespaced_deployment.assert_called_once_with("shop", _request_timeout=5)
    apps.list_deployment_for_all_namespaces.assert_not_called()
    assert_read_only(apps, core)


def test_list_namespaces_and_its_forbidden_status(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    apps, core = apis
    core.list_namespace.return_value = NS(
        items=[NS(metadata=NS(name="shop")), NS(metadata=NS(name="default"))]
    )
    assert adapter().list_namespaces() == ["default", "shop"]
    core.list_namespace.side_effect = ApiException(status=403, reason="Forbidden")
    with pytest.raises(ClusterUnavailableError) as info:
        adapter().list_namespaces()
    assert info.value.status == 403
    assert_read_only(apps, core)
