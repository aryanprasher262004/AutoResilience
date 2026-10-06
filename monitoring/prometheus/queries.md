# Baseline PromQL (Contract)

Queries used by `apps/api/app/services/orchestration/baseline.py` (`baseline_queries`).
All are instant queries evaluated at one shared timestamp; `W` is `BASELINE_WINDOW_SECONDS` (default 300s).

## Metric sources

| Source | Metrics | Present for |
|---|---|---|
| kube-state-metrics (chart subchart) | `kube_deployment_spec_replicas`, `kube_deployment_status_replicas_available`, `kube_statefulset_replicas`, `kube_statefulset_status_replicas_ready`, `kube_pod_container_status_restarts_total` | every Deployment/StatefulSet |
| App pods with `prometheus.io/scrape: "true"` | `http_requests_total{status}` | only targets that expose it (sample app: `shop/checkout`, podinfo) |
| Load generator (`infra/sample-app/loadgen`) | `loadgen_requests_total{target_namespace,target_workload,outcome}`, `loadgen_request_duration_seconds` | workloads listed in its `TARGETS` (`shop/checkout`, `shop/frontend`) |

Target pods are selected by name: Deployment `<name>-[a-z0-9]+-[a-z0-9]{5}`, StatefulSet `<name>-[0-9]+`.

## Groups

| Group | Required | Queries | Fails when |
|---|---|---|---|
| availability | yes | `kube_*_spec/replicas` (desired), `avg_over_time`, `min_over_time`, `count_over_time` of available/ready replicas over `W` | fewer than 4 samples in `W`, or Prometheus error |
| restarts | yes | `sum(restarts)`, `sum(max_over_time(restarts[W]) - min_over_time(restarts[W]))` | no restart series, or Prometheus error |
| requests | no | `count(http_requests_total)`, `sum(rate(...[W]))`, `sum(rate(...{status=~"5.."}[W]))` | Prometheus error only. A target without the metric is `UNAVAILABLE` (does not block). |

| client | no | `count(loadgen_requests_total{target_namespace,target_workload})`, `sum(rate(...[W]))`, `sum(rate(...{outcome!="success"}[W]))`, p95 from `loadgen_request_duration_seconds_bucket` | Prometheus error only. A target the load generator does not hit is `UNAVAILABLE`. |

A baseline is `CAPTURED` only if both required groups are `OK` and neither optional group (`requests`, `client`) is `ERROR`; only then does the experiment move `BASELINING → INJECTING`.

# Observation / recovery PromQL (Contract)

Queries used by `apps/api/app/services/orchestration/recovery.py` (`observation_queries`,
`window_request_queries`), evaluated at the current time with `W` = seconds since the
ChaosEngine was created.

| Purpose | Query | Notes |
|---|---|---|
| Client outcomes (raw counters) | `loadgen_requests_total{target_namespace,target_workload}[W+60s]` | Exact per-outcome counts from the last scrape before the fault; failure intervals at scrape resolution. |
| Client latency | `histogram_quantile(0.95, sum by (le) (rate(loadgen_request_duration_seconds_bucket{…}[W])))` | Evidence only. |
| Availability (raw scrapes) | `kube_deployment_status_replicas_available{…}[W]` (StatefulSet: `kube_statefulset_status_replicas_ready`) | Range selector returns actual samples, so data gaps stay visible (no lookback fill). |
| Replacement pods | `last_over_time(kube_pod_created{pod=~…}[W])`, `last_over_time(kube_pod_status_ready_time{pod=~…}[W])` | Kubernetes object timestamps (1s resolution), independent of the 15s scrape interval. |
| Impact | `sum(max_over_time(restarts[W]) - min_over_time(restarts[W]))`, `sum(increase(http_requests_total[W]))`, same with `status=~"5.."` | Evidence only. |
| Stable-window errors | `sum(increase(http_requests_total[S]))` and 5xx, evaluated at the end of the stable streak, `S` = streak length | Recovery criterion 3 when the baseline had traffic. |

Measurement limits observed on kind: a podinfo replacement is Ready ~1s after deletion,
so 15s availability scrapes typically show **no dip**; recovery timing therefore comes from
the pod timestamps. Server-side `http_requests_total` cannot see connections refused while
a pod terminates; the load generator's client counters can (see docs/scoring/resilience-score-v2.md).
