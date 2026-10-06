"""Resilience Score: persisted experiment evidence -> explainable 0-100 score.

Pure and deterministic: reads only the stored baseline and observation evidence
(no cluster/Prometheus access, no LLM). Methodology: docs/scoring/.

Versions (every stored score records its version; older versions stay reproducible):
  v1  error_ratio from server-side 5xx (weight 20), availability 25.
  v2  request_failures from the client-side load generator when available
      (connection errors, timeouts and HTTP 5xx as the client saw them), falling
      back to server-side 5xx; weight 30. availability reduced to 15.
  v3  client_outage (weight 15) replaces the sampled Kubernetes availability: the
      client-observed outage duration measured by the load generator, independent of
      the scrape interval. Falls back to sampled availability (stated in the reason)
      when the client outage data is insufficient.

score = 100 * sum(weight_i * normalized_i) / sum(weight_i over applicable components)

Components whose input was not measurable for this target (e.g. no request
metrics) are NOT_APPLICABLE and excluded with weights re-normalized; this is
recorded, never treated as a failure.
"""

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

CURRENT_VERSION = "v3"


class ScoreStatus(StrEnum):
    SCORED = "SCORED"  # COMPLETED: target recovered per the recovery rule
    SCORED_NOT_RECOVERED = "SCORED_NOT_RECOVERED"  # UNKNOWN, cause=application
    NOT_SCORED = "NOT_SCORED"  # platform / conflicting evidence / not finished


class ComponentStatus(StrEnum):
    SCORED = "SCORED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


@dataclass(frozen=True)
class WeightsV1:
    recovery_time: float = 35
    availability: float = 25
    error_ratio: float = 20
    restarts: float = 10
    litmus_verdict: float = 10


@dataclass(frozen=True)
class WeightsV2:
    recovery_time: float = 35
    availability: float = 15
    request_failures: float = 30
    restarts: float = 10
    litmus_verdict: float = 10


@dataclass(frozen=True)
class Thresholds:
    # Recovery time (replacement created -> Ready): full marks up to `fast`,
    # zero at `slow`, linear in between.
    recovery_fast_seconds: float = 10
    recovery_slow_seconds: float = 120
    # Increase of the failure ratio over baseline (absolute): full marks up to
    # `tolerated`, zero at `severe`, linear in between. v1: server 5xx ratio;
    # v2: client failure ratio (or server 5xx as fallback).
    error_ratio_tolerated_increase: float = 0.001
    error_ratio_severe_increase: float = 0.05
    # Container restarts in the fault window: 1 restart halves, 2+ zero.
    restarts_zero_at: int = 2
    # A target that did not recover can never score above this.
    not_recovered_cap: float = 40


@dataclass(frozen=True)
class WeightsV3:
    recovery_time: float = 35
    client_outage: float = 15
    request_failures: float = 30
    restarts: float = 10
    litmus_verdict: float = 10


@dataclass(frozen=True)
class OutageThresholds:
    # Client-observed outage beyond baseline: full marks up to `tolerated`, zero at
    # `severe`, linear in between.
    outage_tolerated_seconds: float = 1
    outage_severe_seconds: float = 60


WEIGHTS_V1 = WeightsV1()
WEIGHTS_V3 = WeightsV3()
OUTAGE_THRESHOLDS = OutageThresholds()
WEIGHTS_V2 = WeightsV2()
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
    recovered: bool, recovery: dict[str, Any], t: Thresholds, weight: float
) -> Component:
    seconds = recovery.get("time_to_recovery_seconds")
    raw = {"recovered": recovered, "time_to_recovery_seconds": seconds}
    if not recovered:
        return Component(
            "recovery_time",
            ComponentStatus.SCORED,
            raw,
            0.0,
            weight,
            "Target did not satisfy the recovery rule within the timeout",
        )
    assert seconds is not None  # guaranteed by score_experiment
    score = _linear_down(seconds, t.recovery_fast_seconds, t.recovery_slow_seconds)
    return Component(
        "recovery_time",
        ComponentStatus.SCORED,
        raw,
        score,
        weight,
        f"Recovered in {seconds:g}s (replacement created -> Ready, 1s resolution; "
        f"full marks <= {t.recovery_fast_seconds:g}s, zero >= {t.recovery_slow_seconds:g}s)",
    )


