"""Recovery rule for the RECOVERING phase (pure; no I/O).

A target counts as recovered only when all of these hold:
  1. Replacement: at least `affected_replicas` pods of the workload were created
     after the fault started and became Ready. The recovery instant is the ready
     time of the N-th replacement (Kubernetes object timestamps from
     kube-state-metrics, 1s resolution, not limited by the scrape interval).
  2. Sustained: at least `stable_samples` consecutive raw availability samples at or
     above the baseline's desired replicas, all at/after the recovery instant, with
     no gap between samples larger than `max_gap_seconds`.
  3. Requests (only when the baseline had request metrics with traffic): requests
     keep flowing during that stable window and its 5xx ratio is at most
     baseline ratio + `error_ratio_tolerance`. Checked by the caller via
     `error_check`, because it needs a Prometheus query over the window.
"""

from dataclasses import dataclass, field
from itertools import pairwise

from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.services.orchestration.baseline import pod_name_regex


@dataclass(frozen=True)
class RecoveryRule:
    stable_samples: int
    max_gap_seconds: float
    error_ratio_tolerance: float

    def describe(self) -> str:
        return (
            "recovered when >= affected_replicas replacement pods are Ready, then "
            f">= {self.stable_samples} consecutive availability samples >= baseline "
            f"desired replicas with no gap > {self.max_gap_seconds:g}s, and (if the "
            "baseline had traffic) requests flow with 5xx ratio <= baseline + "
            f"{self.error_ratio_tolerance:g}"
        )


@dataclass(frozen=True)
class PodTimes:
    name: str
    created_at: float
    ready_at: float | None


@dataclass(frozen=True)
class RecoveryFinding:
    recovered: bool
    message: str
    fault_observed_at: float | None = None  # first replacement pod created
    recovered_at: float | None = None  # N-th replacement Ready
    confirmed_at: float | None = None  # last sample of the stable streak
    streak: list[tuple[float, float]] = field(default_factory=list)
    # Largest gap between availability samples since the fault (data quality).
    max_observed_gap: float | None = None

    @property
    def time_to_recovery_seconds(self) -> float | None:
        if self.recovered_at is None or self.fault_observed_at is None:
            return None
        return self.recovered_at - self.fault_observed_at


def observation_queries(
    target: ExperimentTarget, window_seconds: int
) -> dict[str, str]:
    """Queries evaluated at the current time covering [fault start, now]."""
    ns = target.namespace
    w = f"[{window_seconds}s]"
    if target.kind is WorkloadKind.DEPLOYMENT:
        available = (
            "kube_deployment_status_replicas_available"
            f'{{namespace="{ns}",deployment="{target.name}"}}'
        )
    else:
        available = (
            "kube_statefulset_status_replicas_ready"
            f'{{namespace="{ns}",statefulset="{target.name}"}}'
        )
    pods = f'namespace="{ns}",pod=~"{pod_name_regex(target)}"'
    restarts = f"kube_pod_container_status_restarts_total{{{pods}}}"
    requests = f"http_requests_total{{{pods}}}"
    errors = f'http_requests_total{{{pods},status=~"5.."}}'
    return {
        "availability_raw": f"{available}{w}",
        "pod_created": f"last_over_time(kube_pod_created{{{pods}}}{w})",
        "pod_ready_time": f"last_over_time(kube_pod_status_ready_time{{{pods}}}{w})",
        "restarts_in_window": (
            f"sum(max_over_time({restarts}{w}) - min_over_time({restarts}{w}))"
        ),
        "requests_in_window": f"sum(increase({requests}{w}))",
        "errors_in_window": f"sum(increase({errors}{w}))",
    }


def window_request_queries(target: ExperimentTarget, seconds: int) -> dict[str, str]:
    pods = f'namespace="{target.namespace}",pod=~"{pod_name_regex(target)}"'
    return {
        "requests": f"sum(increase(http_requests_total{{{pods}}}[{seconds}s]))",
        "errors": (
            f'sum(increase(http_requests_total{{{pods},status=~"5.."}}[{seconds}s]))'
        ),
    }


def find_recovery(
    *,
    fault_start: float,
    affected_replicas: int,
    desired_replicas: int,
    pods: list[PodTimes],
    availability: list[tuple[float, float]],
    rule: RecoveryRule,
) -> RecoveryFinding:
    after_fault = [(t, v) for t, v in availability if t >= fault_start]
    gaps = [b[0] - a[0] for a, b in pairwise(after_fault)]
    max_gap = max(gaps) if gaps else None

    # Pod timestamps have 1s resolution; allow for truncation.
    replacements = sorted(
        (
            p
            for p in pods
            if p.created_at >= int(fault_start) and p.ready_at is not None
        ),
        key=lambda p: (p.ready_at, p.name),
    )
    created = [p for p in pods if p.created_at >= int(fault_start)]
    if len(replacements) < affected_replicas:
        return RecoveryFinding(
            False,
            f"{len(replacements)}/{affected_replicas} replacement pods Ready "
            f"({len(created)} created since fault start)",
            max_observed_gap=max_gap,
        )
    needed = replacements[:affected_replicas]
    recovered_at = needed[-1].ready_at
    assert recovered_at is not None
    fault_observed_at = min(p.created_at for p in needed)

    streak: list[tuple[float, float]] = []
    for ts, value in after_fault:
        if ts < recovered_at:
            continue
        gap_ok = not streak or ts - streak[-1][0] <= rule.max_gap_seconds
        if value >= desired_replicas and gap_ok:
            streak.append((ts, value))
        elif value >= desired_replicas:
            streak = [(ts, value)]  # gap in data: start over
        else:
            streak = []
        if len(streak) >= rule.stable_samples:
            return RecoveryFinding(
                True,
                f"{affected_replicas} replacement pod(s) Ready, then "
                f"{len(streak)} consecutive samples >= {desired_replicas} available",
                fault_observed_at=fault_observed_at,
                recovered_at=recovered_at,
                confirmed_at=streak[-1][0],
                streak=list(streak),
                max_observed_gap=max_gap,
            )
    return RecoveryFinding(
        False,
        f"Replacement pod(s) Ready; {len(streak)}/{rule.stable_samples} consecutive "
        f"samples >= {desired_replicas} available so far",
        fault_observed_at=fault_observed_at,
        recovered_at=recovered_at,
        streak=list(streak),
        max_observed_gap=max_gap,
    )


def error_check(
    *,
    requests: float | None,
    errors: float | None,
    baseline_error_ratio: float,
    rule: RecoveryRule,
) -> tuple[bool, str, float | None]:
    """Criterion 3 for the stable window. Returns (ok, message, observed ratio)."""
    if not requests:
        return False, "No requests served during the stable window", None
    ratio = round((errors or 0.0) / requests, 4)
    limit = baseline_error_ratio + rule.error_ratio_tolerance
    ok = ratio <= limit
    return ok, f"5xx ratio {ratio} {'<=' if ok else '>'} limit {limit:g}", ratio
