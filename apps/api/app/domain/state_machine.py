from enum import StrEnum


class ExperimentState(StrEnum):
    CREATED = "CREATED"
    VALIDATING = "VALIDATING"
    BASELINING = "BASELINING"
    INJECTING = "INJECTING"
    OBSERVING = "OBSERVING"
    RECOVERING = "RECOVERING"
    COMPLETED = "COMPLETED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    INJECTION_FAILED = "INJECTION_FAILED"
    ABORTED = "ABORTED"
    # Orchestrator lost track of the run (e.g. chaos backend unreachable mid-run).
    UNKNOWN = "UNKNOWN"


S = ExperimentState

ALLOWED_TRANSITIONS: dict[ExperimentState, frozenset[ExperimentState]] = {
    S.CREATED: frozenset({S.VALIDATING, S.ABORTED}),
    S.VALIDATING: frozenset({S.BASELINING, S.VALIDATION_FAILED, S.ABORTED}),
    S.BASELINING: frozenset({S.INJECTING, S.ABORTED, S.UNKNOWN}),
    S.INJECTING: frozenset({S.OBSERVING, S.INJECTION_FAILED, S.ABORTED, S.UNKNOWN}),
    S.OBSERVING: frozenset({S.RECOVERING, S.ABORTED, S.UNKNOWN}),
    S.RECOVERING: frozenset({S.COMPLETED, S.ABORTED, S.UNKNOWN}),
    S.UNKNOWN: frozenset({S.ABORTED}),
    S.COMPLETED: frozenset(),
    S.VALIDATION_FAILED: frozenset(),
    S.INJECTION_FAILED: frozenset(),
    S.ABORTED: frozenset(),
}

INITIAL_STATE = S.CREATED
TERMINAL_STATES = frozenset(
    s for s, targets in ALLOWED_TRANSITIONS.items() if not targets
)


class InvalidTransitionError(ValueError):
    def __init__(self, current: ExperimentState, target: ExperimentState) -> None:
        super().__init__(f"Invalid experiment state transition: {current} -> {target}")
        self.current = current
        self.target = target


def can_transition(current: ExperimentState, target: ExperimentState) -> bool:
    return target in ALLOWED_TRANSITIONS[current]


def transition(current: ExperimentState, target: ExperimentState) -> ExperimentState:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target
