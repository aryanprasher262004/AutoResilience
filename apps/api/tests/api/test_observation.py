import uuid
from datetime import datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.integrations.chaos_provider import ChaosProviderError, FaultPhase, FaultStatus
from tests.api.test_injection import ready_to_inject
from tests.conftest import Clock, FakeChaos, FakePrometheus, fault

COMPLETED_PASS = FaultStatus(
    FaultPhase.COMPLETED, "completed", "Completed", "Pass", "pod-delete-x"
)
COMPLETED_FAIL = FaultStatus(
    FaultPhase.FAILED, "completed", "Completed", "Fail", "pod-delete-x"
)


def observing(client: TestClient) -> tuple[str, datetime]:
    """An experiment in OBSERVING; returns its id and the fault start time."""
    experiment_id = ready_to_inject(client)
    body = client.post(f"/experiments/{experiment_id}/inject").json()
    assert body["state"] == "OBSERVING"
    return experiment_id, datetime.fromisoformat(body["chaos"]["created_at"])


def observe(client: TestClient, experiment_id: str) -> dict[str, Any]:
    response = client.post(f"/experiments/{experiment_id}/observe")
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


@pytest.fixture
def litmus_done(chaos: FakeChaos) -> None:
    chaos.statuses = [COMPLETED_PASS]


def at(clock: Clock, start: datetime, seconds: float) -> None:
    clock.now = start + timedelta(seconds=seconds)


# --- happy path ----------------------------------------------------------------


