# Services (workload discovery)

Implementation: `apps/api/app/services/analysis/services.py`, routes in
`apps/api/app/api/routes/targets.py`, adapter `KubernetesAdapter.list_workloads()`.

## Contract: `GET /services`

Every Deployment and StatefulSet outside `SYSTEM_NAMESPACES` (the safety policy's
forbidden namespaces, returned as `excluded_namespaces`), sorted by namespace and name.

| Field | Source |
|---|---|
| `desired_replicas`, `current_replicas`, `ready_replicas`, `available_replicas` | the controller's `spec.replicas` / `status.*`: the numbers `kubectl get` shows |
| `health` | `SCALED_TO_ZERO` (desired 0), `HEALTHY` (ready ≥ desired), `DEGRADED` (some ready), `UNAVAILABLE` (none ready) |
| `experiment_count`, `latest_experiment` | experiments whose target is exactly this namespace/kind/name |
| `latest_score` | newest experiment with a numeric score, any methodology version (`version` is included) |

Kubernetes unreachable → **503** with the adapter's message. The list is not paged: it is
one cluster's inventory, and the console filters and sorts it in the browser.

## Contract: `GET /services/{namespace}/{kind}/{name}`

- `live`: pod-level status from `get_workload_status`, the same read safety validation uses
  (running, ready, ready pod names).
- `health` adds `NOT_FOUND` (deleted, but history kept) and `UNKNOWN` (cluster error, in
  `cluster_error`; history is still returned).
- `faults`: runs, completed and latest score per fault type and deletion mode.
- `score_history`: current methodology only, oldest first; `experiments`: newest 50.
- 404 for system namespaces, and for workloads that are neither in the cluster nor in history.

## Decision

Discovery is read-only and hides exactly the namespaces the safety policy forbids, so
everything offered as a target can at least pass the namespace check. `local-path-storage`
(kind's storage provisioner) was added to `SYSTEM_NAMESPACES` for this reason. The
builder's picker only fills the target fields; server-side validation stays authoritative,
and manual entry remains possible.
