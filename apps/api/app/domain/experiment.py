from dataclasses import dataclass
from enum import StrEnum


class FaultType(StrEnum):
    # Values match LitmusChaos generic experiment names.
    POD_DELETE = "pod-delete"
    POD_CPU_HOG = "pod-cpu-hog"
    POD_MEMORY_HOG = "pod-memory-hog"
    POD_NETWORK_LATENCY = "pod-network-latency"


class WorkloadKind(StrEnum):
    DEPLOYMENT = "Deployment"
    STATEFULSET = "StatefulSet"


@dataclass(frozen=True)
class ExperimentTarget:
    namespace: str
    kind: WorkloadKind
    name: str


@dataclass(frozen=True)
class ExperimentSpec:
    """What a policy is evaluated against: the target plus the fault and its blast radius."""

    target: ExperimentTarget
    fault_type: FaultType
    duration_seconds: int
    affected_replicas: int
