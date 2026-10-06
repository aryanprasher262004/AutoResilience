"""Resilience Score v1: persisted experiment evidence -> explainable 0-100 score.

Pure and deterministic: reads only the stored baseline and observation evidence
(no cluster/Prometheus access, no LLM). Methodology: docs/scoring/resilience-score-v1.md.

score = 100 * sum(weight_i * normalized_i) / sum(weight_i over applicable components)

Components whose input was not measurable for this target (e.g. no request
metrics) are NOT_APPLICABLE and excluded with weights re-normalized; this is
recorded, never treated as a failure.
"""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

SCORING_VERSION = "v1"


class ScoreStatus(StrEnum):
    SCORED = "SCORED"  # COMPLETED: target recovered per the recovery rule
    SCORED_NOT_RECOVERED = "SCORED_NOT_RECOVERED"  # UNKNOWN, cause=application
    NOT_SCORED = "NOT_SCORED"  # platform / conflicting evidence / not finished


class ComponentStatus(StrEnum):
    SCORED = "SCORED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class Weights:
    recovery_time: float = 35
    availability: float = 25
    error_ratio: float = 20
    restarts: float = 10
    litmus_verdict: float = 10


@dataclass(frozen=True)
class Thresholds:
    # Recovery time (replacement created -> Ready): full marks up to `fast`,
    # zero at `slow`, linear in between.
    recovery_fast_seconds: float = 10
    recovery_slow_seconds: float = 120
    # Increase of the 5xx ratio over baseline (absolute): full marks up to
    # `tolerated`, zero at `severe`, linear in between.
    error_ratio_tolerated_increase: float = 0.001
    error_ratio_severe_increase: float = 0.05
    # Container restarts in the fault window: 1 restart halves, 2+ zero.
    restarts_zero_at: int = 2
    # A target that did not recover can never score above this.
    not_recovered_cap: float = 40


WEIGHTS = Weights()
THRESHOLDS = Thresholds()
RATING_BANDS = ((90, "Excellent"), (75, "Good"), (50, "Fair"), (0, "Poor"))


@dataclass(frozen=True)
class Component:
    name: str
    status: ComponentStatus
    raw: dict[str, Any]
    normalized: float | None
    weight: float
    reason: str


def _linear_down(value: float, full_at: float, zero_at: float) -> float:
    """1.0 at/below full_at, 0.0 at/above zero_at, linear in between."""
    if value <= full_at:
        return 1.0
    if value >= zero_at:
        return 0.0
    return round(1 - (value - full_at) / (zero_at - full_at), 4)


# --- components -------------------------------------------------------------


def recovery_component(
    recovered: bool, recovery: dict[str, Any], t: Thresholds
) -> Component:
    seconds = recovery.get("time_to_recovery_seconds")
    raw = {"recovered": recovered, "time_to_recovery_seconds": seconds}
    if not recovered:
        return Component(
            "recovery_time",
            ComponentStatus.SCORED,
            raw,
            0.0,
            WEIGHTS.recovery_time,
            "Target did not satisfy the recovery rule within the timeout",
        )
    assert seconds is not None  # guaranteed by score_experiment
    score = _linear_down(seconds, t.recovery_fast_seconds, t.recovery_slow_seconds)
    return Component(
        "recovery_time",
        ComponentStatus.SCORED,
        raw,
        score,
        WEIGHTS.recovery_time,
        f"Recovered in {seconds:g}s (replacement created -> Ready, 1s resolution; "
        f"full marks <= {t.recovery_fast_seconds:g}s, zero >= {t.recovery_slow_seconds:g}s)",
    )


