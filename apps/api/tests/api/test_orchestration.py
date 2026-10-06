"""Automatic orchestration: reconciler, restart/resume, timeouts, abort, cleanup."""

import uuid
from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.safety_policy import policy_for_namespace
from app.integrations.chaos_provider import FaultPhase, FaultStatus
from app.services.orchestration.orchestrator import (
    Dependencies,
    OrchestratorConfig,
    Reconciler,
)
from tests.api.test_experiments import payload
from tests.conftest import (
    OBSERVATION_CONFIG,
    Clock,
    FakeChaos,
    FakeKubernetes,
    FakePrometheus,
    fault,
)

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
DONE = FaultStatus(FaultPhase.COMPLETED, "completed", "Completed", "Pass", "pd")
STOPPED = FaultStatus(FaultPhase.FAILED, "stopped", "Running", "Stopped", "pd")
CONFIG = OrchestratorConfig(
    interval_seconds=5,
    baseline_window_seconds=300,
    baseline_timeout_seconds=180,
    injection_timeout_seconds=120,
    max_runtime_seconds=1800,
    cleanup_grace_seconds=120,
    observation=OBSERVATION_CONFIG,
)
UNRELATED = {
    ("resilience-sandbox", "ar-someone-elses-run"): {
        "app.kubernetes.io/managed-by": "autoresilience",
        "autoresilience.io/experiment-id": "someone-elses-run",
    },
    ("shop", "hand-made-engine"): {},
}


@pytest.fixture
def reconciler(
    db_session: Session,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
    clock: Clock,
) -> Reconciler:
    clock.now = T0
    chaos.engines.update(UNRELATED)
    return new_reconciler(db_session, kubernetes, prometheus, chaos, clock)


def new_reconciler(
    db_session: Session,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
    clock: Clock,
    config: OrchestratorConfig = CONFIG,
) -> Reconciler:
    return Reconciler(
        session_factory=lambda: nullcontext(db_session),
        deps=Dependencies(kubernetes, prometheus, chaos, policy_for_namespace),
        config=config,
        clock=clock,
    )


def start(client: TestClient, **overrides: Any) -> str:
    experiment_id: str = client.post("/experiments", json=payload(**overrides)).json()[
        "id"
    ]
    response = client.post(f"/experiments/{experiment_id}/run")
    assert response.status_code == 202
    assert response.json()["orchestration"]["mode"] == "auto"
    return experiment_id


def get(client: TestClient, experiment_id: str) -> dict[str, Any]:
    body: dict[str, Any] = client.get(f"/experiments/{experiment_id}").json()
    return body


def tick_until(
    reconciler: Reconciler,
    client: TestClient,
    experiment_id: str,
    state: str,
    clock: Clock,
    step: float = 5,
    limit: int = 20,
) -> dict[str, Any]:
    for _ in range(limit):
        body = get(client, experiment_id)
        if body["state"] == state:
            return body
        reconciler.tick()
        assert clock.now is not None
        clock.now += timedelta(seconds=step)
    raise AssertionError(
        f"never reached {state}: {get(client, experiment_id)['state']}"
    )


def to_observing(
    reconciler: Reconciler,
    client: TestClient,
    prometheus: FakePrometheus,
    clock: Clock,
) -> tuple[str, float]:
    experiment_id = start(client)
    body = tick_until(reconciler, client, experiment_id, "OBSERVING", clock)
    fault_start = datetime.fromisoformat(body["chaos"]["created_at"]).timestamp()
    prometheus.healthy_recovery(fault_start)
    return experiment_id, fault_start


def own_engine(experiment_id: str) -> tuple[str, str]:
    return ("shop", f"ar-{experiment_id}")


# --- normal automatic completion -------------------------------------------------


def test_run_completes_automatically_and_cleans_up(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
    db_session: Session,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)

    reconciler.tick()  # OBSERVING -> RECOVERING -> COMPLETED, then cleanup

    body = get(client, experiment_id)
    assert body["state"] == "COMPLETED"
    assert body["score"]["status"] == "SCORED"
    orch = body["orchestration"]
    events = [e["event"] for e in orch["events"]]
    assert events[0] == "auto run requested"
    assert any("CREATED -> BASELINING" in e for e in events)
    assert any("INJECTING -> OBSERVING" in e for e in events)
    assert any("-> COMPLETED" in e for e in events)
    assert orch["cleanup"]["done"] is True
    assert orch["cleanup"]["engine"] == "deleted"
    assert len(chaos.requests) == 1  # exactly one chaos run
    assert own_engine(experiment_id) not in chaos.engines
    for key in UNRELATED:  # unrelated engines untouched
        assert key in chaos.engines
    assert {c[2] for c in chaos.deleted_calls} == {experiment_id}
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None and stored.orchestration is not None


