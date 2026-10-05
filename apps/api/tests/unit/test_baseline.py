import re
from datetime import UTC, datetime
from typing import Any

import pytest

from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.integrations.prometheus_client import PrometheusError
from app.services.orchestration.baseline import (
    MIN_SAMPLES,
    baseline_queries,
    capture_baseline,
    pod_name_regex,
)
from tests.conftest import CHECKOUT, WINDOW_SECONDS, FakePrometheus

AT = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)
REDIS = ExperimentTarget("shop", WorkloadKind.STATEFULSET, "cart-redis")


def capture(prometheus: FakePrometheus) -> dict[str, Any]:
    return capture_baseline(prometheus, CHECKOUT, WINDOW_SECONDS, AT)


# --- pod scoping ------------------------------------------------------------


@pytest.mark.parametrize(
    ("target", "pod", "matches"),
    [
        (CHECKOUT, "checkout-5bd4c587b4-pjv5m", True),
        (CHECKOUT, "checkout-api-5bd4c587b4-pjv5m", False),
        (CHECKOUT, "checkout-0", False),
        (CHECKOUT, "my-checkout-5bd4c587b4-pjv5m", False),
        (REDIS, "cart-redis-0", True),
        (REDIS, "cart-redis-12", True),
        (REDIS, "cart-redis-cache-0", False),
    ],
)
def test_pod_name_regex(target: ExperimentTarget, pod: str, matches: bool) -> None:
    # Prometheus anchors =~ regexes, i.e. fullmatch semantics.
    assert (re.fullmatch(pod_name_regex(target), pod) is not None) is matches


def test_queries_use_kind_specific_kube_state_metrics() -> None:
    deploy = baseline_queries(CHECKOUT, 300)
    sts = baseline_queries(REDIS, 120)

    assert deploy["desired_replicas"] == (
        'kube_deployment_spec_replicas{namespace="shop",deployment="checkout"}'
    )
    assert "kube_statefulset_status_replicas_ready" in sts["available_replicas_avg"]
    assert "[120s]" in sts["available_replicas_avg"]
    assert 'status=~"5.."' in deploy["error_rate_rps"]


# --- capture ---------------------------------------------------------------


def test_healthy_capture() -> None:
    prometheus = FakePrometheus()

    baseline = capture(prometheus)

    assert baseline["status"] == "CAPTURED"
    assert baseline["failure_reasons"] == []
    assert baseline["captured_at"] == AT.isoformat()
    assert baseline["window_seconds"] == 300
    assert baseline["availability"]["values"] == {
        "desired_replicas": 2,
        "available_replicas_avg": 2.0,
        "available_replicas_min": 2,
        "availability_ratio": 1.0,
        "samples": 20,
    }
    assert baseline["restarts"]["values"] == {
        "restarts_total": 1,
        "restarts_in_window": 0,
    }
    assert baseline["requests"]["values"] == {
        "request_rate_rps": 1.5,
        "error_rate_rps": 0.0,
        "error_ratio": 0.0,
    }
    # Every query is evaluated at the same instant.
    assert {at for _, at in prometheus.queries} == {AT}


def test_capture_is_deterministic() -> None:
    assert capture(FakePrometheus()) == capture(FakePrometheus())


def test_error_ratio_from_5xx_rate() -> None:
    prometheus = FakePrometheus()
    prometheus.values["request_rate_rps"] = 2.0
    prometheus.values["error_rate_rps"] = 0.5

    requests = capture(prometheus)["requests"]

    assert requests["values"]["error_ratio"] == 0.25
    assert requests["message"] == "2.000 req/s, 0.500 5xx/s (error ratio 0.25)"


def test_target_without_request_metrics_is_unavailable_not_failed() -> None:
    prometheus = FakePrometheus()
    prometheus.values["request_series"] = None

    baseline = capture(prometheus)

    assert baseline["status"] == "CAPTURED"
    assert baseline["requests"]["status"] == "UNAVAILABLE"
    assert baseline["requests"]["values"] == {}


def test_no_traffic_has_no_error_ratio() -> None:
    prometheus = FakePrometheus()
    prometheus.values["request_rate_rps"] = 0.0

    requests = capture(prometheus)["requests"]

    assert requests["status"] == "OK"
    assert requests["values"]["error_ratio"] is None


@pytest.mark.parametrize("samples", [None, 0, MIN_SAMPLES - 1])
def test_insufficient_availability_data_fails(samples: float | None) -> None:
    prometheus = FakePrometheus()
    prometheus.values["availability_samples"] = samples

    baseline = capture(prometheus)

    assert baseline["status"] == "FAILED"
    assert baseline["availability"]["status"] == "ERROR"
    expected = (
        f"availability: Insufficient availability data: {int(samples or 0)} samples "
        f"in window (need >= {MIN_SAMPLES})"
    )
    assert baseline["failure_reasons"] == [expected]


def test_missing_restart_series_fails() -> None:
    prometheus = FakePrometheus()
    prometheus.values["restarts_total"] = None

    baseline = capture(prometheus)

    assert baseline["status"] == "FAILED"
    assert baseline["restarts"]["status"] == "ERROR"


def test_prometheus_error_on_optional_group_still_fails() -> None:
    prometheus = FakePrometheus()
    prometheus.values["request_series"] = PrometheusError("Prometheus unreachable: x")

    baseline = capture(prometheus)

    assert baseline["status"] == "FAILED"
    assert baseline["requests"]["status"] == "ERROR"
    assert baseline["availability"]["status"] == "OK"


def test_prometheus_down_fails_every_group() -> None:
    prometheus = FakePrometheus()
    prometheus.error = "Prometheus unreachable: connection refused"

    baseline = capture(prometheus)

    assert baseline["status"] == "FAILED"
    assert len(baseline["failure_reasons"]) == 3
    assert all("connection refused" in r for r in baseline["failure_reasons"])
