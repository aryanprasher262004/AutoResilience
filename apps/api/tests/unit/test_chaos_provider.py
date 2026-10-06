from typing import Any
from unittest.mock import MagicMock

import pytest
from kubernetes.client.exceptions import ApiException
from urllib3.exceptions import MaxRetryError

from app.domain.experiment import ExperimentTarget, PodDeleteMode, WorkloadKind
from app.integrations import chaos_provider
from app.integrations.chaos_provider import (
    ChaosEngineExistsError,
    ChaosProviderError,
    FaultPhase,
    LitmusChaosProvider,
    PodDeleteRequest,
    build_pod_delete_engine,
    parse_engine_status,
)

EXP_ID = "0b6f2c1e-0000-4000-8000-000000000001"
CHECKOUT = ExperimentTarget("shop", WorkloadKind.DEPLOYMENT, "checkout")


def request(**overrides: Any) -> PodDeleteRequest:
    fields: dict[str, Any] = {
        "experiment_id": EXP_ID,
        "target": CHECKOUT,
        "label_selector": "app=checkout",
        "target_pods": ("checkout-a",),
        "duration_seconds": 30,
    }
    fields.update(overrides)
    return PodDeleteRequest(**fields)


def env(engine: dict[str, Any]) -> dict[str, str]:
    items = engine["spec"]["experiments"][0]["spec"]["components"]["env"]
    return {e["name"]: e["value"] for e in items}


# --- engine manifest ------------------------------------------------------


def test_engine_is_scoped_to_validated_target() -> None:
    engine = build_pod_delete_engine(
        request(target_pods=("checkout-a", "checkout-b"), duration_seconds=45)
    )

    assert engine["kind"] == "ChaosEngine"
    assert engine["metadata"]["name"] == f"ar-{EXP_ID}"
    assert engine["metadata"]["namespace"] == "shop"
    assert engine["metadata"]["labels"]["autoresilience.io/experiment-id"] == EXP_ID
    spec = engine["spec"]
    assert spec["appinfo"] == {
        "appns": "shop",
        "applabel": "app=checkout",
        "appkind": "deployment",
    }
    assert spec["chaosServiceAccount"] == "autoresilience-chaos"
    assert spec["engineState"] == "active"
    assert [e["name"] for e in spec["experiments"]] == ["pod-delete"]
    assert env(engine) == {
        "TOTAL_CHAOS_DURATION": "45",
        # One deletion round: interval == duration.
        "CHAOS_INTERVAL": "45",
        "FORCE": "false",
        "TARGET_PODS": "checkout-a,checkout-b",
        "PODS_AFFECTED_PERC": "",
        "SEQUENCE": "parallel",
    }
    assert len(engine["metadata"]["name"]) <= 63


def test_statefulset_appkind() -> None:
    target = ExperimentTarget("shop", WorkloadKind.STATEFULSET, "cart-redis")
    engine = build_pod_delete_engine(
        request(target=target, target_pods=("cart-redis-0",))
    )
    assert engine["spec"]["appinfo"]["appkind"] == "statefulset"


@pytest.mark.parametrize("namespace", ["kube-system", "litmus", "monitoring"])
def test_refuses_system_namespaces(namespace: str) -> None:
    target = ExperimentTarget(namespace, WorkloadKind.DEPLOYMENT, "x")
    with pytest.raises(ChaosProviderError, match="Refusing to inject"):
        build_pod_delete_engine(request(target=target))


@pytest.mark.parametrize(
    ("overrides", "message"),
    [({"target_pods": ()}, "No target pods"), ({"duration_seconds": 0}, "Duration")],
)
def test_rejects_invalid_requests(overrides: dict[str, Any], message: str) -> None:
    with pytest.raises(ChaosProviderError, match=message):
        build_pod_delete_engine(request(**overrides))


# --- status parsing (shapes observed from Litmus 3.31 on kind) -------------


def engine_with(
    engine_status: str | None = "initialized", **experiment: str
) -> dict[str, Any]:
    status: dict[str, Any] = {"engineStatus": engine_status}
    if experiment:
        status["experiments"] = [experiment]
    return {"status": status}


@pytest.mark.parametrize(
    ("engine", "phase"),
    [
        ({}, FaultPhase.PENDING),
        (engine_with(), FaultPhase.PENDING),
        (
            engine_with(
                status="Waiting for Job Creation",
                verdict="N/A",
                experimentPod="Yet to be launched",
            ),
            FaultPhase.PENDING,
        ),
        (
            engine_with(status="Running", verdict="Awaited", experimentPod="pd-1"),
            FaultPhase.RUNNING,
        ),
        (
            engine_with("completed", status="Completed", verdict="Pass"),
            FaultPhase.COMPLETED,
        ),
        (engine_with(status="Completed", verdict="Fail"), FaultPhase.FAILED),
        (engine_with(status="Running", verdict="Error"), FaultPhase.FAILED),
        (
            engine_with("stopped", status="Running", verdict="Stopped"),
            FaultPhase.FAILED,
        ),
    ],
)
def test_parse_engine_status(engine: dict[str, Any], phase: FaultPhase) -> None:
    assert parse_engine_status(engine).phase is phase


