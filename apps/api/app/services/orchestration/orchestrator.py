"""Automatic experiment orchestration: an in-process reconciler.

POST /experiments/{id}/run marks a CREATED experiment `orchestration.mode = "auto"`.
A background thread calls Reconciler.tick() every few seconds; each tick advances
every auto experiment by one bounded step using the existing lifecycle functions
(validation, baseline, injection, observation), then cleans up the ChaosEngine of
finished experiments. All progress is persisted, so after an API restart the next
tick simply continues: nothing is kept only in memory and nothing is re-run.

Safety rules kept from the lifecycle: one ChaosEngine per experiment (deterministic
name), platform uncertainty ends in UNKNOWN (never COMPLETED), only the experiment's
own recorded engine is ever stopped or deleted.

Single API process assumed: per-experiment locks serialize the reconciler with abort.
"""

import logging
import threading
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.safety_policy import SafetyPolicy
from app.domain.state_machine import (
    ExperimentState,
    InvalidTransitionError,
    can_transition,
    transition,
)
from app.integrations.chaos_provider import ChaosProviderError, FaultStatus
from app.services.orchestration.baseline import run_baseline
from app.services.orchestration.injection import advance_injection, start_injection
from app.services.orchestration.observation import (
    ObservationConfig,
    advance_observation,
)
from app.services.orchestration.preflight import complete_validation, run_validation

log = logging.getLogger(__name__)

S = ExperimentState
TERMINAL = frozenset(
    {S.COMPLETED, S.UNKNOWN, S.ABORTED, S.VALIDATION_FAILED, S.INJECTION_FAILED}
)
ABORTABLE = frozenset(
    {S.CREATED, S.VALIDATING, S.BASELINING, S.INJECTING, S.OBSERVING, S.RECOVERING}
)
MAX_EVENTS = 50


