# Resilience Score v2

> **Superseded by [v3](resilience-score-v3.md)** for new experiments (measured client outage
> replaces sampled availability). v2 stays reproducible via `GET /experiments/{id}/score?version=v2`.

v2 differs from
[v1](resilience-score-v1.md) **only** in how request failures and availability are weighted
and measured. Everything else is unchanged: the formula, recovery and restart components,
thresholds, the `NOT_APPLICABLE` re-normalization, the platform/application `UNKNOWN` policy,
the not-recovered cap of 40, and the rating bands.

v1 remains reproducible from the same stored evidence: `GET /experiments/{id}/score?version=v1`.

## Decision: why a new version

v1 scored request impact from the **server-side** 5xx ratio and availability from 15 s
Kubernetes samples. Neither can see what clients experience during a short disruption:
- connections refused or reset while a pod terminates never reach the server's metrics;
- an outage shorter than the scrape interval is invisible to a gauge sample.

The load generator (`infra/sample-app/loadgen/loadgen.py`) now exports client **counters**
(`loadgen_requests_total{target_namespace,target_workload,outcome}`). Counters accumulate
every event, so a one-second outage between two scrapes is still counted. Using them changes
what the request component means, so it is a new version rather than a silent change to v1.

## What changed

| Component | v1 | v2 |
|---|---|---|
| recovery_time | 35 | 35 (unchanged) |
| availability (min replicas over 15 s samples) | 25 | **15**. Coarse; client failures now measure user-visible availability directly. |
| `error_ratio` (server 5xx) → **`request_failures`** | 20 | **30** |
| restarts | 10 | 10 |
| litmus_verdict | 10 | 10 |

`request_failures` takes the first available source:
1. **client**, when the baseline has a client group with traffic and the fault window recorded
   client requests:
   - failure ratio = (`http_error` + `connection_error` + `timeout`) / requests, compared with
     the baseline client failure ratio;
   - outcomes as classified by the client: a response with status ≥ 500 is `http_error`;
     refused, reset or DNS failure is `connection_error`; no response within 1 s is `timeout`.
2. **server**: the v1 server-side 5xx ratio. The reason states why the client source was not
   used:
   - the target has no client baseline; or
   - the load generator recorded **zero** requests in the window. Because the generator counts
     failures too, that means it was not running. It is a measurement gap, not a target
     failure.
3. **`NOT_APPLICABLE`** if neither exists. It is excluded and the weights re-normalize.

Thresholds are those of v1: an increase ≤ 0.001 gets full marks, ≥ 0.05 gets zero, linear in
between.

## Contract: client evidence

- **Baseline** gains an optional `client` group: client req/s, failed/s, failure ratio and p95
  latency over the baseline window. It is `UNAVAILABLE` (never failed) for targets without
  load-generator series.
- **`observation.impact.client`** stores:
  - exact per-outcome counts from the raw counter samples, starting at the last scrape before
    the fault (`counted_from` … `counted_to`, with no `increase()` extrapolation and counter
    resets handled);
  - `failure_intervals`: the scrape intervals in which failures occurred (15 s timing
    resolution);
  - `starts_before_fault`, flagged in the reason if counting began late;
  - p95 latency of answered requests over the window.
- **Latency** is evidence only and not scored in v2.

## Observed on kind (`shop/checkout`, pod-delete, graceful)

| Evidence | Value |
|---|---|
| Server/Kubernetes | 2/2 available throughout, 0 server 5xx, replacement Ready in 1 s |
| Client | 740 requests, **0 failed**, p95 latency 4.75 ms, same as the baseline |
| Score | v1 100.0, v2 100.0 |

The graceful delete removes the pod from the Service before podinfo stops serving, so clients
genuinely see nothing.

A separate sensitivity check, outside any experiment and not scored, scaled `checkout` to 0
replicas for about 20 s. The client recorded 23 connection errors and 17 timeouts. The
instrument does report client-visible failures when they really occur.

### Graceful vs forced deletion (`pod_delete_mode`)

The mode is context in the score (`inputs.fault`, explanation); it never changes the number by
itself. Real runs on kind, `shop/checkout`, 30 s each:

| | GRACEFUL | FORCE |
|---|---|---|
| Deleted pod lifecycle | Terminating, then gone after ~4 s (podinfo exits on SIGTERM) | Terminating, then gone after **5 ms** |
| Replacement created → Ready | 1 s | 1 s |
| Kubernetes availability / server 5xx | 2/2, 0 | 2/2, 0 |
| Client | 740 requests, 0 failed, p95 4.75 ms | 739 requests, 0 failed, p95 4.75 ms |
| v2 score | 100.0 | 100.0 |

Forced deletion changes what Kubernetes does but not what this client saw. Deleting the pod
object removes its endpoint before the kubelet kills the container, so new per-request
connections at 10 req/s were already routed to the surviving replica. Equal scores are the
correct outcome of identical evidence.

## Limitations

- **Sequential client:** one sequential client per target at 10 req/s. During timeouts, each
  request blocks for up to 1 s, so the number of failures under-represents outage duration.
  Failure *counts and ratios* are exact; duration is not measured.
- **Window dilution:** the failure ratio is over the whole observation window, from the fault
  to the final evaluation (about 75 s). A longer window dilutes a short outage.
- **Latency resolution:** latency buckets start at 5 ms, so p95 values below that are
  interpolated within the first bucket.
- **Single target mapping:** the target is mapped by the `target_workload` label, so only
  workloads configured in the load generator's `TARGETS` (currently `checkout` and `frontend`)
  have client evidence.