def test_terminal_experiments_are_not_reprocessed(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)
    reconciler.tick()
    before = get(client, experiment_id)

    assert reconciler.tick() == []
    assert get(client, experiment_id) == before


# --- restart / resume / duplicates -------------------------------------------------


def test_restart_resumes_without_a_second_chaos_run(
    client: TestClient,
    db_session: Session,
    kubernetes: FakeKubernetes,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
    clock: Clock,
    reconciler: Reconciler,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    del reconciler  # "API restart": nothing but the database survives

    restarted = new_reconciler(db_session, kubernetes, prometheus, chaos, clock)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)
    restarted.tick()

    assert get(client, experiment_id)["state"] == "COMPLETED"
    assert len(chaos.requests) == 1


def test_resume_injecting_with_recorded_engine_does_not_recreate_it(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    clock: Clock,
) -> None:
    chaos.statuses = [fault(FaultPhase.PENDING)]
    experiment_id = start(client)
    for _ in range(3):  # CREATED -> BASELINING -> INJECTING -> engine created
        reconciler.tick()
    assert get(client, experiment_id)["chaos"]["engine_name"]

    for _ in range(3):
        reconciler.tick()

    assert len(chaos.requests) == 1
    assert get(client, experiment_id)["state"] == "INJECTING"


def test_existing_engine_after_interrupted_start_is_stopped_not_rerun(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    clock: Clock,
) -> None:
    experiment_id = start(client)
    reconciler.tick()
    reconciler.tick()  # -> INJECTING, engine not yet recorded
    # Simulate: engine created by an earlier attempt that crashed before committing.
    chaos.engines[own_engine(experiment_id)] = {
        "app.kubernetes.io/managed-by": "autoresilience",
        "autoresilience.io/experiment-id": experiment_id,
    }

    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "INJECTION_FAILED"
    assert "already exists" in body["chaos"]["failure_reason"]
    assert chaos.stopped == [own_engine(experiment_id)]
    assert chaos.requests == []


def test_run_is_idempotent_and_requires_created(
    client: TestClient, reconciler: Reconciler
) -> None:
    experiment_id = start(client)
    first = get(client, experiment_id)["orchestration"]["requested_at"]

    assert client.post(f"/experiments/{experiment_id}/run").status_code == 202
    assert get(client, experiment_id)["orchestration"]["requested_at"] == first

    blocked = client.post(
        "/experiments",
        json=payload(
            target={"namespace": "kube-system", "kind": "Deployment", "name": "x"}
        ),
    ).json()["id"]
    assert client.post(f"/experiments/{blocked}/validate").json()["state"] == (
        "VALIDATION_FAILED"
    )
    response = client.post(f"/experiments/{blocked}/run")
    assert response.status_code == 409
    assert "passed validation" in response.json()["detail"]


def test_run_after_manual_validation_continues_from_baselining(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    """Builder flow: create -> /validate (shows the result) -> /run."""
    experiment_id = client.post("/experiments", json=payload()).json()["id"]
    validated = client.post(f"/experiments/{experiment_id}/validate").json()
    assert validated["state"] == "BASELINING"

    response = client.post(f"/experiments/{experiment_id}/run")

    assert response.status_code == 202
    orch = response.json()["orchestration"]
    assert orch["mode"] == "auto"
    assert orch["events"][0]["event"] == "auto run requested (already validated)"
    assert "BASELINING" in orch["state_since"]
    body = tick_until(reconciler, client, experiment_id, "OBSERVING", clock)
    assert body["validation_result"] == validated["validation_result"]  # not re-run
    fault_start = datetime.fromisoformat(body["chaos"]["created_at"]).timestamp()
    prometheus.healthy_recovery(fault_start)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)
    reconciler.tick()
    assert get(client, experiment_id)["state"] == "COMPLETED"
    assert len(chaos.requests) == 1


def test_run_refuses_experiments_already_in_progress(
    client: TestClient, reconciler: Reconciler
) -> None:
    experiment_id = client.post("/experiments", json=payload()).json()["id"]
    for step in ("validate", "baseline"):  # manual path -> INJECTING
        client.post(f"/experiments/{experiment_id}/{step}")
    assert get(client, experiment_id)["state"] == "INJECTING"

    assert client.post(f"/experiments/{experiment_id}/run").status_code == 409


