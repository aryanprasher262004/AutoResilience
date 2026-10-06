"""Steady-state baseline for an experiment target, captured from Prometheus.

Deliberately small: workload availability and container restarts (kube-state-metrics,
always present), server-side request/error rate when the target's pods expose the
http_requests_total{status} counter, and the client-side view when the load
generator targets this workload (loadgen_requests_total{outcome}). All queries are
evaluated at one timestamp.
"""

from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy.orm import Session

from app.db.models import Experiment
from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.domain.state_machine import (
    ExperimentState,
    InvalidTransitionError,
    can_transition,
    transition,
)
from app.integrations.prometheus_client import PrometheusError

# Fewer availability samples than this in the window is not a defensible baseline.
MIN_SAMPLES = 4


class ValueQuery(Protocol):
    def query_value(self, promql: str, at: datetime) -> float | None: ...


class MetricStatus(StrEnum):
    OK = "OK"
    # The target does not expose this metric (optional groups only).
    UNAVAILABLE = "UNAVAILABLE"
    # Prometheus failed or returned too little data.
    ERROR = "ERROR"


class BaselineStatus(StrEnum):
    CAPTURED = "CAPTURED"
    FAILED = "FAILED"


def pod_name_regex(target: ExperimentTarget) -> str:
    # Kubernetes pod naming: Deployment -> <name>-<template-hash>-<5 chars>,
    # StatefulSet -> <name>-<ordinal>. Segments contain no '-', so a workload named
    # "checkout" never matches pods of "checkout-api".
    if target.kind is WorkloadKind.DEPLOYMENT:
        return f"{target.name}-[a-z0-9]+-[a-z0-9]{{5}}"
    return f"{target.name}-[0-9]+"


def client_selector(target: ExperimentTarget) -> str:
    """Load generator series for this workload (infra/sample-app/loadgen)."""
    return f'target_namespace="{target.namespace}",target_workload="{target.name}"'


def baseline_queries(target: ExperimentTarget, window_seconds: int) -> dict[str, str]:
    ns = target.namespace
    w = f"[{window_seconds}s]"
    if target.kind is WorkloadKind.DEPLOYMENT:
        sel = f'{{namespace="{ns}",deployment="{target.name}"}}'
        desired = f"kube_deployment_spec_replicas{sel}"
        available = f"kube_deployment_status_replicas_available{sel}"
    else:
        sel = f'{{namespace="{ns}",statefulset="{target.name}"}}'
        desired = f"kube_statefulset_replicas{sel}"
        available = f"kube_statefulset_status_replicas_ready{sel}"
    pods = f'namespace="{ns}",pod=~"{pod_name_regex(target)}"'
    restarts = f"kube_pod_container_status_restarts_total{{{pods}}}"
    requests = f"http_requests_total{{{pods}}}"
    errors = f'http_requests_total{{{pods},status=~"5.."}}'
    client = f"loadgen_requests_total{{{client_selector(target)}}}"
    client_failed = (
        f'loadgen_requests_total{{{client_selector(target)},outcome!="success"}}'
    )
    client_latency = (
        f"loadgen_request_duration_seconds_bucket{{{client_selector(target)}}}"
    )
    return {
        "desired_replicas": desired,
        "available_replicas_avg": f"avg_over_time({available}{w})",
        "available_replicas_min": f"min_over_time({available}{w})",
        "availability_samples": f"count_over_time({available}{w})",
        "restarts_total": f"sum({restarts})",
        "restarts_in_window": (
            f"sum(max_over_time({restarts}{w}) - min_over_time({restarts}{w}))"
        ),
        "request_series": f"count({requests})",
        "request_rate_rps": f"sum(rate({requests}{w}))",
        "error_rate_rps": f"sum(rate({errors}{w}))",
        "client_series": f"count({client})",
        "client_rate_rps": f"sum(rate({client}{w}))",
        "client_failure_rate_rps": f"sum(rate({client_failed}{w}))",
        "client_latency_p95_seconds": (
            f"histogram_quantile(0.95, sum by (le) (rate({client_latency}{w})))"
        ),
        "client_outage_seconds": (
            f"sum(increase(loadgen_outage_seconds_total{{{client_selector(target)}}}{w}))"
        ),
        "client_outages": (
            f"sum(increase(loadgen_outages_total{{{client_selector(target)}}}{w}))"
        ),
    }


def capture_baseline(
    prometheus: ValueQuery, target: ExperimentTarget, window_seconds: int, at: datetime
) -> dict[str, Any]:
    queries = baseline_queries(target, window_seconds)

    def value(name: str) -> float | None:
        return prometheus.query_value(queries[name], at)

    groups = {
        "availability": _group(_availability, value),
        "restarts": _group(_restarts, value),
        "requests": _group(_requests, value),
        "client": _group(_client, value),
    }
    required_ok = all(
        groups[g]["status"] == MetricStatus.OK for g in ("availability", "restarts")
    )
    optional_ok = all(
        groups[g]["status"] != MetricStatus.ERROR for g in ("requests", "client")
    )
    return {
        "status": BaselineStatus.CAPTURED
        if required_ok and optional_ok
        else BaselineStatus.FAILED,
        "captured_at": at.isoformat(),
        "window_seconds": window_seconds,
        **groups,
        "failure_reasons": [
            f"{name}: {g['message']}"
            for name, g in groups.items()
            if g["status"] == MetricStatus.ERROR
        ],
    }