def availability_component(desired: int, impact: dict[str, Any]) -> Component:
    minimum = impact.get("min_available_replicas")
    samples = impact.get("availability_samples")
    raw = {
        "baseline_desired_replicas": desired,
        "min_available_replicas": minimum,
        "availability_samples": samples,
    }
    if minimum is None or desired <= 0:
        return Component(
            "availability",
            ComponentStatus.NOT_APPLICABLE,
            raw,
            None,
            WEIGHTS.availability,
            "No availability samples during the fault window",
        )
    score = round(max(0.0, min(1.0, minimum / desired)), 4)
    lost = desired - minimum
    return Component(
        "availability",
        ComponentStatus.SCORED,
        raw,
        score,
        WEIGHTS.availability,
        (
            f"Lowest observed availability {minimum}/{desired} replicas"
            + (f" ({lost} lost)" if lost > 0 else " (no dip observed)")
            + "; sampled every scrape interval, so dips shorter than that may be missed"
        ),
    )


def error_ratio_component(
    baseline_requests: dict[str, Any], impact: dict[str, Any], t: Thresholds
) -> Component:
    values = baseline_requests.get("values") or {}
    baseline_ratio = values.get("error_ratio")
    requests = impact.get("requests_in_window")
    errors = impact.get("errors_in_window")
    raw: dict[str, Any] = {
        "baseline_error_ratio": baseline_ratio,
        "requests_in_window": requests,
        "errors_in_window": errors,
    }
    if baseline_requests.get("status") != "OK" or not values.get("request_rate_rps"):
        return Component(
            "error_ratio",
            ComponentStatus.NOT_APPLICABLE,
            raw,
            None,
            WEIGHTS.error_ratio,
            "Target exposes no request metrics (or had no baseline traffic); "
            "excluded and weights re-normalized",
        )
    if not requests:
        return Component(
            "error_ratio",
            ComponentStatus.SCORED,
            raw,
            0.0,
            WEIGHTS.error_ratio,
            "Baseline had traffic but no requests were recorded during the fault window",
        )
    ratio = round((errors or 0.0) / requests, 4)
    increase = round(max(0.0, ratio - (baseline_ratio or 0.0)), 4)
    raw.update({"fault_error_ratio": ratio, "increase": increase})
    score = _linear_down(
        increase, t.error_ratio_tolerated_increase, t.error_ratio_severe_increase
    )
    return Component(
        "error_ratio",
        ComponentStatus.SCORED,
        raw,
        score,
        WEIGHTS.error_ratio,
        f"Server-side 5xx ratio {ratio} vs baseline {baseline_ratio or 0} "
        f"(+{increase}; full marks <= +{t.error_ratio_tolerated_increase:g}, "
        f"zero >= +{t.error_ratio_severe_increase:g})",
    )


def restarts_component(
    baseline_restarts: dict[str, Any], impact: dict[str, Any], t: Thresholds
) -> Component:
    restarts = impact.get("restarts_in_window")
    raw = {
        "restarts_in_window": restarts,
        "baseline_restarts_in_window": (baseline_restarts.get("values") or {}).get(
            "restarts_in_window"
        ),
    }
    if restarts is None:
        return Component(
            "restarts",
            ComponentStatus.NOT_APPLICABLE,
            raw,
            None,
            WEIGHTS.restarts,
            "No restart data for the fault window",
        )
    score = round(max(0.0, 1 - restarts / t.restarts_zero_at), 4)
    return Component(
        "restarts",
        ComponentStatus.SCORED,
        raw,
        score,
        WEIGHTS.restarts,
        f"{restarts} container restart(s) during the fault window "
        f"(zero marks at >= {t.restarts_zero_at})",
    )


def litmus_component(litmus: dict[str, Any]) -> Component:
    verdict = litmus.get("verdict")
    passed = verdict == "Pass"
    return Component(
        "litmus_verdict",
        ComponentStatus.SCORED,
        {
            "verdict": verdict,
            "fail_step": (litmus.get("chaos_result") or {}).get("fail_step"),
        },
        1.0 if passed else 0.0,
        WEIGHTS.litmus_verdict,
        "Litmus verdict Pass" if passed else f"Litmus verdict {verdict}",
    )


# --- overall ------------------------------------------------------------------


