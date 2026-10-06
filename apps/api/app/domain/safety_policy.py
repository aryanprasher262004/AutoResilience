from dataclasses import asdict, dataclass
from typing import Any

SYSTEM_NAMESPACES = frozenset(
    {"kube-system", "kube-public", "kube-node-lease", "litmus", "monitoring"}
)

# Reserved for deliberately fragile test workloads (infra/sample-app/sandbox.yaml).
SANDBOX_NAMESPACE = "resilience-sandbox"


@dataclass(frozen=True)
class SafetyPolicy:
    name: str = "default"
    description: str = "Default policy for all namespaces"
    max_duration_seconds: int = 300
    max_affected_replicas: int = 1
    # Checked against live cluster state: ready pods left after the fault hits.
    min_healthy_replicas: int = 1
    forbidden_namespaces: frozenset[str] = SYSTEM_NAMESPACES
    # None means any namespace not in forbidden_namespaces is allowed.
    allowed_namespaces: frozenset[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["forbidden_namespaces"] = sorted(self.forbidden_namespaces)
        if self.allowed_namespaces is not None:
            data["allowed_namespaces"] = sorted(self.allowed_namespaces)
        return data


DEFAULT_SAFETY_POLICY = SafetyPolicy()

# Identical to the default except that a fault may take down every replica, and it
# can only ever pass validation in the sandbox namespace (allowed_namespaces).
SANDBOX_POLICY = SafetyPolicy(
    name="sandbox",
    description=(
        f"Reduced-redundancy testing; only valid in the '{SANDBOX_NAMESPACE}' namespace"
    ),
    min_healthy_replicas=0,
    allowed_namespaces=frozenset({SANDBOX_NAMESPACE}),
)

# The only way a non-default policy is selected: a fixed, code-reviewed mapping keyed
# by the experiment's (validated, persisted) target namespace. Not configurable via API.
POLICIES_BY_NAMESPACE: dict[str, SafetyPolicy] = {SANDBOX_NAMESPACE: SANDBOX_POLICY}


def policy_for_namespace(namespace: str) -> SafetyPolicy:
    return POLICIES_BY_NAMESPACE.get(namespace, DEFAULT_SAFETY_POLICY)


def policy_selection(namespace: str, policy: SafetyPolicy) -> dict[str, str]:
    """Audit record of why this policy applied to this experiment."""
    return {
        "namespace": namespace,
        "policy": policy.name,
        "rule": (
            f"namespace '{namespace}' maps to policy '{policy.name}'"
            if namespace in POLICIES_BY_NAMESPACE
            else "no namespace-specific policy; default applies"
        ),
    }
