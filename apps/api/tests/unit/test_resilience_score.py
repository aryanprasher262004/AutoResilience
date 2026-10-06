"""Resilience Score v1 (pinned with version="v1" so v1 stays reproducible after v2).

Expected values are computed by hand from the documented weights (35/25/20/10/10)
and thresholds (docs/scoring/resilience-score-v1.md)."""

from typing import Any

import pytest

from app.services.scoring.resilience_score import score_experiment


def baseline(
    *,
    requests: bool = True,
    rate: float = 1.5,
    error_ratio: float = 0.0,
    desired: int = 2,
) -> dict[str, Any]:
    return {
        "status": "CAPTURED",
        "availability": {"status": "OK", "values": {"desired_replicas": desired}},
        "restarts": {
            "status": "OK",
            "values": {"restarts_total": 0, "restarts_in_window": 0},
        },
        "requests": (
            {
                "status": "OK",
                "values": {
                    "request_rate_rps": rate,
                    "error_rate_rps": rate * error_ratio,
                    "error_ratio": error_ratio,
                },
            }
            if requests
            else {"status": "UNAVAILABLE", "values": {}}
        ),
    }


def observation(
    *,
    ttr: float | None = 1.0,
    recovered: bool = True,
    min_available: int | None = 2,
    restarts: int | None = 0,
    requests: float | None = 100.0,
    errors: float | None = 0.0,
    verdict: str = "Pass",
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "result": result
        or {
            "status": "COMPLETED",
            "reason_code": "RECOVERED",
            "reason": "ok",
            "cause": None,
        },
        "litmus": {
            "verdict": verdict,
            "chaos_result": {"verdict": verdict, "fail_step": None},
        },
        "recovery": {
            "status": "RECOVERED" if recovered else "NOT_RECOVERED",
            "time_to_recovery_seconds": ttr,
        },
        "impact": {
            "availability_samples": 5,
            "min_available_replicas": min_available,
            "restarts_in_window": restarts,
            "requests_in_window": requests,
            "errors_in_window": errors if requests is not None else None,
        },
    }


APP_UNKNOWN = {
    "status": "UNKNOWN",
    "reason_code": "RECOVERY_NOT_OBSERVED",
    "reason": "did not recover",
    "cause": "application",
}


def score(state: str = "COMPLETED", **kwargs: Any) -> dict[str, Any]:
    b = kwargs.pop("baseline", None) or baseline()
    return score_experiment(state, b, observation(**kwargs), version="v1")


