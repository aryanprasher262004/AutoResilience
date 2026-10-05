# Baseline PromQL (Contract)

Queries used by `apps/api/app/services/orchestration/baseline.py` (`baseline_queries`).
All are instant queries evaluated at one shared timestamp; `W` is `BASELINE_WINDOW_SECONDS` (default 300s).

## Metric sources

| Source | Metrics | Present for |
|---|---|---|
| kube-state-metrics (chart subchart) | `kube_deployment_spec_replicas`, `kube_deployment_status_replicas_available`, `kube_statefulset_replicas`, `kube_statefulset_status_replicas_ready`, `kube_pod_container_status_restarts_total` | every Deployment/StatefulSet |
| App pods with `prometheus.io/scrape: "true"` | `http_requests_total{status}` | only targets that expose it (sample app: `shop/checkout`, podinfo) |

Target pods are selected by name: Deployment `<name>-[a-z0-9]+-[a-z0-9]{5}`, StatefulSet `<name>-[0-9]+`.

## Groups

| Group | Required | Queries | Fails when |
|---|---|---|---|
| availability | yes | `kube_*_spec/replicas` (desired), `avg_over_time`, `min_over_time`, `count_over_time` of available/ready replicas over `W` | fewer than 4 samples in `W`, or Prometheus error |
| restarts | yes | `sum(restarts)`, `sum(max_over_time(restarts[W]) - min_over_time(restarts[W]))` | no restart series, or Prometheus error |
| requests | no | `count(http_requests_total)`, `sum(rate(...[W]))`, `sum(rate(...{status=~"5.."}[W]))` | Prometheus error only. A target without the metric is `UNAVAILABLE` (does not block). |

A baseline is `CAPTURED` only if both required groups are `OK` and `requests` is not `ERROR`; only then does the experiment move `BASELINING → INJECTING`.
