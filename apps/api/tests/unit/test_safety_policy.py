"""Namespace-scoped safety policies (replaces the old placeholder test)."""

from dataclasses import replace

import pytest

from app.domain.experiment import (
    ExperimentSpec,
    ExperimentTarget,
    FaultType,
    WorkloadKind,
)
from app.domain.safety_policy import (
    DEFAULT_SAFETY_POLICY,
    SANDBOX_NAMESPACE,
    SANDBOX_POLICY,
    SYSTEM_NAMESPACES,
    policy_for_namespace,
    policy_selection,
)
from app.integrations.kubernetes_adapter import WorkloadStatus
from app.services.safety.policy_evaluator import evaluate_cluster, evaluate_static


def spec(namespace: str) -> ExperimentSpec:
    return ExperimentSpec(
        target=ExperimentTarget(namespace, WorkloadKind.DEPLOYMENT, "fragile"),
        fault_type=FaultType.POD_DELETE,
        duration_seconds=30,
        affected_replicas=1,
    )


def test_default_policy_is_unchanged() -> None:
    assert DEFAULT_SAFETY_POLICY.to_dict() == {
        "name": "default",
        "description": "Default policy for all namespaces",
        "max_duration_seconds": 300,
        "max_affected_replicas": 1,
        "min_healthy_replicas": 1,
        "forbidden_namespaces": sorted(SYSTEM_NAMESPACES),
        "allowed_namespaces": None,
    }


@pytest.mark.parametrize(
    "namespace",
    [
        "shop",
        "default",
        "kube-system",
        "resilience-sandbox-2",
        "my-resilience-sandbox",
        "sandbox",
    ],
)
def test_other_namespaces_get_default(namespace: str) -> None:
    assert policy_for_namespace(namespace) is DEFAULT_SAFETY_POLICY
    assert policy_selection(namespace, DEFAULT_SAFETY_POLICY)["policy"] == "default"


def test_only_the_sandbox_namespace_gets_the_sandbox_policy() -> None:
    assert policy_for_namespace(SANDBOX_NAMESPACE) is SANDBOX_POLICY
    assert policy_selection(SANDBOX_NAMESPACE, SANDBOX_POLICY) == {
        "namespace": "resilience-sandbox",
        "policy": "sandbox",
        "rule": "namespace 'resilience-sandbox' maps to policy 'sandbox'",
    }


def test_sandbox_differs_from_default_only_in_redundancy_and_scope() -> None:
    same_otherwise = replace(
        SANDBOX_POLICY,
        name=DEFAULT_SAFETY_POLICY.name,
        description=DEFAULT_SAFETY_POLICY.description,
        min_healthy_replicas=DEFAULT_SAFETY_POLICY.min_healthy_replicas,
        allowed_namespaces=DEFAULT_SAFETY_POLICY.allowed_namespaces,
    )
    assert same_otherwise == DEFAULT_SAFETY_POLICY
    assert SANDBOX_POLICY.min_healthy_replicas == 0
    assert SANDBOX_POLICY.allowed_namespaces == frozenset({SANDBOX_NAMESPACE})


def test_single_replica_passes_only_under_sandbox_policy() -> None:
    one_ready = WorkloadStatus(1, 1, 1)
    default = evaluate_cluster(spec("shop"), DEFAULT_SAFETY_POLICY, one_ready)
    sandbox = evaluate_cluster(spec(SANDBOX_NAMESPACE), SANDBOX_POLICY, one_ready)

    assert not default[2].passed
    assert default[2].message == "1 ready - 1 affected = 0 remaining < minimum 1"
    assert sandbox[2].passed
    assert sandbox[2].message == "1 ready - 1 affected = 0 remaining >= minimum 0"


def test_sandbox_policy_cannot_validate_any_other_namespace() -> None:
    """Defence in depth: even if wrongly selected, its allowlist fails other namespaces."""
    checks = {c.name: c for c in evaluate_static(spec("shop"), SANDBOX_POLICY)}
    assert not checks["namespace_allowed"].passed


@pytest.mark.parametrize("namespace", sorted(SYSTEM_NAMESPACES))
def test_system_namespaces_forbidden_under_every_policy(namespace: str) -> None:
    for policy in (DEFAULT_SAFETY_POLICY, SANDBOX_POLICY):
        checks = {c.name: c for c in evaluate_static(spec(namespace), policy)}
        assert not checks["namespace_not_forbidden"].passed