def availability_component(
    desired: int, impact: dict[str, Any], weight: float
) -> Component:
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
            weight,
            "No availability samples during the fault window",
        )
    score = round(max(0.0, min(1.0, minimum / desired)), 4)
    lost = desired - minimum
    return Component(
        "availability",
        ComponentStatus.SCORED,
        raw,
        score,
        weight,
        (
            f"Lowest observed availability {minimum}/{desired} replicas"
            + (f" ({lost} lost)" if lost > 0 else " (no dip observed)")
            + "; sampled every scrape interval, so dips shorter than that may be missed"
        ),
    )


def error_ratio_component(
    baseline_requests: dict[str, Any],
    impact: dict[str, Any],
    t: Thresholds,
    weight: float,
    name: str = "error_ratio",
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
            name,
            ComponentStatus.NOT_APPLICABLE,
            raw,
            None,
            weight,
            "Target exposes no request metrics (or had no baseline traffic); "
            "excluded and weights re-normalized",
        )
    if not requests:
        return Component(
            name,
            ComponentStatus.SCORED,
            raw,
            0.0,
            weight,
            "Baseline had traffic but no requests were recorded during the fault window",
        )
    ratio = round((errors or 0.0) / requests, 4)
    increase = round(max(0.0, ratio - (baseline_ratio or 0.0)), 4)
    raw.update({"fault_error_ratio": ratio, "increase": increase})
    score = _linear_down(
        increase, t.error_ratio_tolerated_increase, t.error_ratio_severe_increase
    )
    return Component(
        name,
        ComponentStatus.SCORED,
        raw,
        score,
        weight,
        f"Server-side 5xx ratio {ratio} vs baseline {baseline_ratio or 0} "
        f"(+{increase}; full marks <= +{t.error_ratio_tolerated_increase:g}, "
        f"zero >= +{t.error_ratio_severe_increase:g})",
    )


def restarts_component(
    baseline_restarts: dict[str, Any],
    impact: dict[str, Any],
    t: Thresholds,
    weight: float,
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
            weight,
            "No restart data for the fault window",
        )
    score = round(max(0.0, 1 - restarts / t.restarts_zero_at), 4)
    return Component(
        "restarts",
        ComponentStatus.SCORED,
        raw,
        score,
        weight,
        f"{restarts} container restart(s) during the fault window "
        f"(zero marks at >= {t.restarts_zero_at})",
    )


def litmus_component(litmus: dict[str, Any], weight: float) -> Component:
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
        weight,
        "Litmus verdict Pass" if passed else f"Litmus verdict {verdict}",
    )


def request_failures_component(
    baseline: dict[str, Any], impact: dict[str, Any], t: Thresholds, weight: float
) -> Component:
    """v2: what the client experienced; server-side 5xx only as a fallback."""
    name = "request_failures"
    base = baseline.get("client") or {}
    base_values = base.get("values") or {}
    client = impact.get("client") or {}
    fallback_note = ""
    if base.get("status") == "OK" and base_values.get("client_rate_rps"):
        if client.get("status") == "OK" and client.get("requests"):
            return _client_failures(name, base_values, client, t, weight)
        fallback_note = (
            "client load generator recorded no requests during the fault window "
            "(measurement gap, not a target failure)"
        )
    else:
        fallback_note = "no client-side baseline for this target"

    server = error_ratio_component(
        baseline.get("requests") or {}, impact, t, weight, name
    )
    raw = {
        "source": "server" if server.status is ComponentStatus.SCORED else None,
        **server.raw,
    }
    return Component(
        name,
        server.status,
        raw,
        server.normalized,
        weight,
        f"{server.reason} [server-side fallback: {fallback_note}]",
    )


