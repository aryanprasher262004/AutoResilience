"""Resilience Score v3: client-observed outage duration replaces sampled availability.

Weights 35/15/30/10/10; outage excess <= 1s full marks, >= 60s zero.
See docs/scoring/resilience-score-v3.md.
"""

from typing import Any

import pytest

from app.services.scoring.resilience_score import CURRENT_VERSION, score_experiment
from tests.unit.test_resilience_score import APP_UNKNOWN, observation
from tests.unit.test_resilience_score_v2 import client_baseline, client_impact


def outage(
    seconds: float = 0.0,
    outages: int = 0,
    pattern: str | None = None,
    status: str = "OK",
    reason: str | None = None,
) -> dict[str, Any]:
    pattern = pattern or (
        "NONE" if not outages else "CONTINUOUS" if outages == 1 else "INTERMITTENT"
    )
    windows = (
        [
            {
                "start": "2026-10-06T10:59:01.234000+00:00",
                "end": "2026-10-06T10:59:10.634000+00:00",
                "seconds": seconds,
            }
        ]
        if pattern == "CONTINUOUS"
        else []
    )
    return {
        "status": status,
        "pattern": pattern,
        "reason": reason
        or {
            "NONE": "No client-observed outage",
            "CONTINUOUS": f"Continuous client outage of {seconds:g}s",
            "INTERMITTENT": f"Intermittent client failures: {outages} outages totalling {seconds:g}s",
        }.get(pattern, "insufficient"),
        "outage_seconds": seconds,
        "outages": outages,
        "outage_windows": windows,
    }


def v3(
    state: str = "COMPLETED",
    *,
    out: dict[str, Any] | None = None,
    b: dict[str, Any] | None = None,
    client: dict[str, Any] | None = None,
    window: int = 75,
    **kwargs: Any,
) -> dict[str, Any]:
    obs = observation(**kwargs)
    c = client if client is not None else client_impact()
    if out is not None:
        c["outage"] = out
    obs["impact"]["client"] = c
    obs["impact"]["window_seconds"] = window
    base = b or client_baseline()
    base.setdefault("window_seconds", 300)
    return score_experiment(state, base, obs, version="v3")


def comp(result: dict[str, Any]) -> dict[str, Any]:
    return next(c for c in result["components"] if c["name"] == "client_outage")


def test_v3_is_current_with_documented_weights() -> None:
    assert CURRENT_VERSION == "v3"
    result = v3(out=outage())
    assert result["version"] == "v3"
    assert result["weights"] == {
        "recovery_time": 35,
        "client_outage": 15,
        "request_failures": 30,
        "restarts": 10,
        "litmus_verdict": 10,
    }
    assert result["thresholds"]["outage_tolerated_seconds"] == 1
    assert result["thresholds"]["outage_severe_seconds"] == 60
    assert "availability" not in {c["name"] for c in result["components"]}


def test_no_outage_full_marks() -> None:
    result = v3(out=outage())
    assert comp(result)["normalized"] == 1.0
    assert comp(result)["raw"]["pattern"] == "NONE"
    assert result["score"] == 100.0


def test_continuous_outage_scored_by_duration() -> None:
    # 9.4s: 1 - (9.4 - 1) / (60 - 1) = 0.8576
    c = comp(v3(out=outage(9.4, 1)))
    assert c["normalized"] == 0.8576
    assert c["raw"]["source"] == "client"
    assert c["raw"]["pattern"] == "CONTINUOUS"
    assert c["reason"].startswith(
        "Continuous client outage of 9.4s (10:59:01.234 -> 10:59:10.634)"
    )


def test_intermittent_failures_explained() -> None:
    c = comp(v3(out=outage(2.0, 4)))
    assert c["raw"]["pattern"] == "INTERMITTENT"
    assert c["reason"].startswith(
        "Intermittent client failures: 4 outages totalling 2s"
    )
    assert c["normalized"] == 0.9831  # 1 - 1/59


@pytest.mark.parametrize(
    ("seconds", "normalized"),
    [(0, 1.0), (1.0, 1.0), (1.59, 0.99), (30.5, 0.5), (60, 0.0), (300, 0.0)],
)
def test_outage_boundaries(seconds: float, normalized: float) -> None:
    assert (
        comp(v3(out=outage(seconds, 1 if seconds else 0)))["normalized"] == normalized
    )


def test_baseline_outage_rate_is_subtracted() -> None:
    # Baseline: 4s of outage per 300s; a 75s window expects 1s; measured 2s -> excess 1s.
    b = client_baseline()
    b["client"]["values"]["client_outage_seconds"] = 4.0
    c = comp(v3(out=outage(2.0, 1), b=b))
    assert c["raw"]["baseline_expected_seconds"] == 1.0
    assert c["raw"]["excess_seconds"] == 1.0
    assert c["normalized"] == 1.0
    assert "baseline expects 1s" in c["reason"]


@pytest.mark.parametrize(
    ("out", "client", "why"),
    [
        (
            outage(
                status="INSUFFICIENT_DATA",
                pattern="INSUFFICIENT_DATA",
                reason="Counter reset in the window",
            ),
            None,
            "Counter reset in the window",
        ),
        (None, {"status": "UNAVAILABLE"}, "no client outage measurement"),
        (
            outage(),
            client_impact(requests=0),
            "the load generator recorded no requests",
        ),
    ],
)
def test_insufficient_client_data_falls_back_to_sampled_availability(
    out: dict[str, Any] | None, client: dict[str, Any] | None, why: str
) -> None:
    result = v3(out=out, client=client, min_available=1)

    c = comp(result)
    assert c["raw"]["source"] == "kubernetes_sampled"
    assert c["raw"]["pattern"] == "INSUFFICIENT_DATA"
    assert c["normalized"] == 0.5  # sampled 1/2
    assert f"[fallback: {why}" in c["reason"]


def test_less_dependent_on_scrape_timing_than_v2() -> None:
    """Same real 9.4s outage; only whether a 15s scrape caught the dip differs."""
    caught = v3(out=outage(9.4, 1), min_available=0)
    missed = v3(out=outage(9.4, 1), min_available=2)
    assert caught["score"] == missed["score"]

    def v2_score(min_available: int) -> float:
        obs = observation(min_available=min_available)
        obs["impact"]["client"] = {**client_impact(), "outage": outage(9.4, 1)}
        return score_experiment("COMPLETED", client_baseline(), obs, version="v2")[
            "score"
        ]

    assert v2_score(0) != v2_score(2)  # v2 swings by the full availability weight


def test_platform_unknown_not_scored_in_v3() -> None:
    result = v3(
        "UNKNOWN",
        out=outage(30, 1),
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


def test_application_unknown_capped_in_v3() -> None:
    result = v3(
        "UNKNOWN", out=outage(120, 1), recovered=False, ttr=None, result=APP_UNKNOWN
    )
    assert result["status"] == "SCORED_NOT_RECOVERED"
    assert result["score"] <= 40


def test_deterministic() -> None:
    assert v3(out=outage(9.4, 1)) == v3(out=outage(9.4, 1))