class _InsufficientData(Exception):
    pass


ValueFn = Callable[[str], float | None]
GroupResult = tuple[MetricStatus, str, dict[str, Any]]


def _group(build: Callable[[ValueFn], GroupResult], value: ValueFn) -> dict[str, Any]:
    try:
        status, message, values = build(value)
    except (PrometheusError, _InsufficientData) as exc:
        return {"status": MetricStatus.ERROR, "message": str(exc), "values": {}}
    return {"status": status, "message": message, "values": values}


def _round(v: float) -> float:
    return round(v, 4)


def _availability(value: ValueFn) -> GroupResult:
    samples = value("availability_samples")
    desired = value("desired_replicas")
    if samples is None or desired is None or samples < MIN_SAMPLES:
        raise _InsufficientData(
            f"Insufficient availability data: {int(samples or 0)} samples in window "
            f"(need >= {MIN_SAMPLES})"
        )
    avg = value("available_replicas_avg")
    low = value("available_replicas_min")
    if avg is None or low is None:
        raise _InsufficientData("Availability series disappeared during capture")
    ratio = _round(avg / desired) if desired > 0 else None
    return (
        MetricStatus.OK,
        (
            f"avg {avg:.2f} / {int(desired)} desired replicas available "
            f"(min {int(low)}, {int(samples)} samples)"
        ),
        {
            "desired_replicas": int(desired),
            "available_replicas_avg": _round(avg),
            "available_replicas_min": int(low),
            "availability_ratio": ratio,
            "samples": int(samples),
        },
    )


def _restarts(value: ValueFn) -> GroupResult:
    total = value("restarts_total")
    in_window = value("restarts_in_window")
    if total is None or in_window is None:
        raise _InsufficientData("No container restart series found for target pods")
    return (
        MetricStatus.OK,
        f"{int(in_window)} restarts in window ({int(total)} total)",
        {"restarts_total": int(total), "restarts_in_window": int(in_window)},
    )


def _requests(value: ValueFn) -> GroupResult:
    if value("request_series") is None:
        return (
            MetricStatus.UNAVAILABLE,
            "Target pods do not expose http_requests_total",
            {},
        )
    rate = value("request_rate_rps") or 0.0
    # No 5xx series simply means no server errors were ever recorded.
    errors = value("error_rate_rps") or 0.0
    ratio = _round(errors / rate) if rate > 0 else None
    return (
        MetricStatus.OK,
        f"{rate:.3f} req/s, {errors:.3f} 5xx/s"
        + (f" (error ratio {ratio})" if ratio is not None else " (no traffic)"),
        {
            "request_rate_rps": _round(rate),
            "error_rate_rps": _round(errors),
            "error_ratio": ratio,
        },
    )


def _client(value: ValueFn) -> GroupResult:
    if value("client_series") is None:
        return (
            MetricStatus.UNAVAILABLE,
            "No client-side load generator series for this target",
            {},
        )
    rate = value("client_rate_rps") or 0.0
    failures = value("client_failure_rate_rps") or 0.0
    ratio = _round(failures / rate) if rate > 0 else None
    p95 = value("client_latency_p95_seconds")
    # None when the load generator predates outage metrics.
    outage_seconds = value("client_outage_seconds")
    outages = value("client_outages")
    return (
        MetricStatus.OK,
        f"client {rate:.2f} req/s, {failures:.3f} failed/s"
        + (f" (failure ratio {ratio})" if ratio is not None else " (no traffic)")
        + (f", p95 {p95 * 1000:.1f} ms" if p95 is not None else ""),
        {
            "client_rate_rps": _round(rate),
            "client_failure_rate_rps": _round(failures),
            "client_failure_ratio": ratio,
            "client_latency_p95_seconds": _round(p95) if p95 is not None else None,
            "client_outage_seconds": (
                _round(outage_seconds) if outage_seconds is not None else None
            ),
            "client_outages": round(outages) if outages is not None else None,
        },
    )


def run_baseline(
    db: Session,
    experiment: Experiment,
    prometheus: ValueQuery,
    window_seconds: int,
    at: datetime,
) -> None:
    """Capture and persist a baseline; BASELINING -> INJECTING only if it succeeded.

    A failed capture is persisted and the experiment stays in BASELINING (retryable).
    Raises InvalidTransitionError (before any change) if not in BASELINING.
    """
    if not can_transition(experiment.state, ExperimentState.INJECTING):
        raise InvalidTransitionError(experiment.state, ExperimentState.INJECTING)

    baseline = capture_baseline(prometheus, experiment.target, window_seconds, at)
    experiment.baseline = baseline
    if baseline["status"] == BaselineStatus.CAPTURED:
        experiment.state = transition(experiment.state, ExperimentState.INJECTING)
    db.commit()
