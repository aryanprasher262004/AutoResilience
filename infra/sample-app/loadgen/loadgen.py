"""Client-side load generator exporting what the client actually experienced.

Stdlib only (runs on a stock python image; the script is mounted from a ConfigMap).
Each target gets its own sequential worker sending one request per INTERVAL_SECONDS
over a NEW connection each time (no keep-alive), so every request is load-balanced
by the Service like an independent client.

Metrics on :9100/metrics:
  loadgen_requests_total{target_namespace,target_workload,outcome}
      outcome = success | http_error | connection_error | timeout
  loadgen_request_duration_seconds{...}  histogram of requests that got a response

Classification:
  success           response with status < 500
  http_error        response with status >= 500
  timeout           no connection or response within TIMEOUT_SECONDS
  connection_error  refused, reset, DNS failure or connection closed without a response
"""

import http.client
import os
import socket
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OUTCOMES = ("success", "http_error", "connection_error", "timeout")
BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5)
INTERVAL = float(os.environ.get("INTERVAL_SECONDS", "0.1"))
TIMEOUT = float(os.environ.get("TIMEOUT_SECONDS", "1"))
# "namespace/workload=url;..." e.g. "shop/checkout=http://checkout/"
TARGETS = [
    (key.split("/", 1)[0], key.split("/", 1)[1], url)
    for key, url in (item.split("=", 1) for item in os.environ["TARGETS"].split(";") if item)
]


class Stats:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.counts = dict.fromkeys(OUTCOMES, 0)
        self.buckets = [0] * len(BUCKETS)
        self.duration_sum = 0.0
        self.duration_count = 0

    def record(self, outcome: str, duration: float | None) -> None:
        with self.lock:
            self.counts[outcome] += 1
            if duration is not None:
                self.duration_sum += duration
                self.duration_count += 1
                for i, bound in enumerate(BUCKETS):
                    if duration <= bound:
                        self.buckets[i] += 1


STATS = {(ns, workload): Stats() for ns, workload, _ in TARGETS}


def probe(url: str) -> tuple[str, float | None]:
    parts = urllib.parse.urlsplit(url)
    started = time.monotonic()
    conn = http.client.HTTPConnection(parts.hostname, parts.port or 80, timeout=TIMEOUT)
    try:
        conn.request("GET", parts.path or "/", headers={"Connection": "close"})
        response = conn.getresponse()
        response.read()
        duration = time.monotonic() - started
        return ("success" if response.status < 500 else "http_error"), duration
    except TimeoutError:  # socket.timeout: connect or read exceeded TIMEOUT
        return "timeout", None
    except (OSError, http.client.HTTPException):  # refused/reset/DNS/RemoteDisconnected
        return "connection_error", None
    finally:
        conn.close()


def worker(ns: str, workload: str, url: str) -> None:
    stats = STATS[(ns, workload)]
    while True:
        started = time.monotonic()
        outcome, duration = probe(url)
        stats.record(outcome, duration)
        time.sleep(max(0.0, INTERVAL - (time.monotonic() - started)))


def render() -> str:
    lines = [
        "# HELP loadgen_requests_total Client requests by outcome.",
        "# TYPE loadgen_requests_total counter",
    ]
    for (ns, workload), s in STATS.items():
        labels = f'target_namespace="{ns}",target_workload="{workload}"'
        with s.lock:
            for outcome in OUTCOMES:
                lines.append(
                    f'loadgen_requests_total{{{labels},outcome="{outcome}"}} {s.counts[outcome]}'
                )
    lines += [
        "# HELP loadgen_request_duration_seconds Latency of requests that got a response.",
        "# TYPE loadgen_request_duration_seconds histogram",
    ]
    for (ns, workload), s in STATS.items():
        labels = f'target_namespace="{ns}",target_workload="{workload}"'
        with s.lock:
            for bound, count in zip(BUCKETS, s.buckets, strict=True):
                lines.append(
                    f'loadgen_request_duration_seconds_bucket{{{labels},le="{bound}"}} {count}'
                )
            lines.append(
                f'loadgen_request_duration_seconds_bucket{{{labels},le="+Inf"}} {s.duration_count}'
            )
            lines.append(f"loadgen_request_duration_seconds_sum{{{labels}}} {s.duration_sum}")
            lines.append(f"loadgen_request_duration_seconds_count{{{labels}}} {s.duration_count}")
    return "\n".join(lines) + "\n"


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        body = render().encode() if self.path == "/metrics" else b"ok\n"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; version=0.0.4")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


if __name__ == "__main__":
    socket.setdefaulttimeout(TIMEOUT)
    for ns, workload, url in TARGETS:
        threading.Thread(target=worker, args=(ns, workload, url), daemon=True).start()
    ThreadingHTTPServer(("", 9100), Handler).serve_forever()