def _not_scored(reason: str, state: str, result: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": SCORING_VERSION,
        "status": ScoreStatus.NOT_SCORED,
        "score": None,
        "rating": None,
        "explanation": reason,
        "components": [],
        "cap_applied": None,
        "inputs": {"state": state, "result": result},
    }


def score_experiment(
    state: str,
    baseline: dict[str, Any] | None,
    observation: dict[str, Any] | None,
    thresholds: Thresholds = THRESHOLDS,
) -> dict[str, Any]:
    result = (observation or {}).get("result") or {}
    if state not in ("COMPLETED", "UNKNOWN") or not baseline or not observation:
        return _not_scored(
            f"Experiment is {state}; only finished runs are scored", state, result
        )
    if state == "UNKNOWN" and result.get("cause") != "application":
        return _not_scored(
            f"Not scored: outcome undetermined ({result.get('reason_code')}, cause "
            f"{result.get('cause')}). Platform or conflicting evidence says nothing "
            "reliable about the target's resilience.",
            state,
            result,
        )
    recovered = state == "COMPLETED"
    recovery = observation.get("recovery") or {}
    if (
        not observation.get("impact")
        or not recovery
        or (recovered and recovery.get("time_to_recovery_seconds") is None)
    ):
        return _not_scored("Observation evidence incomplete", state, result)

    desired = int(baseline["availability"]["values"]["desired_replicas"])
    components = [
        recovery_component(recovered, observation["recovery"], thresholds),
        availability_component(desired, observation["impact"]),
        error_ratio_component(
            baseline.get("requests") or {}, observation["impact"], thresholds
        ),
        restarts_component(
            baseline.get("restarts") or {}, observation["impact"], thresholds
        ),
        litmus_component(observation.get("litmus") or {}),
    ]
    applicable = [c for c in components if c.status is ComponentStatus.SCORED]
    total_weight = sum(c.weight for c in applicable)

    breakdown = []
    raw_score = 0.0
    for c in components:
        effective = (
            c.weight / total_weight * 100 if c.status is ComponentStatus.SCORED else 0
        )
        contribution = (c.normalized or 0.0) * effective
        raw_score += contribution
        breakdown.append(
            {
                **asdict(c),
                "effective_weight": round(effective, 2),
                "contribution": round(contribution, 2),
            }
        )
    score = round(raw_score, 1)

    cap = None
    if not recovered and score > thresholds.not_recovered_cap:
        cap = {"cap": thresholds.not_recovered_cap, "uncapped_score": score}
        score = thresholds.not_recovered_cap
    rating = next(label for floor, label in RATING_BANDS if score >= floor)

    weakest = sorted(
        (
            b
            for b in breakdown
            if b["status"] == ComponentStatus.SCORED and b["normalized"] < 1
        ),
        key=lambda b: b["contribution"] - b["effective_weight"],
    )
    explanation = f"Resilience Score {score:g}/100 ({rating})."
    if not recovered:
        explanation += (
            f" Target did NOT recover ({result.get('reason_code')}); score capped at "
            f"{thresholds.not_recovered_cap:g}."
        )
    if weakest:
        explanation += " Lost points: " + "; ".join(
            f"{b['name']} -{b['effective_weight'] - b['contribution']:.1f} ({b['reason']})"
            for b in weakest
        )
    else:
        explanation += " Full marks on every applicable component."
    excluded = [
        b["name"] for b in breakdown if b["status"] == ComponentStatus.NOT_APPLICABLE
    ]
    if excluded:
        explanation += (
            f" Not applicable (weights re-normalized): {', '.join(excluded)}."
        )

    return {
        "version": SCORING_VERSION,
        "status": ScoreStatus.SCORED if recovered else ScoreStatus.SCORED_NOT_RECOVERED,
        "score": score,
        "rating": rating,
        "explanation": explanation,
        "components": breakdown,
        "cap_applied": cap,
        "weights": asdict(WEIGHTS),
        "thresholds": asdict(thresholds),
        "inputs": {"state": state, "result": result},
    }
