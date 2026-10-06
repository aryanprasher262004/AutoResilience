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

## Observed on kind: sandbox pod-delete (`resilience-sandbox/fragile`, 1 replica, 30 s)

**Without a warm-up**, podinfo is Ready in about 0.5 s. Graceful and forced deletes both gave
0/740 client failures, and a score of 100:
- **GRACEFUL:** kube-proxy falls back to serving-but-terminating endpoints.
- **FORCE:** even with `gracePeriodSeconds=0`, the kubelet keeps the container for its minimum
  2 s termination grace. iptables kube-proxy syncs at most once per second.
- **Both:** the replacement is Ready before the old container stops.

**With the modelled 10 s warm-up** (`readinessProbe.initialDelaySeconds: 10`, the current
manifest), the outage is real:

| | GRACEFUL | FORCE |
|---|---|---|
| Replacement created → Ready | 10:58:59 → 10:59:10 (11 s) | 11:05:36 → 11:05:46 (10 s) |
| Client | 19/826 failed (13 connection errors, 6 timeouts) | 22/668 failed (14 connection errors, 8 timeouts) |
| Kubernetes min available (15 s samples) | 0/1, the dip was caught by a scrape | 1/1, the 10 s gap fell between scrapes |
| v2 score | 71.2 (Fair) | 80.5 (Good) |
| v1 score on the same evidence | 74.7 | 100.0 |

v1, which uses only server and Kubernetes evidence, gives FORCE a perfect score despite 22 real
client failures. The difference between the two v2 scores comes mostly from the sampled
availability component: whether a scrape happened to land inside the gap. That component is
noisy for outages shorter than the scrape interval.

## Not yet covered

No live abort during `OBSERVING` (`services/safety/live_monitor.py`), and no automatic
cleanup of completed ChaosEngine/ChaosResult objects (kept as evidence).
