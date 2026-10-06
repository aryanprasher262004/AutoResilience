import json
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
import pytest

from app.integrations.prometheus_client import PrometheusClient, PrometheusError, Sample

AT = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> PrometheusClient:
    return PrometheusClient(
        "http://prom:9090", 5, transport=httpx.MockTransport(handler)
    )


def vector(*results: tuple[dict[str, str], str]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "status": "success",
            "data": {
                "resultType": "vector",
                "result": [
                    {"metric": m, "value": [AT.timestamp(), v]} for m, v in results
                ],
            },
        },
    )


def test_query_sends_read_only_instant_query_at_fixed_time() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return vector(({"pod": "a"}, "1.5"), ({"pod": "b"}, "2"))

    samples = client_for(handler).query('up{job="x"}', AT)

    assert samples == [Sample({"pod": "a"}, 1.5), Sample({"pod": "b"}, 2.0)]
    (request,) = seen
    assert request.method == "GET"
    assert request.url.path == "/api/v1/query"
    assert request.url.params["query"] == 'up{job="x"}'
    assert float(request.url.params["time"]) == AT.timestamp()


def test_nan_samples_are_dropped() -> None:
    client = client_for(lambda _: vector(({}, "NaN")))
    assert client.query("x", AT) == []
    assert client.query_value("x", AT) is None


def test_query_value() -> None:
    assert client_for(lambda _: vector(({}, "3"))).query_value("x", AT) == 3.0
    assert client_for(lambda _: vector()).query_value("x", AT) is None
    with pytest.raises(PrometheusError, match="Expected one series, got 2"):
        client_for(lambda _: vector(({}, "1"), ({}, "2"))).query_value("x", AT)


def raise_(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


@pytest.mark.parametrize(
    ("handler", "message"),
    [
        (raise_(httpx.ConnectError("refused")), "Prometheus unreachable"),
        (raise_(httpx.ReadTimeout("slow")), "Prometheus unreachable"),
        (
            lambda _: httpx.Response(
                400, json={"status": "error", "error": "parse error at char 3"}
            ),
            r"query failed \(400\): parse error at char 3",
        ),
        (lambda _: httpx.Response(503, text="<html>down</html>"), "non-JSON"),
        (
            lambda _: httpx.Response(
                200,
                json={
                    "status": "success",
                    "data": {"resultType": "matrix", "result": []},
                },
            ),
            "Expected vector result",
        ),
        (lambda _: httpx.Response(200, content=json.dumps([1])), "unexpected response"),
    ],
)
def test_failures_raise_prometheus_error(
    handler: Callable[[httpx.Request], httpx.Response], message: str
) -> None:
    with pytest.raises(PrometheusError, match=message):
        client_for(handler).query("x", AT)


def test_query_raw_returns_scraped_samples() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "success",
                "data": {
                    "resultType": "matrix",
                    "result": [
                        {
                            "metric": {"deployment": "checkout"},
                            "values": [[100.0, "2"], [115.0, "NaN"], [130.0, "1"]],
                        }
                    ],
                },
            },
        )

    (series,) = client_for(handler).query_raw("x[1m]", AT)

    assert series.labels == {"deployment": "checkout"}
    assert series.samples == [(100.0, 2.0), (130.0, 1.0)]


def test_query_raw_rejects_vector() -> None:
    with pytest.raises(PrometheusError, match="Expected matrix result"):
        client_for(lambda _: vector(({}, "1"))).query_raw("x", AT)
