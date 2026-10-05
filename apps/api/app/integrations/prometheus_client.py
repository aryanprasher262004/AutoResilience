"""Read-only Prometheus HTTP API client (instant queries only)."""

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx


class PrometheusError(Exception):
    """Prometheus could not answer a query (network, timeout, HTTP or query error)."""


@dataclass(frozen=True)
class Sample:
    labels: dict[str, str]
    value: float


class PrometheusClient:
    def __init__(
        self,
        base_url: str,
        timeout: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url, timeout=timeout, transport=transport
        )

    def query(self, promql: str, at: datetime) -> list[Sample]:
        """Evaluate an instant-vector query at a fixed time. NaN samples are dropped."""
        try:
            response = self._http.get(
                "/api/v1/query", params={"query": promql, "time": at.timestamp()}
            )
        except httpx.HTTPError as exc:
            raise PrometheusError(f"Prometheus unreachable: {exc!r}") from exc

        body = _json(response)
        if response.status_code != 200 or body.get("status") != "success":
            detail = body.get("error") or response.reason_phrase
            raise PrometheusError(
                f"Prometheus query failed ({response.status_code}): {detail}"
            )

        data = body.get("data") or {}
        if data.get("resultType") != "vector":
            raise PrometheusError(
                f"Expected vector result, got {data.get('resultType')!r}"
            )
        samples = [
            Sample(labels=r["metric"], value=float(r["value"][1]))
            for r in data.get("result", [])
        ]
        return [s for s in samples if not math.isnan(s.value)]

    def query_value(self, promql: str, at: datetime) -> float | None:
        """Single-value query: None if empty, error if it unexpectedly returns several."""
        samples = self.query(promql, at)
        if len(samples) > 1:
            raise PrometheusError(f"Expected one series, got {len(samples)}: {promql}")
        return samples[0].value if samples else None


def _json(response: httpx.Response) -> dict[str, Any]:
    try:
        body = response.json()
    except ValueError as exc:
        raise PrometheusError(
            f"Prometheus returned non-JSON response ({response.status_code})"
        ) from exc
    if not isinstance(body, dict):
        raise PrometheusError("Prometheus returned an unexpected response shape")
    return body
