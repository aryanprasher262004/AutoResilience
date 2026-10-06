# Chaos injection safety (Contract)

What AutoResilience guarantees before and during a LitmusChaos fault. Backend policy
values live in `apps/api/app/domain/safety_policy.py`; this is the chaos-side view.

## Which policy applies

Policies are selected only by the experiment's validated target namespace, through a fixed
mapping in code (`apps/api/app/domain/safety_policy.py`, `POLICIES_BY_NAMESPACE`). No API
field can choose, create or change a policy; unknown request fields are ignored.

| Namespace | Policy | Differs from default |
|---|---|---|
| any other namespace | `default` | — (max 300 s, max 1 affected replica, **min 1 healthy replica**, system namespaces forbidden) |
| `resilience-sandbox` | `sandbox` | `min_healthy_replicas=0`, and `allowed_namespaces={resilience-sandbox}` |

The sandbox policy's allowlist means it cannot validate any other namespace even if it were
selected by mistake. System namespaces stay forbidden under both policies.

Every validation result stores the full policy and a `policy_selection` record (namespace,
policy name and rule). Injection re-resolves the policy and refuses with `INJECTION_FAILED`
if its name differs from the one recorded at validation. `experiments.chaos.safety_policy`
records the policy the fault ran under.

The sandbox namespace is created by `infra/sample-app/sandbox.yaml` (labelled
`autoresilience.io/sandbox=true`) and is reserved for deliberately fragile test workloads.

## Before a ChaosEngine is created (`POST /experiments/{id}/inject`)

1. Experiment is in `INJECTING`, i.e. it passed validation (static + cluster checks)
   and has a `CAPTURED` baseline. Any other state returns 409 and touches nothing.
2. Fault type is `pod-delete` (the only supported type; others fail validation).
3. The namespace's policy is re-resolved and must match the policy recorded at validation.
   Cluster checks are then re-run against live state (workload exists, ready pods,
   ready − affected ≥ `min_healthy_replicas`). A failure → `INJECTION_FAILED`.
4. Target pods = the first `affected_replicas` ready pods by name (deterministic).
5. The provider refuses `SYSTEM_NAMESPACES` (kube-system, kube-public,
   kube-node-lease, litmus, monitoring) independently of validation.
6. The namespace must already contain the vetted `pod-delete` ChaosExperiment
   (`chaos/templates/pod-delete.yaml`) and the `autoresilience-chaos` ServiceAccount
   (`chaos/rbac/pod-delete-rbac.yaml`, applied per chaos namespace: `shop`,
   `resilience-sandbox`); otherwise `INJECTION_FAILED`.

## The ChaosEngine

Built only from typed fields (no user YAML): `appinfo` = validated namespace, workload
selector and kind; `TARGET_PODS` = the chosen pods; `TOTAL_CHAOS_DURATION` =
`CHAOS_INTERVAL` = `duration_seconds` (exactly one deletion round); `FORCE` from the
experiment's validated `pod_delete_mode`:

| `pod_delete_mode` | `FORCE` | Kubernetes deletion (litmus-go 3.31 `pod-delete`) |
|---|---|---|
| `GRACEFUL` (default) | `false` | `DeleteOptions{}`: the pod's `terminationGracePeriodSeconds` applies (SIGTERM first) |
| `FORCE` | `true` | `DeleteOptions{GracePeriodSeconds: 0}`: containers killed immediately |

Only these two values are accepted (422 otherwise); no other Litmus option is exposed. The
mode is labelled on the engine (`autoresilience.io/pod-delete-mode`) and recorded in
`experiments.chaos` and the score's `inputs.fault`. Both modes keep the same target, blast
radius, namespace guard and RBAC. Named `ar-<experiment id>`, labelled
`app.kubernetes.io/managed-by=autoresilience`. Runs as `autoresilience-chaos`, whose
Role only allows deleting pods in its own namespace.

## After creation

`OBSERVING` is entered only when Litmus reports the experiment `Running`/`Completed`
**and** the target pods are gone or terminating. If Litmus reports failure, the
pods are not deleted within `CHAOS_START_TIMEOUT_SECONDS`, or status cannot be read,
the engine is stopped (`engineState: stop`) and the experiment is `INJECTION_FAILED`.
The engine name, target pods and last Litmus status are persisted in `experiments.chaos`.

## Observed on kind: why even a single replica showed no client outage

Real sandbox runs against `resilience-sandbox/fragile` (podinfo, 1 replica, 30 s):

| Mode | Pod timeline | Client | v2 score |
|---|---|---|---|
| GRACEFUL | old pod Terminating 10:51:30.212, still serving until it exited about 3 s later; replacement Ready 10:51:30.863 | 739 requests, 0 failed | 100.0 |
| FORCE | old pod object deleted 10:53:01.843; replacement Ready 10:53:02.348 | 740 requests, 0 failed | 100.0 |

Why no failures:
- **GRACEFUL:** kube-proxy keeps routing to serving-but-terminating endpoints when no ready
  endpoint exists.
- **FORCE:** even with `gracePeriodSeconds=0`, the kubelet enforces a minimum 2 s termination
  grace, so the container keeps serving.
- **Both:** iptables kube-proxy syncs at most once per second.

podinfo is Ready in about 0.5 s, faster than the old container dies, so a pod-delete cannot
open a client-visible gap for this workload.

## Not yet covered

No live abort during `OBSERVING` (`services/safety/live_monitor.py`), and no automatic
cleanup of completed ChaosEngine/ChaosResult objects (kept as evidence).