def _client_failures(
    name: str,
    base_values: dict[str, Any],
    client: dict[str, Any],
    t: Thresholds,
    weight: float,
) -> Component:
    baseline_ratio = base_values.get("client_failure_ratio") or 0.0
    ratio = client.get("failure_ratio") or 0.0
    increase = round(max(0.0, ratio - baseline_ratio), 4)
    raw = {
        "source": "client",
        "requests": client.get("requests"),
        "failed": client.get("failed"),
        "http_error": client.get("http_error"),
        "connection_error": client.get("connection_error"),
        "timeout": client.get("timeout"),
        "fault_failure_ratio": ratio,
        "baseline_failure_ratio": baseline_ratio,
        "increase": increase,
        "failure_intervals": len(client.get("failure_intervals") or []),
        "counted_from": client.get("counted_from"),
        "counted_to": client.get("counted_to"),
    }
    score = _linear_down(
        increase, t.error_ratio_tolerated_increase, t.error_ratio_severe_increase
    )
    kinds = ", ".join(
        f"{client.get(o)} {o.replace('_', ' ')}"
        for o in ("connection_error", "timeout", "http_error")
        if client.get(o)
    )
    reason = (
        f"Client saw {client.get('failed')}/{client.get('requests')} requests fail"
        + (f" ({kinds})" if kinds else "")
        + f": ratio {ratio} vs baseline {baseline_ratio} (+{increase}; full marks <= "
        f"+{t.error_ratio_tolerated_increase:g}, zero >= +{t.error_ratio_severe_increase:g})"
    )
    if not client.get("starts_before_fault"):
        reason += (
            "; counting started after the fault began, early failures may be missed"
        )
    return Component(name, ComponentStatus.SCORED, raw, score, weight, reason)


def client_outage_component(
    baseline: dict[str, Any],
    impact: dict[str, Any],
    desired: int,
    o: OutageThresholds,
    weight: float,
) -> Component:
    """v3: measured client-observed outage duration (sampled availability as fallback)."""
    name = "client_outage"
    client = impact.get("client") or {}
    outage = client.get("outage") or {}
    insufficient = None
    if client.get("status") != "OK" or not outage:
        insufficient = "no client outage measurement for this target"
    elif not client.get("requests"):
        insufficient = "the load generator recorded no requests in the window"
    elif outage.get("status") != "OK":
        insufficient = outage.get("reason") or "insufficient client outage data"
    if insufficient:
        sampled = availability_component(desired, impact, weight)
        return Component(
            name,
            sampled.status,
            {
                "source": "kubernetes_sampled",
                "pattern": "INSUFFICIENT_DATA",
                **sampled.raw,
            },
            sampled.normalized,
            weight,
            f"{sampled.reason} [fallback: {insufficient}]",
        )

    window = impact.get("window_seconds") or 0
    base = (baseline.get("client") or {}).get("values") or {}
    base_seconds = base.get("client_outage_seconds")
    base_window = baseline.get("window_seconds") or 0
    expected = (
        round(base_seconds / base_window * window, 3)
        if base_seconds and base_window
        else 0.0
    )
    seconds = outage["outage_seconds"]
    excess = round(max(0.0, seconds - expected), 3)
    score = _linear_down(excess, o.outage_tolerated_seconds, o.outage_severe_seconds)
    windows = outage.get("outage_windows") or []
    raw = {
        "source": "client",
        "pattern": outage["pattern"],
        "outage_seconds": seconds,
        "outages": outage.get("outages"),
        "baseline_expected_seconds": expected,
        "excess_seconds": excess,
        "outage_windows": windows,
        "window_seconds": window,
    }
    timing = ""
    if outage["pattern"] == "CONTINUOUS" and windows and windows[-1].get("end"):
        timing = f" ({windows[-1]['start'][11:23]} -> {windows[-1]['end'][11:23]})"
    reason = (
        f"{outage['reason']}{timing}"
        + (f"; baseline expects {expected:g}s" if expected else "")
        + f"; excess {excess:g}s (full marks <= {o.outage_tolerated_seconds:g}s, "
        f"zero >= {o.outage_severe_seconds:g}s)"
    )
    return Component(name, ComponentStatus.SCORED, raw, score, weight, reason)


# --- overall ------------------------------------------------------------------