def test_parse_hides_placeholder_experiment_pod() -> None:
    status = parse_engine_status(
        engine_with(
            status="Waiting for Job Creation", experimentPod="Yet to be launched"
        )
    )
    assert status.experiment_pod is None


# --- API calls --------------------------------------------------------------


@pytest.fixture
def apis(monkeypatch: pytest.MonkeyPatch) -> tuple[MagicMock, MagicMock]:
    custom, core = MagicMock(), MagicMock()
    monkeypatch.setattr(chaos_provider.config, "new_client_from_config", MagicMock())
    monkeypatch.setattr(chaos_provider.client, "CustomObjectsApi", lambda _: custom)
    monkeypatch.setattr(chaos_provider.client, "CoreV1Api", lambda _: core)
    return custom, core


def provider() -> LitmusChaosProvider:
    return LitmusChaosProvider(context="kind-autoresilience", request_timeout=5)


def test_start_creates_only_a_chaos_engine(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, core = apis

    name = provider().start_pod_delete(request())

    assert name == f"ar-{EXP_ID}"
    custom.create_namespaced_custom_object.assert_called_once()
    group, version, namespace, plural, body = (
        custom.create_namespaced_custom_object.call_args.args
    )
    assert (group, version, namespace, plural) == (
        "litmuschaos.io",
        "v1alpha1",
        "shop",
        "chaosengines",
    )
    assert body == build_pod_delete_engine(request())
    writes = [
        c[0]
        for c in custom.method_calls + core.method_calls
        if not c[0].startswith(("get_", "read_", "list_"))
    ]
    assert writes == ["create_namespaced_custom_object"]


@pytest.mark.parametrize("missing", ["experiment", "service_account"])
def test_start_requires_prepared_namespace(
    apis: tuple[MagicMock, MagicMock], missing: str
) -> None:
    custom, core = apis
    not_found = ApiException(status=404, reason="Not Found")
    if missing == "experiment":
        custom.get_namespaced_custom_object.side_effect = not_found
    else:
        core.read_namespaced_service_account.side_effect = not_found

    with pytest.raises(ChaosProviderError, match="not prepared for chaos"):
        provider().start_pod_delete(request())
    custom.create_namespaced_custom_object.assert_not_called()


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ApiException(status=409, reason="AlreadyExists"), "already exists"),
        (ApiException(status=403, reason="Forbidden"), "API error 403"),
        (MaxRetryError(None, "/apis", "refused"), "unreachable"),  # type: ignore[arg-type]
    ],
)
def test_create_failures_raise_provider_error(
    apis: tuple[MagicMock, MagicMock], error: Exception, message: str
) -> None:
    custom, _ = apis
    custom.create_namespaced_custom_object.side_effect = error

    with pytest.raises(ChaosProviderError, match=message):
        provider().start_pod_delete(request())


