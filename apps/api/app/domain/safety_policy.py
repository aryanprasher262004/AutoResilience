from dataclasses import asdict, dataclass
from typing import Any

SYSTEM_NAMESPACES = frozenset(
    {"kube-system", "kube-public", "kube-node-lease", "litmus", "monitoring"}
)


@dataclass(frozen=True)
class SafetyPolicy:
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