@pytest.mark.parametrize("step", ["validate", "baseline", "inject", "observe"])
def test_manual_steps_rejected_for_auto_runs(
    client: TestClient, reconciler: Reconciler, step: str
) -> None:
    experiment_id = start(client)
    response = client.post(f"/experiments/{experiment_id}/{step}")
    assert response.status_code == 409
    assert "orchestrator" in response.json()["detail"]


def test_manual_experiments_are_not_driven(
    client: TestClient, reconciler: Reconciler
) -> None:
    experiment_id = client.post("/experiments", json=payload()).json()["id"]
    reconciler.tick()
    assert get(client, experiment_id)["state"] == "CREATED"


# --- timeouts -------------------------------------------------------------------------


def test_injection_timeout(
    client: TestClient, reconciler: Reconciler, chaos: FakeChaos, clock: Clock
) -> None:
    chaos.statuses = [fault(FaultPhase.PENDING)]
    experiment_id = start(client)
    tick_until(reconciler, client, experiment_id, "INJECTING", clock)
    reconciler.tick()  # engine created
    assert clock.now is not None
    clock.now += timedelta(seconds=121)

    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "INJECTION_FAILED"
    assert "not deleted within 120s" in body["chaos"]["failure_reason"]
    assert own_engine(experiment_id) in chaos.stopped