def _components(
    version: str,
    recovered: bool,
    baseline: dict[str, Any],
    observation: dict[str, Any],
    t: Thresholds,
) -> tuple[list[Component], dict[str, float]]:
    desired = int(baseline["availability"]["values"]["desired_replicas"])
    impact, recovery = observation["impact"], observation["recovery"]
    litmus = observation.get("litmus") or {}
    restarts_baseline = baseline.get("restarts") or {}
    if version == "v1":
        w1 = WEIGHTS_V1
        return [
            recovery_component(recovered, recovery, t, w1.recovery_time),
            availability_component(desired, impact, w1.availability),
            error_ratio_component(
                baseline.get("requests") or {}, impact, t, w1.error_ratio
            ),
            restarts_component(restarts_baseline, impact, t, w1.restarts),
            litmus_component(litmus, w1.litmus_verdict),
        ], asdict(w1)
    if version == "v3":
        w3 = WEIGHTS_V3
        return [
            recovery_component(recovered, recovery, t, w3.recovery_time),
            client_outage_component(
                baseline, impact, desired, OUTAGE_THRESHOLDS, w3.client_outage
            ),
            request_failures_component(baseline, impact, t, w3.request_failures),
            restarts_component(restarts_baseline, impact, t, w3.restarts),
            litmus_component(litmus, w3.litmus_verdict),
        ], asdict(w3)
    w2 = WEIGHTS_V2
    return [
        recovery_component(recovered, recovery, t, w2.recovery_time),
        availability_component(desired, impact, w2.availability),
        request_failures_component(baseline, impact, t, w2.request_failures),
        restarts_component(restarts_baseline, impact, t, w2.restarts),
        litmus_component(litmus, w2.litmus_verdict),
    ], asdict(w2)


SUPPORTED_VERSIONS = ("v1", "v2", "v3")


def _fault_inputs(chaos: dict[str, Any] | None) -> dict[str, Any]:
    """Which fault produced the evidence (context only; never changes the number)."""
    chaos = chaos or {}
    return {
        "type": chaos.get("experiment"),
        # Records from before modes existed all ran graceful deletion (FORCE=false).
        "pod_delete_mode": chaos.get("pod_delete_mode") or "GRACEFUL",
        "target_pods": chaos.get("target_pods"),
    }


def _not_scored(
    version: str,
    reason: str,
    state: str,
    result: dict[str, Any],
    chaos: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "version": version,
        "status": ScoreStatus.NOT_SCORED,
        "score": None,
        "rating": None,
        "explanation": reason,
        "components": [],
        "cap_applied": None,
        "inputs": {"state": state, "result": result, "fault": _fault_inputs(chaos)},
    }


def score_experiment(
    state: str,
    baseline: dict[str, Any] | None,
    observation: dict[str, Any] | None,
    thresholds: Thresholds = THRESHOLDS,
    version: str = CURRENT_VERSION,
    chaos: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(f"Unknown scoring version {version!r}")
    result = (observation or {}).get("result") or {}
    if state not in ("COMPLETED", "UNKNOWN") or not baseline or not observation:
        return _not_scored(
            version,
            f"Experiment is {state}; only finished runs are scored",
            state,
            result,
            chaos,
        )
    if state == "UNKNOWN" and result.get("cause") != "application":
        return _not_scored(
            version,
            f"Not scored: outcome undetermined ({result.get('reason_code')}, cause "
            f"{result.get('cause')}). Platform or conflicting evidence says nothing "
            "reliable about the target's resilience.",
            state,
            result,
            chaos,
        )
    recovered = state == "COMPLETED"
    recovery = observation.get("recovery") or {}
    if (
        not observation.get("impact")
        or not recovery
        or (recovered and recovery.get("time_to_recovery_seconds") is None)
    ):
        return _not_scored(
            version, "Observation evidence incomplete", state, result, chaos
        )

    components, weights = _components(
        version, recovered, baseline, observation, thresholds
    )
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
    fault = _fault_inputs(chaos)
    explanation = f"Resilience Score {score:g}/100 ({rating})"
    if fault["type"]:
        explanation += f" for {fault['type']} ({fault['pod_delete_mode']})"
    explanation += "."
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
        "version": version,
        "status": ScoreStatus.SCORED if recovered else ScoreStatus.SCORED_NOT_RECOVERED,
        "score": score,
        "rating": rating,
        "explanation": explanation,
        "components": breakdown,
        "cap_applied": cap,
        "weights": weights,
        "thresholds": (
            {**asdict(thresholds), **asdict(OUTAGE_THRESHOLDS)}
            if version == "v3"
            else asdict(thresholds)
        ),
        "inputs": {"state": state, "result": result, "fault": fault},
    }
