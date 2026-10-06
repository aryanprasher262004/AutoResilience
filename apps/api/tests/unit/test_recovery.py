import pytest

from app.domain.experiment import ExperimentTarget, WorkloadKind
from app.services.orchestration.recovery import (
    PodTimes,
    RecoveryFinding,
    RecoveryRule,
    error_check,
    find_recovery,
    observation_queries,
)

RULE = RecoveryRule(stable_samples=4, max_gap_seconds=40, error_ratio_tolerance=0.01)
T0 = 1_000_000.0  # fault start
OLD = PodTimes("checkout-a-11111", T0 - 3600, T0 - 3590)
NEW = PodTimes("checkout-a-22222", T0 + 5, T0 + 7)


def samples(
    *values: float, start: float = T0, step: float = 15
) -> list[tuple[float, float]]:
    return [(start + step * i, v) for i, v in enumerate(values)]


def recover(
    availability: list[tuple[float, float]],
    pods: list[PodTimes] | None = None,
    affected: int = 1,
    desired: int = 2,
) -> RecoveryFinding:
    return find_recovery(
        fault_start=T0,
        affected_replicas=affected,
        desired_replicas=desired,
        pods=[OLD, NEW] if pods is None else pods,
        availability=availability,
        rule=RULE,
    )


def test_recovers_after_replacement_ready_and_stable_streak() -> None:
    finding = recover(samples(2, 2, 2, 2, 2, 2))

    assert finding.recovered
    assert finding.fault_observed_at == T0 + 5
    assert finding.recovered_at == T0 + 7
    assert finding.time_to_recovery_seconds == 2
    # Samples before the replacement was Ready don't count: streak starts at T0+15.
    assert [t for t, _ in finding.streak] == [T0 + 15, T0 + 30, T0 + 45, T0 + 60]
    assert finding.confirmed_at == T0 + 60


def test_single_good_sample_is_not_recovery() -> None:
    finding = recover(samples(2, 2))

    assert not finding.recovered
    assert "1/4 consecutive samples" in finding.message


def test_dip_resets_the_streak() -> None:
    finding = recover(samples(2, 2, 2, 1, 2, 2, 2, 2))

    assert finding.recovered
    assert finding.streak[0][0] == T0 + 60


def test_data_gap_resets_the_streak() -> None:
    availability = samples(2, 2, 2) + samples(2, 2, 2, start=T0 + 120)

    finding = recover(availability)

    assert not finding.recovered
    assert finding.max_observed_gap == 90


def test_no_ready_replacement_is_not_recovery() -> None:
    pending = PodTimes("checkout-a-33333", T0 + 5, None)

    finding = recover(samples(2, 2, 2, 2, 2), pods=[OLD, pending])

    assert not finding.recovered
    assert finding.message == "0/1 replacement pods Ready (1 created since fault start)"


def test_pods_from_before_the_fault_are_not_replacements() -> None:
    finding = recover(samples(2, 2, 2, 2, 2), pods=[OLD])
    assert not finding.recovered


def test_multiple_affected_replicas_wait_for_last_replacement() -> None:
    slow = PodTimes("checkout-a-44444", T0 + 6, T0 + 40)

    finding = recover(samples(*[3] * 8), pods=[OLD, NEW, slow], affected=2, desired=3)

    assert finding.recovered
    assert finding.recovered_at == T0 + 40
    assert finding.streak[0][0] == T0 + 45


def test_below_desired_never_recovers() -> None:
    assert not recover(samples(*[1] * 10)).recovered


def test_is_deterministic() -> None:
    assert recover(samples(2, 2, 2, 2, 2)) == recover(samples(2, 2, 2, 2, 2))


@pytest.mark.parametrize(
    ("requests", "errors", "baseline", "ok"),
    [
        (100.0, None, 0.0, True),
        (100.0, 1.0, 0.0, True),  # 0.01 == limit
        (100.0, 2.0, 0.0, False),
        (100.0, 5.0, 0.05, True),
        (None, None, 0.0, False),  # no traffic: cannot show the service is serving
        (0.0, None, 0.0, False),
    ],
)
def test_error_check(
    requests: float | None, errors: float | None, baseline: float, ok: bool
) -> None:
    assert (
        error_check(
            requests=requests, errors=errors, baseline_error_ratio=baseline, rule=RULE
        )[0]
        is ok
    )


def test_observation_queries_cover_the_window() -> None:
    q = observation_queries(
        ExperimentTarget("shop", WorkloadKind.DEPLOYMENT, "checkout"), 120
    )

    assert q["availability_raw"] == (
        'kube_deployment_status_replicas_available{namespace="shop",deployment="checkout"}[120s]'
    )
    assert q["pod_ready_time"].startswith("last_over_time(kube_pod_status_ready_time{")
    assert all("[120s]" in v for v in q.values())