def test_unsafe_request_never_reaches_the_api(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    custom, core = apis
    target = ExperimentTarget("kube-system", WorkloadKind.DEPLOYMENT, "coredns")

    with pytest.raises(ChaosProviderError):
        provider().start_pod_delete(request(target=target))
    assert custom.method_calls == [] and core.method_calls == []


def test_get_status_reads_engine(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.return_value = engine_with(
        status="Running", verdict="Awaited", experimentPod="pd-1"
    )

    status = provider().get_status("shop", "ar-x")

    assert status.phase is FaultPhase.RUNNING
    assert status.experiment_pod == "pd-1"
    custom.get_namespaced_custom_object.assert_called_once_with(
        "litmuschaos.io", "v1alpha1", "shop", "chaosengines", "ar-x", _request_timeout=5
    )


def test_stop_patches_engine_state(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, _ = apis

    provider().stop("shop", "ar-x")

    custom.patch_namespaced_custom_object.assert_called_once_with(
        "litmuschaos.io",
        "v1alpha1",
        "shop",
        "chaosengines",
        "ar-x",
        {"spec": {"engineState": "stop"}},
        _request_timeout=5,
    )


def test_status_failure_raises_provider_error(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="NF"
    )
    with pytest.raises(ChaosProviderError, match="read ChaosEngine"):
        provider().get_status("shop", "ar-x")


def test_get_result_reads_chaos_result(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.return_value = {
        "status": {
            "experimentStatus": {
                "phase": "Completed",
                "verdict": "Fail",
                "failStep": "[post-chaos]: Failed to verify that the AUT is running",
                "probeSuccessPercentage": "0",
            }
        }
    }

    result = provider().get_result("shop", "ar-x")

    assert result == {
        "phase": "Completed",
        "verdict": "Fail",
        "fail_step": "[post-chaos]: Failed to verify that the AUT is running",
        "probe_success_percentage": "0",
    }
    custom.get_namespaced_custom_object.assert_called_once_with(
        "litmuschaos.io",
        "v1alpha1",
        "shop",
        "chaosresults",
        "ar-x-pod-delete",
        _request_timeout=5,
    )


# --- pod-delete mode ---------------------------------------------------------------


def test_graceful_is_the_default_and_maps_to_force_false() -> None:
    engine = build_pod_delete_engine(request())

    assert env(engine)["FORCE"] == "false"
    assert (
        engine["metadata"]["labels"]["autoresilience.io/pod-delete-mode"] == "GRACEFUL"
    )


def test_force_mode_maps_to_force_true_only() -> None:
    graceful = build_pod_delete_engine(request(mode=PodDeleteMode.GRACEFUL))
    force = build_pod_delete_engine(request(mode=PodDeleteMode.FORCE))

    assert env(force)["FORCE"] == "true"
    assert force["metadata"]["labels"]["autoresilience.io/pod-delete-mode"] == "FORCE"
    # Nothing else about the engine differs: same target, pods, duration, RBAC.
    for engine in (graceful, force):
        engine["metadata"]["labels"].pop("autoresilience.io/pod-delete-mode")
        for item in engine["spec"]["experiments"][0]["spec"]["components"]["env"]:
            if item["name"] == "FORCE":
                item["value"] = "X"
    assert graceful == force


def test_force_mode_keeps_namespace_guard() -> None:
    target = ExperimentTarget("kube-system", WorkloadKind.DEPLOYMENT, "coredns")
    with pytest.raises(ChaosProviderError, match="Refusing to inject"):
        build_pod_delete_engine(request(target=target, mode=PodDeleteMode.FORCE))


# --- owned cleanup -------------------------------------------------------------------


def owned_engine(experiment_id: str = EXP_ID) -> dict[str, Any]:
    return {
        "metadata": {
            "labels": {
                "app.kubernetes.io/managed-by": "autoresilience",
                "autoresilience.io/experiment-id": experiment_id,
            }
        }
    }


def test_delete_owned_deletes_engine_and_result(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.side_effect = [
        owned_engine(),
        {"kind": "ChaosResult"},
    ]

    outcome = provider().delete_owned("shop", f"ar-{EXP_ID}", EXP_ID)

    assert outcome == {"engine": "deleted", "result": "deleted"}
    deleted = [
        c.args[3:5] for c in custom.delete_namespaced_custom_object.call_args_list
    ]
    assert deleted == [
        ("chaosengines", f"ar-{EXP_ID}"),
        ("chaosresults", f"ar-{EXP_ID}-pod-delete"),
    ]


def test_delete_owned_refuses_foreign_engine(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.return_value = owned_engine("another-run")

    with pytest.raises(ChaosProviderError, match="not owned"):
        provider().delete_owned("shop", f"ar-{EXP_ID}", EXP_ID)
    custom.delete_namespaced_custom_object.assert_not_called()


def test_delete_owned_refuses_unlabelled_engine(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.return_value = {"metadata": {"labels": {}}}

    with pytest.raises(ChaosProviderError, match="not owned"):
        provider().delete_owned("shop", f"ar-{EXP_ID}", EXP_ID)
    custom.delete_namespaced_custom_object.assert_not_called()


@pytest.mark.parametrize(
    ("namespace", "name", "message"),
    [
        ("kube-system", f"ar-{EXP_ID}", "Refusing to clean up"),
        ("shop", "ar-other", "does not belong"),
        ("shop", "hand-made-engine", "does not belong"),
    ],
)
def test_delete_owned_refuses_before_any_api_call(
    apis: tuple[MagicMock, MagicMock], namespace: str, name: str, message: str
) -> None:
    custom, _ = apis
    with pytest.raises(ChaosProviderError, match=message):
        provider().delete_owned(namespace, name, EXP_ID)
    assert custom.method_calls == []


def test_delete_owned_absent_objects_are_fine(
    apis: tuple[MagicMock, MagicMock],
) -> None:
    custom, _ = apis
    custom.get_namespaced_custom_object.side_effect = ApiException(
        status=404, reason="NF"
    )

    assert provider().delete_owned("shop", f"ar-{EXP_ID}", EXP_ID) == {
        "engine": "absent",
        "result": "absent",
    }
    custom.delete_namespaced_custom_object.assert_not_called()


def test_start_reports_existing_engine(apis: tuple[MagicMock, MagicMock]) -> None:
    custom, _ = apis
    custom.create_namespaced_custom_object.side_effect = ApiException(
        status=409, reason="AlreadyExists"
    )
    with pytest.raises(ChaosEngineExistsError, match="already exists"):
        provider().start_pod_delete(request())
