# Resilience Score v3

v3 is the current version, computed automatically for new experiments. It differs from
[v2](resilience-score-v2.md) in **one component**: the sampled Kubernetes `availability` is
replaced by **`client_outage`**, the outage duration measured by the client. Everything else is
identical to v2:
- `recovery_time`, `request_failures`, `restarts` and `litmus_verdict`, with their weights and
  thresholds;
- the formula and `NOT_APPLICABLE` re-normalization;
- the platform/application `UNKNOWN` policy and the not-recovered cap of 40;
- the rating bands.

v1 and v2 stay reproducible from the same stored evidence via `GET /score?version=v1|v2`.

## Decision: why

v2's availability was the minimum of 15 s Kubernetes samples. On real sandbox runs, a 10 s
outage scored 0/15 or 15/15 depending only on whether a scrape landed inside it, enough to
reverse the order of two runs. v3 uses a duration the client measures itself, independent of
the scrape interval.

## Measurement contract (load generator)

Per target, from the client's own requests (`infra/sample-app/loadgen/loadgen.py`):
- **Outage boundaries:** an outage **starts** at the start of the first failing request after
  a success, and **ends** at the start of the next successful request. Resolution is one
  request interval: 0.1 s, or up to the 1 s timeout while requests time out.
- **`loadgen_outage_seconds_total`** (counter): down time, accrued *during* the outage. A
  scrape taken mid-outage already includes it, and scrape gaps lose no seconds.
- **`loadgen_outages_total`** (counter): up → down transitions.
- **`loadgen_last_outage_{start,end}_timestamp_seconds`** (gauges): exact timing of the most
  recent outage.

**Observation** (`observation.impact.client.outage`) uses the raw samples from the last scrape
before the fault onwards:
- `outage_seconds` and `outages` are exact counter increases, with no extrapolation;
- `outage_windows` come from the gauges;
- `pattern` is one of:

| Pattern | When |
|---|---|
| `NONE` | 0 s and 0 transitions |
| `CONTINUOUS` | one outage, or one already in progress when the window started |
| `INTERMITTENT` | more than one outage |
| `INSUFFICIENT_DATA` | series missing, counting started after the fault, or a **counter reset** (the load generator restarted, so down time may be lost) |

**Baseline** (`baseline.client.values`) adds `client_outage_seconds` and `client_outages` over
the baseline window.

## Formula for `client_outage` (weight 15)

```
expected = baseline_outage_seconds / baseline_window_seconds × observation_window_seconds
excess   = max(0, measured_outage_seconds − expected)
normalized = 1                        if excess ≤ 1 s
           = 0                        if excess ≥ 60 s
           = 1 − (excess − 1) / 59    otherwise
```

The reason states the pattern (continuous with exact start → end, intermittent with its count,
or none). If the client data is `INSUFFICIENT_DATA`, the target has no client measurement, or
the client recorded no requests, the component falls back to v2's sampled availability. In
that case `raw.source` is `kubernetes_sampled` and the reason begins `[fallback: …]`.

## Real runs (kind, `resilience-sandbox/fragile`, 1 replica with a 10 s warm-up, 30 s pod-delete)

| | GRACEFUL | FORCE |
|---|---|---|
| Pod timeline | stopped serving at 11:19:47.168; replacement Ready at about 11:19:55 | object deleted at 11:26:21.226 (the container kept serving about 1 s); Ready at about 11:26:31 |
| **Measured client outage** | **CONTINUOUS 8.358 s** (11:19:47.198 → 11:19:55.557) | **CONTINUOUS 10.479 s** (11:26:22.304 → 11:26:32.782) |
| Client failures | 20/678 (13 connection errors, 7 timeouts) | 23/658 (15 connection errors, 8 timeouts) |
| Kubernetes min available (15 s samples) | 0/1 (caught by a scrape) | 1/1 (missed) |
| v2 availability → v2 score | 0/15 → **67.2** | 15/15 → **79.2** |
| v3 client_outage → v3 score | 13.13/15 → **80.4** | 12.59/15 → **76.8** |
| v1 score | 74.7 | 100.0 |

v2's ordering was reversed by scrape timing alone. v3 follows the measured outage: FORCE had
the longer outage and the lower score.

## Limitations

- **Overlap with request_failures:** `request_failures` (weight 30) and `client_outage`
  (weight 15) both reflect the same outage, from different angles (proportion of requests vs
  duration). The failure ratio is still diluted by the length of the observation window.
- **One client per target:** the outage is that client's view, at its 10 req/s, through the
  Service.
- **Restarted load generator:** if it restarts inside the window, the run falls back to sampled
  availability and says so.
