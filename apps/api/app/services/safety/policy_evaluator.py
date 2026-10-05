"""Deterministic safety checks.

Static checks use only the experiment spec and policy. Cluster checks use a
WorkloadStatus already fetched from Kubernetes, so both stay pure and testable.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from app.domain.experiment import SUPPORTED_FAULT_TYPES, ExperimentSpec
from app.domain.safety_policy import SafetyPolicy
from app.integrations.kubernetes_adapter import WorkloadStatus

CLUSTER_CHECK_NAMES = (
    "target_workload_exists",
    "target_has_running_pods",
    "min_healthy_replicas_after_fault",
)


class CheckStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    # Data needed for the check could not be obtained.
    ERROR = "ERROR"
    # Not evaluated because an earlier check made it meaningless.
    SKIPPED = "SKIPPED"


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: CheckStatus
    message: str

    @property
    def passed(self) -> bool:
        return self.status is CheckStatus.PASSED


@dataclass(frozen=True)
class ValidationResult:
    static_checks: list[CheckResult]
    cluster_checks: list[CheckResult]
    policy: SafetyPolicy

    @property
    def passed(self) -> bool:
        # Only an explicit PASSED counts; ERROR and SKIPPED block the experiment.
        return all(c.passed for c in self.static_checks + self.cluster_checks)

    @property
    def failure_reasons(self) -> list[str]:
        return [
            c.message for c in self.static_checks + self.cluster_checks if not c.passed
        ]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "static_checks": [_check_dict(c) for c in self.static_checks],
            "cluster_checks": [_check_dict(c) for c in self.cluster_checks],
            "policy": self.policy.to_dict(),
        }


def _check_dict(check: CheckResult) -> dict[str, str]:
    return {"name": check.name, "status": check.status, "message": check.message}


def _check(name: str, passed: bool, message: str) -> CheckResult:
    return CheckResult(
        name, CheckStatus.PASSED if passed else CheckStatus.FAILED, message
    )


def evaluate_static(spec: ExperimentSpec, policy: SafetyPolicy) -> list[CheckResult]:
    """Run every static check (no short-circuit) so all failure reasons are reported."""
    namespace = spec.target.namespace
    forbidden = namespace in policy.forbidden_namespaces
    duration_ok = spec.duration_seconds <= policy.max_duration_seconds
    replicas_ok = spec.affected_replicas <= policy.max_affected_replicas
    supported = spec.fault_type in SUPPORTED_FAULT_TYPES
    return [
        _check(
            "fault_type_supported",
            supported,
            f"Fault type '{spec.fault_type}' is "
            + ("supported" if supported else "not supported yet"),
        ),
        _check(
            "namespace_not_forbidden",
            not forbidden,
            f"Namespace '{namespace}' is "
            + ("protected and cannot be targeted" if forbidden else "not protected"),
        ),
        _namespace_allowed(namespace, policy),
        _check(
            "duration_within_limit",
            duration_ok,
            f"Duration {spec.duration_seconds}s "
            + ("<=" if duration_ok else ">")
            + f" limit {policy.max_duration_seconds}s",
        ),
        _check(
            "affected_replicas_within_limit",
            replicas_ok,
            f"Affected replicas {spec.affected_replicas} "
            + ("<=" if replicas_ok else ">")
            + f" limit {policy.max_affected_replicas}",
        ),
    ]


def _namespace_allowed(namespace: str, policy: SafetyPolicy) -> CheckResult:
    if policy.allowed_namespaces is None:
        return _check("namespace_allowed", True, "No namespace allowlist configured")
    allowed = namespace in policy.allowed_namespaces
    return _check(
        "namespace_allowed",
        allowed,
        f"Namespace '{namespace}' is "
        + ("in" if allowed else "not in")
        + f" the allowlist {sorted(policy.allowed_namespaces)}",
    )


def skipped_cluster_checks(reason: str) -> list[CheckResult]:
    return [CheckResult(n, CheckStatus.SKIPPED, reason) for n in CLUSTER_CHECK_NAMES]


def errored_cluster_checks(error: str) -> list[CheckResult]:
    message = f"Kubernetes data unavailable: {error}"
    return [CheckResult(n, CheckStatus.ERROR, message) for n in CLUSTER_CHECK_NAMES]


def evaluate_cluster(
    spec: ExperimentSpec, policy: SafetyPolicy, status: WorkloadStatus | None
) -> list[CheckResult]:
    target = spec.target
    ref = f"{target.kind} {target.namespace}/{target.name}"
    if status is None:
        return [
            _check("target_workload_exists", False, f"{ref} not found"),
            *skipped_cluster_checks("Skipped: target workload not found")[1:],
        ]

    checks = [
        _check("target_workload_exists", True, f"{ref} exists"),
        _check(
            "target_has_running_pods",
            status.ready_pods > 0,
            f"{status.ready_pods}/{status.desired_replicas} desired pods running and "
            f"ready ({status.running_pods} running)",
        ),
    ]
    if status.ready_pods == 0:
        checks.append(
            CheckResult(
                "min_healthy_replicas_after_fault",
                CheckStatus.SKIPPED,
                "Skipped: no running and ready pods to fault",
            )
        )
        return checks

    remaining = status.ready_pods - spec.affected_replicas
    checks.append(
        _check(
            "min_healthy_replicas_after_fault",
            remaining >= policy.min_healthy_replicas,
            f"{status.ready_pods} ready - {spec.affected_replicas} affected = "
            f"{remaining} remaining "
            + (">=" if remaining >= policy.min_healthy_replicas else "<")
            + f" minimum {policy.min_healthy_replicas}",
        )
    )
    return checks
