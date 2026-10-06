"""Resilience Score v2: client-side request failures.

Weights 35/15/30/10/10; failure thresholds as v1 (+0.001 full marks, +0.05 zero).
Hand-computed expectations; see docs/scoring/resilience-score-v2.md.
"""

from typing import Any

import pytest

from app.services.scoring.resilience_score import CURRENT_VERSION, score_experiment
from tests.unit.test_resilience_score import APP_UNKNOWN, baseline, observation


def client_baseline(*, failure_ratio: float = 0.0, rate: float = 9.9) -> dict[str, Any]:
    b = baseline()
    b["client"] = {
        "status": "OK",
        "values": {
            "client_rate_rps": rate,
            "client_failure_rate_rps": rate * failure_ratio,
            "client_failure_ratio": failure_ratio,
            "client_latency_p95_seconds": 0.005,
        },
    }
    return b


def client_impact(
    *,
    requests: int = 1000,
    connection_error: int = 0,
    timeout: int = 0,
    http_error: int = 0,
    starts_before_fault: bool = True,
) -> dict[str, Any]:
    failed = connection_error + timeout + http_error
    return {
        "status": "OK",
        "requests": requests,
        "success": requests - failed,
        "connection_error": connection_error,
        "timeout": timeout,
        "http_error": http_error,
        "failed": failed,
        "failure_ratio": round(failed / requests, 4) if requests else None,
        "starts_before_fault": starts_before_fault,
        "failure_intervals": [{"failed": failed}] if failed else [],
        "counted_from": "a",
        "counted_to": "b",
    }


def v2(
    state: str = "COMPLETED",
    *,
    b: dict[str, Any] | None = None,
    client: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    obs = observation(**kwargs)
    if client is not None:
        obs["impact"]["client"] = client
    return score_experiment(state, b or client_baseline(), obs)


def failures(result: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in result["components"] if c["name"] == "request_failures")


def test_v2_is_the_current_version() -> None:
    assert CURRENT_VERSION == "v2"
    result = v2(client=client_impact())
    assert result["version"] == "v2"
    assert result["weights"] == {
        "recovery_time": 35,
        "availability": 15,
        "request_failures": 30,
        "restarts": 10,
        "litmus_verdict": 10,
    }


def test_clean_client_traffic_scores_100() -> None:
    result = v2(client=client_impact())

    assert result["score"] == 100.0
    assert failures(result)["raw"]["source"] == "client"
    assert failures(result)["reason"].startswith("Client saw 0/1000 requests fail")


def test_connection_errors_and_timeouts_are_penalized() -> None:
    # 9 connection errors + 3 timeouts in 1000 requests: ratio 0.012, +0.012
    result = v2(client=client_impact(connection_error=9, timeout=3))

    f = failures(result)
    assert f["raw"]["fault_failure_ratio"] == 0.012
    assert f["normalized"] == 0.7755  # 1 - (0.012 - 0.001) / 0.049
    assert f["contribution"] == 23.27  # 0.7755 * 30
    assert result["score"] == 93.3
    assert "9 connection error, 3 timeout" in f["reason"]


def test_http_errors_seen_by_client_are_penalized() -> None:
    f = failures(v2(client=client_impact(http_error=50)))  # +0.05 -> zero
    assert f["normalized"] == 0.0
    assert "50 http error" in f["reason"]


def test_failures_are_relative_to_client_baseline() -> None:
    result = v2(b=client_baseline(failure_ratio=0.01), client=client_impact(timeout=10))
    assert failures(result)["normalized"] == 1.0


def test_client_failure_boundaries() -> None:
    assert failures(v2(client=client_impact(timeout=1)))["normalized"] == 1.0  # +0.001
    assert failures(v2(client=client_impact(timeout=2)))["normalized"] == 0.9796


def test_missing_client_metrics_fall_back_to_server_side() -> None:
    result = v2(b=baseline(), requests=100, errors=3)  # no client group at all

    f = failures(result)
    assert f["raw"]["source"] == "server"
    assert f["normalized"] == 0.4082  # v1 server-side formula
    assert "server-side fallback: no client-side baseline" in f["reason"]


def test_client_window_with_no_requests_is_a_measurement_gap_not_a_failure() -> None:
    result = v2(client=client_impact(requests=0))

    f = failures(result)
    assert f["raw"]["source"] == "server"
    assert "measurement gap, not a target failure" in f["reason"]
    assert result["score"] == 100.0


def test_neither_client_nor_server_metrics_is_not_applicable() -> None:
    result = v2(b=baseline(requests=False), requests=None)

    assert failures(result)["status"] == "NOT_APPLICABLE"
    assert result["score"] == 100.0
    # 35 / 70 of the applicable weight
    assert result["components"][0]["effective_weight"] == 50.0


def test_late_counting_is_flagged() -> None:
    f = failures(v2(client=client_impact(starts_before_fault=False)))
    assert "early failures may be missed" in f["reason"]


def test_availability_weight_reduced() -> None:
    result = v2(client=client_impact(), min_available=1)
    assert result["score"] == 92.5  # 100 - 0.5 * 15


def test_platform_unknown_still_not_scored_in_v2() -> None:
    result = v2(
        "UNKNOWN",
        client=client_impact(connection_error=500),
        recovered=False,
        ttr=None,
        result={
            "status": "UNKNOWN",
            "reason_code": "LITMUS_TIMEOUT",
            "cause": "platform",
        },
    )
    assert result["status"] == "NOT_SCORED"
    assert result["score"] is None
    assert result["version"] == "v2"


def test_application_unknown_capped_in_v2() -> None:
    result = v2(
        "UNKNOWN",
        client=client_impact(connection_error=20),
        recovered=False,
        ttr=None,
        result=APP_UNKNOWN,
    )
    assert result["status"] == "SCORED_NOT_RECOVERED"
    assert result["score"] <= 40


def test_v1_and_v2_differ_only_where_documented() -> None:
    b = client_baseline()
    obs = observation()
    obs["impact"]["client"] = client_impact(connection_error=20)

    v1 = score_experiment("COMPLETED", b, obs, version="v1")
    v2_ = score_experiment("COMPLETED", b, obs, version="v2")

    assert v1["score"] == 100.0  # server-side 0 errors
    assert v2_["score"] < 100.0


def test_unknown_version_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown scoring version"):
        score_experiment("COMPLETED", baseline(), observation(), version="v9")
