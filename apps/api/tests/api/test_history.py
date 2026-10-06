"""GET /experiments/history and GET /dashboard/summary (read-only aggregation)."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import FaultType, PodDeleteMode, WorkloadKind
from app.domain.state_machine import ExperimentState as S
from tests.api.test_experiments import payload

T0 = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def score(
    value: float | None,
    status: str = "SCORED",
    version: str = "v3",
    rating: str | None = "Good",
) -> dict[str, Any]:
    return {
        "score": value,
        "status": status,
        "version": version,
        "rating": rating,
        "explanation": "x",
    }


def add(
    db: Session,
    name: str,
    state: S,
    *,
    minutes: int,
    namespace: str = "shop",
    workload: str = "checkout",
    fault: FaultType = FaultType.POD_DELETE,
    mode: PodDeleteMode = PodDeleteMode.GRACEFUL,
    **evidence: Any,
) -> Experiment:
    e = Experiment(
        name=name,
        state=state,
        target_namespace=namespace,
        target_kind=WorkloadKind.DEPLOYMENT,
        target_name=workload,
        fault_type=fault,
        pod_delete_mode=mode,
        duration_seconds=30,
        affected_replicas=1,
        created_at=T0 + timedelta(minutes=minutes),
        updated_at=T0 + timedelta(minutes=minutes, seconds=90),
        **evidence,
    )
    db.add(e)
    db.commit()
    return e


def observation(ttr: float, outage: float | None) -> dict[str, Any]:
    client: dict[str, Any] = {"status": "OK", "requests": 700, "failed": 5}
    if outage is not None:
        client["outage"] = {
            "status": "OK",
            "pattern": "CONTINUOUS",
            "outage_seconds": outage,
        }
    return {
        "result": {"status": "COMPLETED", "reason": "recovered"},
        "recovery": {"time_to_recovery_seconds": ttr},
        "impact": {"client": client},
    }


@pytest.fixture
def data(db_session: Session) -> dict[str, Experiment]:
    return {
        "a": add(
            db_session,
            "fragile graceful",
            S.COMPLETED,
            minutes=1,
            namespace="resilience-sandbox",
            workload="fragile",
            score=score(80.4),
            observation=observation(11, 8.36),
            orchestration={"mode": "auto"},
            baseline={"status": "CAPTURED"},
        ),
        "b": add(
            db_session,
            "checkout graceful",
            S.COMPLETED,
            minutes=2,
            score=score(100.0, rating="Excellent"),
            observation=observation(1, 0.0),
        ),
        "c": add(
            db_session,
            "fragile force",
            S.COMPLETED,
            minutes=3,
            namespace="resilience-sandbox",
            workload="fragile",
            mode=PodDeleteMode.FORCE,
            score=score(76.8),
            observation=observation(10, 10.48),
        ),
        "d": add(
            db_session,
            "old methodology",
            S.COMPLETED,
            minutes=4,
            score=score(90.0, version="v2"),
            observation=observation(2, None),
        ),
        "e": add(
            db_session,
            "kube-system probe",
            S.VALIDATION_FAILED,
            minutes=5,
            namespace="kube-system",
            workload="coredns",
            validation_result={
                "passed": False,
                "static_checks": [
                    {
                        "name": "namespace_not_forbidden",
                        "status": "FAILED",
                        "message": "Namespace 'kube-system' is protected",
                    }
                ],
                "cluster_checks": [],
            },
        ),
        "f": add(
            db_session,
            "litmus timeout",
            S.UNKNOWN,
            minutes=6,
            namespace="resilience-sandbox",
            workload="fragile",
            score=score(None, status="NOT_SCORED", rating=None),
            observation={
                "result": {
                    "status": "UNKNOWN",
                    "reason": "Litmus did not finish",
                    "cause": "platform",
                }
            },
        ),
        "g": add(
            db_session,
            "aborted run",
            S.ABORTED,
            minutes=7,
            orchestration={"mode": "auto", "abort": {"reason": "operator stop"}},
        ),
        "h": add(
            db_session, "draft", S.CREATED, minutes=8, fault=FaultType.POD_CPU_HOG
        ),
    }


def history(client: TestClient, **params: Any) -> dict[str, Any]:
    response = client.get("/experiments/history", params=params)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def names(body: dict[str, Any]) -> list[str]:
    return [i["name"] for i in body["items"]]


# --- history ------------------------------------------------------------------------


@pytest.mark.usefixtures("data")
def test_history_default_is_newest_first_with_total(client: TestClient) -> None:
    body = history(client)
    assert body["total"] == 8
    assert (body["limit"], body["offset"]) == (25, 0)
    assert names(body)[:2] == ["draft", "aborted run"]


def test_history_summary_fields(
    client: TestClient, data: dict[str, Experiment]
) -> None:
    item = next(i for i in history(client)["items"] if i["name"] == "fragile graceful")
    assert item["score"] == {
        "score": 80.4,
        "rating": "Good",
        "status": "SCORED",
        "version": "v3",
    }
    assert item["time_to_recovery_seconds"] == 11
    assert item["client_outage_seconds"] == 8.36
    assert item["outcome_reason"] == "recovered"
    assert item["auto"] is True and item["has_baseline"] is True
    assert "observation" not in item and "baseline" not in item  # slim rows
    blocked = next(
        i for i in history(client)["items"] if i["name"] == "kube-system probe"
    )
    assert blocked["outcome_reason"] == "Namespace 'kube-system' is protected"
    aborted = next(i for i in history(client)["items"] if i["name"] == "aborted run")
    assert aborted["outcome_reason"] == "operator stop"


@pytest.mark.usefixtures("data")
@pytest.mark.parametrize(
    ("params", "expected"),
    [
        ({"q": "FRAGILE"}, {"fragile graceful", "fragile force", "litmus timeout"}),
        ({"q": "kube-sys"}, {"kube-system probe"}),
        ({"state": ["UNKNOWN", "ABORTED"]}, {"litmus timeout", "aborted run"}),
        ({"fault_type": "pod-cpu-hog"}, {"draft"}),
        (
            {"namespace": "resilience-sandbox", "state": "COMPLETED"},
            {"fragile graceful", "fragile force"},
        ),
        ({"q": "nothing-matches"}, set()),
    ],
)
def test_history_filters(
    client: TestClient, params: dict[str, Any], expected: set[str]
) -> None:
    body = history(client, **params)
    assert set(names(body)) == expected
    assert body["total"] == len(expected)


@pytest.mark.usefixtures("data")
def test_history_pagination(client: TestClient) -> None:
    first = history(client, limit=3, offset=0)
    second = history(client, limit=3, offset=3)
    last = history(client, limit=3, offset=6)
    assert first["total"] == second["total"] == last["total"] == 8
    assert len(first["items"]) == len(second["items"]) == 3 and len(last["items"]) == 2
    assert not set(names(first)) & set(names(second))


@pytest.mark.usefixtures("data")
def test_history_sorting(client: TestClient) -> None:
    by_score = names(history(client, sort="score", order="desc"))
    assert by_score[:4] == [
        "checkout graceful",
        "old methodology",
        "fragile graceful",
        "fragile force",
    ]
    assert set(by_score[4:]) == {
        "kube-system probe",
        "litmus timeout",
        "aborted run",
        "draft",
    }  # no score: last
    assert names(history(client, sort="name", order="asc"))[0] == "aborted run"
    assert (
        names(history(client, sort="created_at", order="asc"))[0] == "fragile graceful"
    )


@pytest.mark.parametrize(
    "params",
    [
        {"state": "NOPE"},
        {"fault_type": "rm-rf"},
        {"sort": "id"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
    ],
)
def test_history_rejects_invalid_params(
    client: TestClient, params: dict[str, Any]
) -> None:
    assert client.get("/experiments/history", params=params).status_code == 422


def test_history_route_does_not_shadow_experiment_routes(client: TestClient) -> None:
    created = client.post("/experiments", json=payload()).json()
    assert client.get(f"/experiments/{created['id']}").json()["id"] == created["id"]
    assert len(client.get("/experiments").json()) == 1  # existing list unchanged
    assert history(client)["items"][0]["id"] == created["id"]
    assert client.get(f"/experiments/{uuid.uuid4()}").status_code == 404


# --- dashboard ------------------------------------------------------------------------


def test_dashboard_summary_empty(client: TestClient) -> None:
    body = client.get("/dashboard/summary").json()
    assert body["total"] == 0
    assert set(body["by_state"].values()) == {0}
    assert body["scores"]["count"] == 0 and body["scores"]["average"] is None
    assert body["recovery_time_seconds"] == {
        "count": 0,
        "median": None,
        "minimum": None,
        "maximum": None,
    }
    assert (
        body["score_history"] == []
        and body["recent"] == []
        and body["namespaces"] == []
    )


@pytest.mark.usefixtures("data")
def test_dashboard_summary_aggregates_only_real_records(client: TestClient) -> None:
    body = client.get("/dashboard/summary").json()

    assert body["total"] == 8
    assert body["by_state"]["COMPLETED"] == 4
    assert len(body["by_state"]) == 11
    assert body["outcomes"] == {
        "active": 1,
        "completed": 4,
        "failed": 1,
        "aborted": 1,
        "undetermined": 1,
    }

    scores = body["scores"]
    assert scores["version"] == "v3"
    assert scores["count"] == 3  # v2 record excluded, NOT_SCORED excluded
    assert scores["average"] == round((80.4 + 100.0 + 76.8) / 3, 1)
    assert (scores["minimum"], scores["maximum"]) == (76.8, 100.0)
    assert scores["by_rating"] == {"Good": 2, "Excellent": 1}
    assert (
        scores["not_scored"],
        scores["other_versions"],
        scores["not_recovered"],
    ) == (1, 1, 0)

    assert body["recovery_time_seconds"] == {
        "count": 4,
        "median": 6.0,
        "minimum": 1.0,
        "maximum": 11.0,
    }
    assert body["client_outage_seconds"] == {
        "count": 3,
        "median": 8.36,
        "minimum": 0.0,
        "maximum": 10.48,
    }

    history_points = body["score_history"]
    assert [p["score"] for p in history_points] == [
        80.4,
        100.0,
        76.8,
    ]  # oldest first, v3 only
    assert history_points[0]["namespace"] == "resilience-sandbox"

    namespaces = {n["namespace"]: n for n in body["namespaces"]}
    assert namespaces["resilience-sandbox"]["total"] == 3
    assert namespaces["resilience-sandbox"]["completed"] == 2
    assert namespaces["shop"]["total"] == 4
    assert [r["name"] for r in body["recent"]][:2] == ["draft", "aborted run"]