def test_observation_timeout(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    chaos.statuses, chaos.status_calls = [fault(FaultPhase.RUNNING)], 0
    clock.now = datetime.fromtimestamp(fault_start + 60 + 181, UTC)

    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "LITMUS_TIMEOUT"
    assert body["observation"]["result"]["cause"] == "platform"
    assert own_engine(experiment_id) in chaos.stopped


def test_recovery_timeout(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    prometheus.availability = [(t, 1.0) for t, _ in prometheus.availability]
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 60, UTC)
    reconciler.tick()
    assert get(client, experiment_id)["state"] == "RECOVERING"

    clock.now = datetime.fromtimestamp(fault_start + 60 + 301, UTC)
    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "RECOVERY_NOT_OBSERVED"


def test_baseline_timeout_is_platform_unknown(
    client: TestClient,
    reconciler: Reconciler,
    prometheus: FakePrometheus,
    chaos: FakeChaos,
    clock: Clock,
) -> None:
    prometheus.error = "Prometheus unreachable: connection refused"
    experiment_id = start(client)
    reconciler.tick()  # -> BASELINING
    reconciler.tick()  # baseline fails, still BASELINING
    assert get(client, experiment_id)["state"] == "BASELINING"
    assert clock.now is not None
    clock.now += timedelta(seconds=181)

    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "UNKNOWN"
    result = body["orchestration"]["result"]
    assert result["reason_code"] == "BASELINE_TIMEOUT"
    assert result["cause"] == "platform"
    assert "connection refused" in result["reason"]
    assert chaos.requests == []


def test_overall_deadline_stops_engine_and_ends_unknown(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    clock: Clock,
) -> None:
    chaos.statuses = [fault(FaultPhase.PENDING)]
    experiment_id = start(client)
    tick_until(reconciler, client, experiment_id, "INJECTING", clock)
    reconciler.tick()
    assert clock.now is not None
    clock.now = T0 + timedelta(seconds=1801)

    reconciler.tick()

    body = get(client, experiment_id)
    assert body["state"] == "UNKNOWN"
    assert body["orchestration"]["result"]["reason_code"] == "ORCHESTRATION_TIMEOUT"
    assert own_engine(experiment_id) in chaos.stopped


# --- abort ------------------------------------------------------------------------------


def test_abort_during_observation_stops_own_engine(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, _ = to_observing(reconciler, client, prometheus, clock)

    response = client.post(
        f"/experiments/{experiment_id}/abort", json={"reason": "operator saw errors"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["state"] == "ABORTED"
    abort = body["orchestration"]["abort"]
    assert abort["reason"] == "operator saw errors"
    assert abort["engine_stopped"] == f"ar-{experiment_id}"
    assert chaos.stopped == [own_engine(experiment_id)]
    assert any("-> ABORTED" in e["event"] for e in body["orchestration"]["events"])

    chaos.statuses, chaos.status_calls = [STOPPED], 0
    reconciler.tick()  # cleanup of the stopped engine
    assert get(client, experiment_id)["orchestration"]["cleanup"]["done"] is True
    for key in UNRELATED:
        assert key in chaos.engines


def test_abort_before_injection_touches_no_chaos(
    client: TestClient, reconciler: Reconciler, chaos: FakeChaos
) -> None:
    experiment_id = start(client)

    body = client.post(
        f"/experiments/{experiment_id}/abort", json={"reason": "wrong target"}
    ).json()

    assert body["state"] == "ABORTED"
    assert body["orchestration"]["abort"]["note"] == "no ChaosEngine had been created"
    assert chaos.stopped == []
    reconciler.tick()
    assert get(client, experiment_id)["state"] == "ABORTED"


def test_abort_with_stop_failure_is_recorded_and_cleanup_retries(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, _ = to_observing(reconciler, client, prometheus, clock)
    chaos.stop_error = "Failed to stop ChaosEngine: unreachable"

    body = client.post(
        f"/experiments/{experiment_id}/abort", json={"reason": "stop it"}
    ).json()

    assert body["state"] == "ABORTED"
    assert "unreachable" in body["orchestration"]["abort"]["stop_error"]
    chaos.stop_error = None
    chaos.statuses, chaos.status_calls = [fault(FaultPhase.RUNNING)], 0
    assert clock.now is not None
    clock.now += timedelta(seconds=121)  # grace over: delete the still-running engine
    reconciler.tick()
    assert get(client, experiment_id)["orchestration"]["cleanup"]["done"] is True
    assert own_engine(experiment_id) not in chaos.engines


@pytest.mark.parametrize("body", [{}, {"reason": ""}, {"reason": "x" * 501}])
def test_abort_requires_a_reason(
    client: TestClient, reconciler: Reconciler, body: dict[str, Any]
) -> None:
    experiment_id = start(client)
    assert (
        client.post(f"/experiments/{experiment_id}/abort", json=body).status_code == 422
    )


def test_abort_finished_experiment_is_rejected(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)
    reconciler.tick()
    stopped_before = list(chaos.stopped)

    response = client.post(
        f"/experiments/{experiment_id}/abort", json={"reason": "late"}
    )

    assert response.status_code == 409
    assert chaos.stopped == stopped_before


# --- cleanup ----------------------------------------------------------------------------


def test_cleanup_waits_for_running_engine_until_grace(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, _ = to_observing(reconciler, client, prometheus, clock)
    client.post(f"/experiments/{experiment_id}/abort", json={"reason": "stop"})
    chaos.statuses, chaos.status_calls = [fault(FaultPhase.RUNNING)], 0

    reconciler.tick()

    cleanup = get(client, experiment_id)["orchestration"]["cleanup"]
    assert cleanup.get("done") is not True
    assert cleanup["waiting"] == "ChaosEngine still finishing"
    assert own_engine(experiment_id) in chaos.engines


def test_cleanup_failure_is_retried(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    chaos.statuses, chaos.status_calls = [DONE], 0
    chaos.delete_error = "Failed to clean up ChaosEngine: 500"
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)

    reconciler.tick()
    cleanup = get(client, experiment_id)["orchestration"]["cleanup"]
    assert cleanup["done"] is False
    assert "500" in cleanup["error"]

    chaos.delete_error = None
    reconciler.tick()
    assert get(client, experiment_id)["orchestration"]["cleanup"]["done"] is True


def test_cleanup_never_touches_engines_it_does_not_own(
    client: TestClient,
    reconciler: Reconciler,
    chaos: FakeChaos,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, fault_start = to_observing(reconciler, client, prometheus, clock)
    # Something else replaced the engine under our name: labels no longer ours.
    chaos.engines[own_engine(experiment_id)] = {
        "autoresilience.io/experiment-id": "intruder"
    }
    chaos.statuses, chaos.status_calls = [DONE], 0
    clock.now = datetime.fromtimestamp(fault_start + 120, UTC)

    reconciler.tick()

    cleanup = get(client, experiment_id)["orchestration"]["cleanup"]
    assert cleanup["done"] is False
    assert "not owned" in cleanup["error"]
    assert own_engine(experiment_id) in chaos.engines
    for key in UNRELATED:
        assert key in chaos.engines


def test_one_failing_experiment_does_not_block_others(
    client: TestClient,
    reconciler: Reconciler,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad, good = start(client), start(client)

    original = Reconciler.step

    def flaky(self: Reconciler, db: Session, experiment: Experiment) -> None:
        if str(experiment.id) == bad:
            raise RuntimeError("boom")
        original(self, db, experiment)

    monkeypatch.setattr(Reconciler, "step", flaky)
    reconciler.tick()

    assert get(client, good)["state"] == "BASELINING"
    assert get(client, bad)["state"] == "CREATED"
    assert get(client, bad)["orchestration"]["last_error"] == "RuntimeError: boom"