def component(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(c for c in result["components"] if c["name"] == name)


# --- strong / slow recovery ----------------------------------------------------


def test_strong_recovery_scores_100() -> None:
    result = score()

    assert result["status"] == "SCORED"
    assert result["score"] == 100.0
    assert result["rating"] == "Excellent"
    assert result["version"] == "v1"
    assert "Full marks" in result["explanation"]
    assert [c["name"] for c in result["components"]] == [
        "recovery_time",
        "availability",
        "error_ratio",
        "restarts",
        "litmus_verdict",
    ]
    for c in result["components"]:
        assert c["normalized"] == 1.0
        assert c["contribution"] == c["effective_weight"] == c["weight"]


def test_slow_recovery_loses_recovery_points() -> None:
    result = score(ttr=65)  # halfway between 10s and 120s

    recovery = component(result, "recovery_time")
    assert recovery["normalized"] == 0.5
    assert recovery["contribution"] == 17.5
    assert recovery["raw"] == {"recovered": True, "time_to_recovery_seconds": 65}
    assert result["score"] == 82.5
    assert result["rating"] == "Good"
    assert "recovery_time -17.5" in result["explanation"]


@pytest.mark.parametrize(
    ("ttr", "normalized"),
    [(0, 1.0), (10, 1.0), (10.11, 0.999), (120, 0.0), (119.89, 0.001), (600, 0.0)],
)
def test_recovery_time_boundaries(ttr: float, normalized: float) -> None:
    assert component(score(ttr=ttr), "recovery_time")["normalized"] == normalized


# --- availability, restarts, errors ----------------------------------------------


def test_availability_dip_is_penalized() -> None:
    result = score(min_available=1)

    availability = component(result, "availability")
    assert availability["normalized"] == 0.5
    assert availability["contribution"] == 12.5
    assert "1/2 replicas (1 lost)" in availability["reason"]
    assert result["score"] == 87.5


def test_total_availability_loss() -> None:
    assert component(score(min_available=0), "availability")["normalized"] == 0.0


@pytest.mark.parametrize(
    ("restarts", "normalized", "total"),
    [(0, 1.0, 100.0), (1, 0.5, 95.0), (2, 0.0, 90.0), (7, 0.0, 90.0)],
)
def test_restarts(restarts: int, normalized: float, total: float) -> None:
    result = score(restarts=restarts)
    assert component(result, "restarts")["normalized"] == normalized
    assert result["score"] == total


def test_error_ratio_degradation() -> None:
    result = score(requests=100, errors=3)  # +0.03 over a 0 baseline

    errors = component(result, "error_ratio")
    assert errors["raw"]["fault_error_ratio"] == 0.03
    assert errors["raw"]["increase"] == 0.03
    assert errors["normalized"] == 0.4082  # 1 - (0.03 - 0.001) / (0.05 - 0.001)
    assert result["score"] == 88.2


@pytest.mark.parametrize(
    ("errors", "normalized"),
    [(0.1, 1.0), (5, 0.0), (50, 0.0)],  # +0.001, +0.05, +0.5
)
def test_error_ratio_boundaries(errors: float, normalized: float) -> None:
    assert (
        component(score(requests=100, errors=errors), "error_ratio")["normalized"]
        == normalized
    )


def test_error_ratio_is_relative_to_baseline() -> None:
    result = score(baseline=baseline(error_ratio=0.02), requests=100, errors=2)
    assert component(result, "error_ratio")["normalized"] == 1.0


def test_no_requests_during_fault_despite_baseline_traffic_scores_zero() -> None:
    errors = component(score(requests=0), "error_ratio")
    assert errors["status"] == "SCORED"
    assert errors["normalized"] == 0.0
    assert "no requests were recorded" in errors["reason"]


# --- missing optional request metrics ----------------------------------------------


def test_missing_request_metrics_are_not_applicable_and_reweighted() -> None:
    result = score(baseline=baseline(requests=False), requests=None)

    errors = component(result, "error_ratio")
    assert errors["status"] == "NOT_APPLICABLE"
    assert errors["normalized"] is None
    assert errors["contribution"] == 0
    assert result["score"] == 100.0  # not treated as a failure
    assert component(result, "recovery_time")["effective_weight"] == 43.75  # 35 / 80
    assert sum(c["effective_weight"] for c in result["components"]) == pytest.approx(
        100
    )
    assert (
        "Not applicable (weights re-normalized): error_ratio" in result["explanation"]
    )


def test_reweighting_changes_slow_recovery_impact() -> None:
    result = score(baseline=baseline(requests=False), requests=None, ttr=65)
    assert result["score"] == 78.1  # 100 - 0.5 * 43.75


def test_baseline_without_traffic_is_not_applicable() -> None:
    result = score(baseline=baseline(rate=0.0))
    assert component(result, "error_ratio")["status"] == "NOT_APPLICABLE"


# --- Litmus and UNKNOWN policies ---------------------------------------------------


def test_litmus_fail_with_application_non_recovery() -> None:
    result = score(
        "UNKNOWN", recovered=False, ttr=None, verdict="Fail", result=APP_UNKNOWN
    )

    litmus = component(result, "litmus_verdict")
    assert litmus["normalized"] == 0.0
    assert litmus["reason"] == "Litmus verdict Fail"
    assert result["status"] == "SCORED_NOT_RECOVERED"
    assert result["score"] == 40.0  # 0 + 25 + 20 + 10 + 0 = 55, capped
    assert result["cap_applied"] == {"cap": 40, "uncapped_score": 55.0}


def test_litmus_fail_with_recovery_is_conflicting_and_not_scored() -> None:
    result = score(
        "UNKNOWN",
        verdict="Fail",
        result={
            "status": "UNKNOWN",
            "reason_code": "LITMUS_VERDICT_FAIL",
            "cause": "conflicting_evidence",
        },
    )
    assert result["status"] == "NOT_SCORED"
    assert result["score"] is None


@pytest.mark.parametrize(
    "code",
    ["LITMUS_TIMEOUT", "LITMUS_ERROR", "PROMETHEUS_UNAVAILABLE", "INSUFFICIENT_DATA"],
)
def test_platform_unknown_is_never_scored(code: str) -> None:
    result = score(
        "UNKNOWN",
        recovered=False,
        ttr=None,
        result={"status": "UNKNOWN", "reason_code": code, "cause": "platform"},
    )

    assert result["status"] == "NOT_SCORED"
    assert result["score"] is None
    assert result["rating"] is None
    assert result["components"] == []
    assert code in result["explanation"]
    assert "says nothing reliable" in result["explanation"]


def test_application_unknown_is_scored_but_capped_and_distinguishable() -> None:
    result = score(
        "UNKNOWN", recovered=False, ttr=None, min_available=1, result=APP_UNKNOWN
    )

    assert result["status"] == "SCORED_NOT_RECOVERED"
    assert component(result, "recovery_time")["normalized"] == 0.0
    assert result["cap_applied"] == {"cap": 40, "uncapped_score": 52.5}
    assert result["score"] == 40
    assert result["rating"] == "Poor"
    assert "did NOT recover" in result["explanation"]


def test_application_unknown_below_cap_is_not_capped() -> None:
    result = score(
        "UNKNOWN", recovered=False, ttr=None, min_available=0, result=APP_UNKNOWN
    )
    assert result["score"] == 40.0  # 0 + 0 + 20 + 10 + 10
    assert result["cap_applied"] is None


@pytest.mark.parametrize(
    "state", ["CREATED", "OBSERVING", "RECOVERING", "INJECTION_FAILED"]
)
def test_unfinished_or_other_states_are_not_scored(state: str) -> None:
    assert score(state)["status"] == "NOT_SCORED"


def test_incomplete_evidence_is_not_scored() -> None:
    assert score(ttr=None)["status"] == "NOT_SCORED"
    assert (
        score_experiment("COMPLETED", baseline(), None, version="v1")["status"]
        == "NOT_SCORED"
    )


# --- invariants -------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"ttr": 65},
        {"min_available": 1, "restarts": 1},
        {"requests": 100, "errors": 3},
    ],
)
def test_contributions_add_up_and_are_deterministic(kwargs: dict[str, Any]) -> None:
    first, second = score(**kwargs), score(**kwargs)

    assert first == second
    assert sum(c["contribution"] for c in first["components"]) == pytest.approx(
        first["score"], abs=0.1
    )
    assert sum(c["weight"] for c in first["components"]) == 100
    assert 0 <= first["score"] <= 100


@pytest.mark.parametrize(
    ("ttr", "rating"),
    [
        (10, "Excellent"),
        (41.43, "Excellent"),
        (42, "Good"),
        (88, "Good"),
        (600, "Fair"),
    ],
)
def test_rating_bands(ttr: float, rating: str) -> None:
    assert score(ttr=ttr)["rating"] == rating


def test_rating_band_edges() -> None:
    assert score(ttr=41.43)["score"] == 90.0  # 65 + 35 * 0.7143: exactly Excellent
    assert score(ttr=42)["score"] == 89.8  # just below -> Good
    assert score(ttr=88)["score"] == 75.2
    assert score(ttr=600)["score"] == 65.0  # recovery zeroed -> Fair