@pytest.mark.usefixtures("litmus_done")
def test_pass_and_recovery_completes_with_evidence(
    client: TestClient,
    db_session: Session,
    prometheus: FakePrometheus,
    clock: Clock,
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    obs = body["observation"]
    assert obs["result"] == {
        "status": "COMPLETED",
        "reason_code": "RECOVERED",
        "reason": (
            "1 replacement pod(s) Ready, then 4 consecutive samples >= 2 available; "
            "5xx ratio 0.0 <= limit 0.01"
        ),
        "cause": None,
    }
    assert obs["litmus"]["verdict"] == "Pass"
    assert obs["litmus"]["chaos_result"]["verdict"] == "Pass"
    assert obs["litmus"]["finished_at"] is not None
    recovery = obs["recovery"]
    assert recovery["status"] == "RECOVERED"
    assert recovery["time_to_recovery_seconds"] == 2
    assert len(recovery["stable_streak"]) == 4
    assert recovery["error_check"]["ok"] is True
    impact = obs["impact"]
    assert impact["availability_dip_observed"] is False
    assert impact["restarts_in_window"] == 0
    assert [p["pod"] for p in impact["replacement_pods"]] == ["checkout-new-bbbbb"]
    assert obs["target"]["deleted_pods"] == ["checkout-a"]
    assert obs["target"]["deleted_pods_still_present"] == []
    assert "Ready" in obs["rule"]
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.state == "COMPLETED"
    assert stored.observation is not None
    assert stored.observation["recovery"]["recovered_at"] == recovery["recovered_at"]


def test_stays_observing_until_litmus_finishes(
    client: TestClient, chaos: FakeChaos, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    chaos.statuses = [fault(FaultPhase.RUNNING)]
    chaos.status_calls = 0
    at(clock, start, 30)

    body = observe(client, experiment_id)

    assert body["state"] == "OBSERVING"
    assert body["observation"]["result"]["status"] == "IN_PROGRESS"
    assert body["observation"]["litmus"]["experiment_status"] == "Running"

    chaos.statuses = [COMPLETED_PASS]
    at(clock, start, 120)
    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    assert body["observation"]["evaluations"] == 2


@pytest.mark.usefixtures("litmus_done")
def test_waits_in_recovering_until_streak_is_long_enough(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 35)  # only 2 samples after the replacement became Ready

    body = observe(client, experiment_id)

    assert body["state"] == "RECOVERING"
    assert body["observation"]["recovery"]["status"] == "NOT_RECOVERED"
    assert "2/4 consecutive samples" in body["observation"]["recovery"]["message"]

    at(clock, start, 120)
    assert observe(client, experiment_id)["state"] == "COMPLETED"


@pytest.mark.usefixtures("litmus_done")
def test_target_without_request_metrics_skips_error_check(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    prometheus.values["request_series"] = None  # baseline: requests UNAVAILABLE
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    assert body["observation"]["recovery"]["error_check"] == {"applicable": False}


# --- Litmus outcomes ----------------------------------------------------------------


def test_litmus_fail_with_recovery_is_conflicting_unknown(
    client: TestClient, chaos: FakeChaos, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    chaos.statuses, chaos.status_calls = [COMPLETED_FAIL], 0
    chaos.result = {
        "phase": "Completed",
        "verdict": "Fail",
        "fail_step": "[post-chaos]: Failed to verify that the AUT is running",
        "probe_success_percentage": "0",
    }
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    result = body["observation"]["result"]
    assert result["reason_code"] == "LITMUS_VERDICT_FAIL"
    assert result["cause"] == "conflicting_evidence"
    assert "post-chaos" in result["reason"]
    assert body["observation"]["recovery"]["status"] == "RECOVERED"  # evidence kept


@pytest.mark.parametrize(
    "status",
    [
        FaultStatus(FaultPhase.FAILED, "initialized", "Running", "Error", "pd"),
        FaultStatus(FaultPhase.FAILED, "stopped", "Running", "Stopped", "pd"),
    ],
)
def test_litmus_error_is_platform_unknown(
    client: TestClient, chaos: FakeChaos, clock: Clock, status: FaultStatus
) -> None:
    experiment_id, start = observing(client)
    chaos.statuses, chaos.status_calls = [status], 0
    at(clock, start, 30)

    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "LITMUS_ERROR"
    assert body["observation"]["result"]["cause"] == "platform"


def test_litmus_not_finishing_times_out_and_stops_engine(
    client: TestClient, chaos: FakeChaos, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    chaos.statuses, chaos.status_calls = [fault(FaultPhase.RUNNING)], 0
    at(clock, start, 60 + 180 + 1)  # duration + grace

    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "LITMUS_TIMEOUT"
    assert body["observation"]["litmus"]["stopped"] is True
    assert chaos.stopped == [("shop", f"ar-{experiment_id}")]


def test_litmus_unreadable_waits_then_unknown(
    client: TestClient, chaos: FakeChaos, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    chaos.statuses = [ChaosProviderError("Failed to read ChaosEngine: 500")]
    chaos.status_calls = 0
    at(clock, start, 30)

    body = observe(client, experiment_id)
    assert body["state"] == "OBSERVING"
    assert "500" in body["observation"]["litmus"]["last_error"]

    at(clock, start, 60 + 180 + 1)
    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "LITMUS_UNREADABLE"
    assert body["observation"]["result"]["cause"] == "platform"


@pytest.mark.usefixtures("litmus_done")
def test_chaos_result_read_error_is_recorded_not_fatal(
    client: TestClient, chaos: FakeChaos, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    chaos.result_error = "Failed to read ChaosResult: 404"
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    assert "404" in body["observation"]["litmus"]["chaos_result"]["error"]


# --- recovery failures ---------------------------------------------------------


@pytest.mark.usefixtures("litmus_done")
def test_recovery_timeout_with_reliable_data_is_application_unknown(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp(), desired=2)
    prometheus.availability = [
        (t, 1.0) for t, _ in prometheus.availability
    ]  # stuck at 1
    at(clock, start, 60)
    assert observe(client, experiment_id)["state"] == "RECOVERING"

    at(clock, start, 60 + 300 + 1)  # Litmus finished at +60, timeout 300
    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    result = body["observation"]["result"]
    assert result["reason_code"] == "RECOVERY_NOT_OBSERVED"
    assert result["cause"] == "application"
    assert body["observation"]["impact"]["availability_dip_observed"] is True
    assert body["observation"]["impact"]["min_available_replicas"] == 1


@pytest.mark.usefixtures("litmus_done")
def test_missing_prometheus_data_is_platform_unknown(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    prometheus.availability = []
    at(clock, start, 60)
    assert observe(client, experiment_id)["state"] == "RECOVERING"

    at(clock, start, 60 + 301)
    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "INSUFFICIENT_DATA"
    assert body["observation"]["result"]["cause"] == "platform"


@pytest.mark.usefixtures("litmus_done")
def test_data_gaps_are_platform_not_application(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    s = start.timestamp()
    prometheus.availability = [(s + 15, 2.0), (s + 30, 2.0), (s + 200, 2.0)]
    at(clock, start, 60)
    observe(client, experiment_id)

    at(clock, start, 60 + 301)
    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "INSUFFICIENT_DATA"
    assert "gaps" in body["observation"]["result"]["reason"]


@pytest.mark.usefixtures("litmus_done")
def test_prometheus_down_waits_then_platform_unknown(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.error = "Prometheus unreachable: connection refused"
    at(clock, start, 60)

    body = observe(client, experiment_id)
    assert body["state"] == "RECOVERING"
    assert "connection refused" in body["observation"]["last_error"]

    at(clock, start, 60 + 301)
    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["reason_code"] == "PROMETHEUS_UNAVAILABLE"
    assert body["observation"]["result"]["cause"] == "platform"


@pytest.mark.usefixtures("litmus_done")
def test_high_error_ratio_blocks_recovery(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    prometheus.window["errors"] = 20.0  # 20% 5xx vs baseline 0%
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "RECOVERING"
    assert body["observation"]["recovery"]["error_check"]["ok"] is False
    assert "5xx ratio 0.2 > limit 0.01" in body["observation"]["recovery"]["message"]


# --- state guards ----------------------------------------------------------------


def test_observe_requires_observing_or_recovering(client: TestClient) -> None:
    experiment_id = ready_to_inject(client)  # INJECTING

    response = client.post(f"/experiments/{experiment_id}/observe")

    assert response.status_code == 409


@pytest.mark.usefixtures("litmus_done")
def test_observe_after_completion_is_rejected(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 120)
    assert observe(client, experiment_id)["state"] == "COMPLETED"

    assert client.post(f"/experiments/{experiment_id}/observe").status_code == 409


def test_observe_unknown_experiment_returns_404(client: TestClient) -> None:
    assert client.post(f"/experiments/{uuid.uuid4()}/observe").status_code == 404


# --- scoring on completion ------------------------------------------------------


@pytest.mark.usefixtures("litmus_done")
def test_completed_experiment_is_scored_and_retrievable(
    client: TestClient, db_session: Session, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    assert body["score"]["status"] == "SCORED"
    response = client.get(f"/experiments/{experiment_id}/score")
    assert response.status_code == 200
    score = response.json()
    assert score == body["score"]
    assert score["score"] == 100.0  # recovered in 2s, no dip/restarts/errors, Pass
    assert score["version"] == "v2"
    assert {c["name"] for c in score["components"]} == {
        "recovery_time",
        "availability",
        "request_failures",
        "restarts",
        "litmus_verdict",
    }
    stored = db_session.get(Experiment, uuid.UUID(experiment_id))
    assert stored is not None
    assert stored.score is not None
    assert stored.score["score"] == 100.0


def test_platform_unknown_gets_not_scored(
    client: TestClient, chaos: FakeChaos, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    chaos.statuses, chaos.status_calls = [fault(FaultPhase.RUNNING)], 0
    at(clock, start, 60 + 181)

    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    score = client.get(f"/experiments/{experiment_id}/score").json()
    assert score["status"] == "NOT_SCORED"
    assert score["score"] is None
    assert "LITMUS_TIMEOUT" in score["explanation"]


@pytest.mark.usefixtures("litmus_done")
def test_application_unknown_gets_capped_score(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    prometheus.availability = [(t, 1.0) for t, _ in prometheus.availability]
    at(clock, start, 60)
    observe(client, experiment_id)
    at(clock, start, 60 + 301)

    body = observe(client, experiment_id)

    assert body["state"] == "UNKNOWN"
    assert body["observation"]["result"]["cause"] == "application"
    score = client.get(f"/experiments/{experiment_id}/score").json()
    assert score["status"] == "SCORED_NOT_RECOVERED"
    assert score["score"] <= 40


def test_score_not_available_before_finish(client: TestClient) -> None:
    experiment_id, _ = observing(client)

    response = client.get(f"/experiments/{experiment_id}/score")

    assert response.status_code == 404
    assert "OBSERVING" in response.json()["detail"]


def test_score_unknown_experiment_404(client: TestClient) -> None:
    assert client.get(f"/experiments/{uuid.uuid4()}/score").status_code == 404


# --- client-side evidence and v2 scoring --------------------------------------


@pytest.mark.usefixtures("litmus_done")
def test_client_disruption_is_recorded_and_penalized(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    # Second scrape interval after the fault: 9 connection errors, 3 timeouts.
    prometheus.client_counters(
        start.timestamp(), {2: {"connection_error": 9, "timeout": 3}}
    )
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["state"] == "COMPLETED"
    seen = body["observation"]["impact"]["client"]
    assert seen["status"] == "OK"
    assert (seen["connection_error"], seen["timeout"], seen["http_error"]) == (9, 3, 0)
    assert seen["failed"] == 12
    assert seen["latency_p95_seconds"] == 0.006
    assert len(seen["failure_intervals"]) == 1
    score = client.get(f"/experiments/{experiment_id}/score").json()
    failures = next(c for c in score["components"] if c["name"] == "request_failures")
    assert failures["raw"]["source"] == "client"
    assert failures["raw"]["connection_error"] == 9
    assert failures["normalized"] < 1
    assert "9 connection error, 3 timeout" in failures["reason"]
    assert score["score"] < 100
    assert "request_failures -" in score["explanation"]


@pytest.mark.usefixtures("litmus_done")
def test_v1_can_be_recomputed_from_the_same_evidence(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    prometheus.client_counters(start.timestamp(), {2: {"connection_error": 30}})
    at(clock, start, 120)
    observe(client, experiment_id)

    v2 = client.get(f"/experiments/{experiment_id}/score").json()
    v1 = client.get(f"/experiments/{experiment_id}/score?version=v1").json()

    assert (v1["version"], v2["version"]) == ("v1", "v2")
    assert v1["score"] == 100.0  # server/K8s evidence saw nothing
    assert v2["score"] < v1["score"]  # the client did
    assert (
        client.get(f"/experiments/{experiment_id}/score?version=v9").status_code == 422
    )


@pytest.mark.usefixtures("litmus_done")
def test_target_without_client_metrics_still_scores(
    client: TestClient, prometheus: FakePrometheus, clock: Clock
) -> None:
    prometheus.values["client_series"] = None  # baseline: client UNAVAILABLE
    experiment_id, start = observing(client)
    prometheus.healthy_recovery(start.timestamp())
    at(clock, start, 120)

    body = observe(client, experiment_id)

    assert body["observation"]["impact"]["client"]["status"] == "UNAVAILABLE"
    failures = next(
        c for c in body["score"]["components"] if c["name"] == "request_failures"
    )
    assert failures["raw"]["source"] == "server"
    assert "server-side fallback: no client-side baseline" in failures["reason"]
    assert body["score"]["score"] == 100.0