class Chaos(Protocol):
    def start_pod_delete(self, request: Any) -> str: ...
    def get_status(self, namespace: str, name: str) -> FaultStatus: ...
    def get_result(self, namespace: str, name: str) -> dict[str, str | None]: ...
    def stop(self, namespace: str, name: str) -> None: ...
    def delete_owned(
        self, namespace: str, name: str, experiment_id: str
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class OrchestratorConfig:
    interval_seconds: float
    baseline_window_seconds: int
    baseline_timeout_seconds: float
    injection_timeout_seconds: float
    max_runtime_seconds: float
    cleanup_grace_seconds: float
    observation: ObservationConfig


@dataclass(frozen=True)
class Dependencies:
    kubernetes: Any
    prometheus: Any
    chaos: Chaos
    policies: Callable[[str], SafetyPolicy]


class OrchestrationError(Exception):
    pass


# --- locking -------------------------------------------------------------------

_locks: dict[UUID, threading.Lock] = {}
_locks_guard = threading.Lock()


@contextmanager
def experiment_lock(experiment_id: UUID) -> Iterator[None]:
    with _locks_guard:
        lock = _locks.setdefault(experiment_id, threading.Lock())
    with lock:
        yield


# --- API-facing operations -------------------------------------------------------


def is_auto(experiment: Experiment) -> bool:
    return (experiment.orchestration or {}).get("mode") == "auto"


def request_auto_run(db: Session, experiment: Experiment, now: datetime) -> None:
    """Hand an experiment to the orchestrator (idempotent).

    Accepts CREATED (the orchestrator validates it) or an experiment that already
    passed POST /validate and is waiting in BASELINING with no baseline yet (the
    orchestrator continues from there; injection still re-checks the cluster).
    """
    if is_auto(experiment):
        return
    validated = (
        experiment.state is S.BASELINING
        and bool((experiment.validation_result or {}).get("passed"))
        and experiment.baseline is None
    )
    if experiment.state is not S.CREATED and not validated:
        raise OrchestrationError(
            "Only CREATED experiments, or experiments that passed validation and "
            f"have not started, can be run (state is {experiment.state})"
        )
    at = now.isoformat()
    experiment.orchestration = {
        "mode": "auto",
        "requested_at": at,
        "state_since": {experiment.state.value: at},
        "events": [
            {
                "at": at,
                "event": "auto run requested"
                + (" (already validated)" if validated else ""),
            }
        ],
        "result": None,
        "abort": None,
        "cleanup": None,
        "last_error": None,
    }
    db.commit()


def abort_experiment(
    db: Session, experiment: Experiment, chaos: Chaos, reason: str, now: datetime
) -> None:
    """Stop this experiment's own ChaosEngine (if any) and move to ABORTED."""
    if experiment.state not in ABORTABLE:
        raise InvalidTransitionError(experiment.state, S.ABORTED)
    orch = dict(experiment.orchestration or {"mode": "manual"})
    record: dict[str, Any] = {"reason": reason, "at": now.isoformat()}
    run = experiment.chaos or {}
    if run.get("engine_name"):
        try:
            chaos.stop(run["namespace"], run["engine_name"])
            record["engine_stopped"] = run["engine_name"]
        except ChaosProviderError as exc:
            # Recorded; cleanup keeps retrying deletion of this engine.
            record["engine_stopped"] = None
            record["stop_error"] = str(exc)
    else:
        record["engine_stopped"] = None
        record["note"] = "no ChaosEngine had been created"
    orch["abort"] = record
    _set_state(experiment, orch, S.ABORTED, now, f"aborted: {reason}")
    experiment.orchestration = orch
    db.commit()


# --- reconciler ------------------------------------------------------------------


class Reconciler:
    def __init__(
        self,
        session_factory: Callable[[], AbstractContextManager[Session]],
        deps: Dependencies,
        config: OrchestratorConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._sessions = session_factory
        self._deps = deps
        self._config = config
        self._clock = clock

    def tick(self) -> list[UUID]:
        """Advance every auto experiment one step and clean up finished ones."""
        with self._sessions() as db:
            ids = [e.id for e in db.scalars(select(Experiment)) if self._needs_work(e)]
        for experiment_id in ids:
            with experiment_lock(experiment_id), self._sessions() as db:
                experiment = db.get(Experiment, experiment_id)
                if experiment is None or not self._needs_work(experiment):
                    continue
                try:
                    self.step(db, experiment)
                except Exception as exc:  # keep reconciling other experiments
                    log.exception("orchestration step failed for %s", experiment_id)
                    db.rollback()
                    experiment = db.get(Experiment, experiment_id)
                    if experiment is not None:
                        orch = dict(experiment.orchestration or {})
                        orch["last_error"] = f"{type(exc).__name__}: {exc}"
                        experiment.orchestration = orch
                        db.commit()
        return ids

    def run_forever(self, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("reconciler tick failed")
            stop.wait(self._config.interval_seconds)

    @staticmethod
    def _needs_work(e: Experiment) -> bool:
        if e.state not in TERMINAL:
            return is_auto(e)
        cleanup = (e.orchestration or {}).get("cleanup") or {}
        return bool((e.chaos or {}).get("engine_name")) and not cleanup.get("done")

    def step(self, db: Session, experiment: Experiment) -> None:
        now = self._clock()
        before = experiment.state
        orch = dict(experiment.orchestration or {"mode": "manual"})
        orch["last_tick_at"] = now.isoformat()
        if experiment.state in TERMINAL:
            self._cleanup(experiment, orch, now)
        else:
            self._advance(db, experiment, orch, now)
        if experiment.state is not before and not _recorded(orch, experiment.state):
            _set_state(experiment, orch, experiment.state, now, None, from_state=before)
        if experiment.state in TERMINAL and experiment.state is not before:
            self._cleanup(experiment, orch, now)
        orch["last_error"] = None
        experiment.orchestration = orch
        db.commit()

    # -- lifecycle ------------------------------------------------------------

    def _advance(
        self, db: Session, experiment: Experiment, orch: dict[str, Any], now: datetime
    ) -> None:
        deps, cfg = self._deps, self._config
        requested = datetime.fromisoformat(orch["requested_at"])
        if (now - requested).total_seconds() > cfg.max_runtime_seconds:
            self._give_up(
                experiment,
                orch,
                now,
                "ORCHESTRATION_TIMEOUT",
                f"Run exceeded {cfg.max_runtime_seconds:g}s without reaching a "
                f"terminal state (stuck in {experiment.state})",
            )
            return
        policy = deps.policies(experiment.target_namespace)
        state = experiment.state
        if state is S.CREATED:
            run_validation(db, experiment, policy, deps.kubernetes)
        elif state is S.VALIDATING:  # interrupted between commits: resume
            complete_validation(db, experiment, policy, deps.kubernetes)
        elif state is S.BASELINING:
            run_baseline(
                db, experiment, deps.prometheus, cfg.baseline_window_seconds, now
            )
            if experiment.state is S.BASELINING and _since(orch, S.BASELINING, now) > (
                cfg.baseline_timeout_seconds
            ):
                reasons = (experiment.baseline or {}).get("failure_reasons") or []
                self._give_up(
                    experiment,
                    orch,
                    now,
                    "BASELINE_TIMEOUT",
                    f"No usable baseline within {cfg.baseline_timeout_seconds:g}s: "
                    + ("; ".join(reasons) or "unknown"),
                )
        elif state is S.INJECTING:
            if not (experiment.chaos or {}).get("engine_name"):
                start_injection(
                    db, experiment, policy, deps.kubernetes, deps.chaos, now=now
                )
            else:
                advance_injection(
                    db,
                    experiment,
                    deps.kubernetes,
                    deps.chaos,
                    cfg.injection_timeout_seconds,
                    now=now,
                )
        elif state in (S.OBSERVING, S.RECOVERING):
            advance_observation(
                db,
                experiment,
                deps.chaos,
                deps.prometheus,
                deps.kubernetes,
                cfg.observation,
                now,
            )

    def _give_up(
        self,
        experiment: Experiment,
        orch: dict[str, Any],
        now: datetime,
        code: str,
        reason: str,
    ) -> None:
        """Platform-side failure: stop our engine, end UNKNOWN (ABORTED pre-baseline)."""
        run = experiment.chaos or {}
        if run.get("engine_name"):
            try:
                self._deps.chaos.stop(run["namespace"], run["engine_name"])
            except ChaosProviderError as exc:
                reason += f" (engine stop failed: {exc})"
        target = S.UNKNOWN if can_transition(experiment.state, S.UNKNOWN) else S.ABORTED
        orch["result"] = {
            "status": target.value,
            "reason_code": code,
            "reason": reason,
            "cause": "platform",
        }
        _set_state(experiment, orch, target, now, f"{code}: {reason}")

    # -- cleanup ---------------------------------------------------------------

    def _cleanup(
        self, experiment: Experiment, orch: dict[str, Any], now: datetime
    ) -> None:
        run = experiment.chaos or {}
        cleanup = dict(orch.get("cleanup") or {})
        if cleanup.get("done") or not run.get("engine_name"):
            if not run.get("engine_name"):
                cleanup.update(done=True, note="no ChaosEngine was created")
            orch["cleanup"] = cleanup
            return
        namespace, name = run["namespace"], run["engine_name"]
        finished_for = _since(orch, experiment.state, now)
        try:
            status = self._deps.chaos.get_status(namespace, name)
            engine_done = status.engine_status in ("completed", "stopped")
        except ChaosProviderError:
            engine_done = True  # gone or unreadable: delete_owned verifies ownership
        if not engine_done and finished_for < self._config.cleanup_grace_seconds:
            cleanup["waiting"] = "ChaosEngine still finishing"
            orch["cleanup"] = cleanup
            return
        try:
            outcome = self._deps.chaos.delete_owned(namespace, name, str(experiment.id))
        except ChaosProviderError as exc:
            cleanup.update(done=False, error=str(exc), attempted_at=now.isoformat())
            orch["cleanup"] = cleanup
            return
        cleanup = {"done": True, "at": now.isoformat(), **outcome}
        orch["cleanup"] = cleanup
        _event(
            orch,
            now,
            f"cleanup: engine {outcome['engine']}, result {outcome['result']}",
        )


# --- helpers ---------------------------------------------------------------------


def _event(orch: dict[str, Any], now: datetime, text: str) -> None:
    events = list(orch.get("events") or [])
    events.append({"at": now.isoformat(), "event": text})
    orch["events"] = events[-MAX_EVENTS:]


def _set_state(
    experiment: Experiment,
    orch: dict[str, Any],
    target: ExperimentState,
    now: datetime,
    note: str | None,
    from_state: ExperimentState | None = None,
) -> None:
    source = from_state or experiment.state
    if experiment.state is not target:
        experiment.state = transition(experiment.state, target)
    since = dict(orch.get("state_since") or {})
    since[target.value] = now.isoformat()
    orch["state_since"] = since
    _event(orch, now, f"{source} -> {target}" + (f" ({note})" if note else ""))


def _recorded(orch: dict[str, Any], state: ExperimentState) -> bool:
    return state.value in (orch.get("state_since") or {})


def _since(orch: dict[str, Any], state: ExperimentState, now: datetime) -> float:
    at = (orch.get("state_since") or {}).get(state.value)
    if at is None:
        return 0.0
    return (now - datetime.fromisoformat(at)).total_seconds()
