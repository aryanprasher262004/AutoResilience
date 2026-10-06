"""Client-observed outage measurement (recovery.client_outage)."""

from typing import Any

import pytest

from app.services.orchestration.recovery import client_outage
from tests.conftest import FakePrometheus

T0 = 1_000_000.0


def measure(**kwargs: Any) -> dict[str, Any]:
    fake = FakePrometheus()
    fake.outage_counters(T0, **kwargs)
    return client_outage(fake.client_outage, T0)


def test_no_outage() -> None:
    result = measure()

    assert result["status"] == "OK"
    assert result["pattern"] == "NONE"
    assert (result["outage_seconds"], result["outages"]) == (0.0, 0)
    assert result["outage_windows"] == []


def test_continuous_outage_measured_exactly() -> None:
    result = measure(outages=[(3.2, 12.6)])

    assert result["pattern"] == "CONTINUOUS"
    assert result["outage_seconds"] == 9.4
    assert result["outages"] == 1
    assert result["reason"] == "Continuous client outage of 9.4s"
    (window,) = result["outage_windows"]
    assert window["seconds"] == 9.4


def test_short_outage_between_scrapes_is_not_missed() -> None:
    """A 1.5s outage entirely between two 15s scrapes is still fully counted."""
    result = measure(outages=[(1.0, 2.5)])
    assert result["outage_seconds"] == 1.5
    assert result["pattern"] == "CONTINUOUS"


@pytest.mark.parametrize("scrape_every", [5, 15, 30, 60])
def test_duration_independent_of_scrape_interval(scrape_every: float) -> None:
    result = measure(outages=[(3.2, 12.6)], scrape_every=scrape_every, samples=8)
    assert result["outage_seconds"] == 9.4


def test_scrape_gap_loses_no_seconds() -> None:
    """Missing scrapes during the outage: counters still carry the full duration."""
    result = measure(outages=[(3.2, 12.6)], scrape_every=45, samples=4)
    assert result["outage_seconds"] == 9.4


def test_intermittent_failures() -> None:
    result = measure(outages=[(2.0, 2.3), (5.0, 5.2), (20.0, 20.5)])

    assert result["pattern"] == "INTERMITTENT"
    assert result["outages"] == 3
    assert result["outage_seconds"] == 1.0
    assert "3 outages totalling 1s" in str(result["reason"])


def test_outage_still_in_progress_at_last_scrape_counts_accrued_time() -> None:
    result = measure(outages=[(5.0, 500.0)], samples=4)  # scrapes up to T0+30

    assert result["pattern"] == "CONTINUOUS"
    assert result["outage_seconds"] == 25.0
    (window,) = result["outage_windows"]
    assert window["end"] is None


def test_counter_reset_is_insufficient_data() -> None:
    # Reset after the outage was counted: counters drop from 10s/1 back to 0.
    result = measure(outages=[(3.0, 13.0)], reset_at=3)

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["reset_detected"] is True
    assert "load generator restarted" in str(result["reason"])


def test_counting_started_after_fault_is_insufficient() -> None:
    result = measure(outages=[(20.0, 25.0)], first_scrape=10)

    assert result["status"] == "INSUFFICIENT_DATA"
    assert result["starts_before_fault"] is False


def test_missing_series_is_insufficient() -> None:
    result = client_outage([], T0)
    assert result["status"] == "INSUFFICIENT_DATA"
    assert "No client outage series" in str(result["reason"])


def test_outage_before_the_window_is_excluded() -> None:
    result = measure(outages=[(-120.0, -100.0)])  # ended before the fault
    assert result["pattern"] == "NONE"
    assert result["outage_windows"] == []
