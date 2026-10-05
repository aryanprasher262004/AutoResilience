import pytest

from app.domain.state_machine import (
    ALLOWED_TRANSITIONS,
    INITIAL_STATE,
    TERMINAL_STATES,
    ExperimentState,
    InvalidTransitionError,
    can_transition,
    transition,
)

S = ExperimentState

HAPPY_PATH = [
    S.CREATED,
    S.VALIDATING,
    S.BASELINING,
    S.INJECTING,
    S.OBSERVING,
    S.RECOVERING,
    S.COMPLETED,
]


def test_has_eleven_states_all_mapped() -> None:
    assert len(ExperimentState) == 11
    assert set(ALLOWED_TRANSITIONS) == set(ExperimentState)


def test_initial_state_is_created() -> None:
    assert INITIAL_STATE is S.CREATED


def test_happy_path_is_allowed() -> None:
    state = INITIAL_STATE
    for target in HAPPY_PATH[1:]:
        state = transition(state, target)
    assert state is S.COMPLETED


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.VALIDATING, S.VALIDATION_FAILED),
        (S.INJECTING, S.INJECTION_FAILED),
        (S.OBSERVING, S.ABORTED),
        (S.INJECTING, S.UNKNOWN),
        (S.UNKNOWN, S.ABORTED),
    ],
)
def test_failure_and_abort_paths_are_allowed(
    current: ExperimentState, target: ExperimentState
) -> None:
    assert can_transition(current, target)


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (S.CREATED, S.INJECTING),  # cannot skip validation
        (S.VALIDATING, S.INJECTING),  # cannot skip baseline
        (S.CREATED, S.COMPLETED),
        (S.RECOVERING, S.OBSERVING),  # no going backwards
        (S.CREATED, S.CREATED),
    ],
)
def test_invalid_transitions_raise(
    current: ExperimentState, target: ExperimentState
) -> None:
    assert not can_transition(current, target)
    with pytest.raises(InvalidTransitionError):
        transition(current, target)


def test_terminal_states_have_no_exits() -> None:
    assert TERMINAL_STATES == {
        S.COMPLETED,
        S.VALIDATION_FAILED,
        S.INJECTION_FAILED,
        S.ABORTED,
    }
    for terminal in TERMINAL_STATES:
        for target in ExperimentState:
            assert not can_transition(terminal, target)
