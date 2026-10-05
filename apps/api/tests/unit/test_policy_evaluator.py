from typing import Any

from app.domain.experiment import (
    ExperimentSpec,
    ExperimentTarget,
    FaultType,
    WorkloadKind,
)
from app.domain.safety_policy import DEFAULT_SAFETY_POLICY, SafetyPolicy
from app.integrations.kubernetes_adapter import WorkloadStatus
from app.services.safety.policy_evaluator import (
    CLUSTER_CHECK_NAMES,
    CheckResult,
    CheckStatus,
    ValidationResult,
    errored_cluster_checks,
    evaluate_cluster,
    evaluate_static,
    skipped_cluster_checks,
)

P = CheckStatus.PASSED
F = CheckStatus.FAILED
S = CheckStatus.SKIPPED


def spec(
    namespace: str = "shop", duration: int = 60, replicas: int = 1
) -> ExperimentSpec:
    return ExperimentSpec(
        target=ExperimentTarget(namespace, WorkloadKind.DEPLOYMENT, "checkout"),
        fault_type=FaultType.POD_DELETE,
        duration_seconds=duration,
        affected_replicas=replicas,
    )


def failure_reasons(checks: list[CheckResult]) -> list[str]:
    return [c.message for c in checks if not c.passed]


# --- static checks ---------------------------------------------------------


def test_valid_spec_passes_all_static_checks() -> None:
    checks = evaluate_static(spec(), DEFAULT_SAFETY_POLICY)

    assert all(c.status is P for c in checks)
    assert [c.name for c in checks] == [
        "namespace_not_forbidden",
        "namespace_allowed",
        "duration_within_limit",
        "affected_replicas_within_limit",
    ]


def test_limits_are_inclusive() -> None:
    policy = SafetyPolicy(max_duration_seconds=120, max_affected_replicas=2)
    assert (
        failure_reasons(evaluate_static(spec(duration=120, replicas=2), policy)) == []
    )
    assert failure_reasons(evaluate_static(spec(duration=121, replicas=2), policy))
    assert failure_reasons(evaluate_static(spec(duration=120, replicas=3), policy))


def test_forbidden_namespace_fails_with_reason() -> None:
    checks = evaluate_static(spec(namespace="kube-system"), DEFAULT_SAFETY_POLICY)

    assert failure_reasons(checks) == [
        "Namespace 'kube-system' is protected and cannot be targeted"
    ]


def test_allowlist_is_enforced_when_configured() -> None:
    policy = SafetyPolicy(allowed_namespaces=frozenset({"sandbox", "staging"}))

    assert failure_reasons(evaluate_static(spec(namespace="staging"), policy)) == []
    assert failure_reasons(evaluate_static(spec(namespace="shop"), policy)) == [
        "Namespace 'shop' is not in the allowlist ['sandbox', 'staging']"
    ]


def test_forbidden_wins_over_allowlist() -> None:
    policy = SafetyPolicy(allowed_namespaces=frozenset({"kube-system"}))
    assert failure_reasons(evaluate_static(spec(namespace="kube-system"), policy))


# --- cluster checks --------------------------------------------------------


def statuses(checks: list[CheckResult]) -> list[CheckStatus]:
    return [c.status for c in checks]


def test_healthy_workload_passes_cluster_checks() -> None:
    checks = evaluate_cluster(spec(), DEFAULT_SAFETY_POLICY, WorkloadStatus(3, 3, 3))

    assert [c.name for c in checks] == list(CLUSTER_CHECK_NAMES)
    assert statuses(checks) == [P, P, P]
    assert checks[2].message == "3 ready - 1 affected = 2 remaining >= minimum 1"


def test_missing_workload_fails_and_skips_dependents() -> None:
    checks = evaluate_cluster(spec(), DEFAULT_SAFETY_POLICY, None)

    assert statuses(checks) == [F, S, S]
    assert checks[0].message == "Deployment shop/checkout not found"


def test_no_ready_pods_fails() -> None:
    checks = evaluate_cluster(spec(), DEFAULT_SAFETY_POLICY, WorkloadStatus(3, 2, 0))

    assert statuses(checks) == [P, F, S]
    assert checks[1].message == "0/3 desired pods running and ready (2 running)"


def test_blast_radius_respects_min_healthy_replicas() -> None:
    policy = SafetyPolicy(max_affected_replicas=5, min_healthy_replicas=2)

    def blast_radius(affected: int, ready: int) -> CheckStatus:
        status = WorkloadStatus(
            desired_replicas=5, running_pods=ready, ready_pods=ready
        )
        return evaluate_cluster(spec(replicas=affected), policy, status)[2].status

    assert blast_radius(affected=1, ready=3) is P
    assert blast_radius(affected=2, ready=3) is F
    # Desired replicas don't count; only pods that are actually ready do.
    assert blast_radius(affected=1, ready=2) is F


def test_affecting_more_than_ready_pods_fails() -> None:
    checks = evaluate_cluster(spec(replicas=3), SafetyPolicy(), WorkloadStatus(2, 2, 2))
    assert checks[2].status is F


# --- combined result -------------------------------------------------------


def test_error_and_skipped_never_count_as_passed() -> None:
    static = evaluate_static(spec(), DEFAULT_SAFETY_POLICY)

    errored = ValidationResult(static, errored_cluster_checks("boom"), SafetyPolicy())
    skipped = ValidationResult(static, skipped_cluster_checks("why"), SafetyPolicy())

    assert not errored.passed
    assert not skipped.passed
    assert errored.failure_reasons[0] == "Kubernetes data unavailable: boom"


def test_result_is_deterministic_and_serializable() -> None:
    def build() -> dict[str, Any]:
        s = spec(namespace="shop", replicas=1)
        return ValidationResult(
            evaluate_static(s, DEFAULT_SAFETY_POLICY),
            evaluate_cluster(s, DEFAULT_SAFETY_POLICY, WorkloadStatus(1, 1, 1)),
            DEFAULT_SAFETY_POLICY,
        ).to_dict()

    first, second = build(), build()

    assert first == second
    assert first["passed"] is False
    assert [c["status"] for c in first["cluster_checks"]] == [
        "PASSED",
        "PASSED",
        "FAILED",
    ]
    assert first["policy"]["forbidden_namespaces"] == sorted(
        DEFAULT_SAFETY_POLICY.forbidden_namespaces
    )
