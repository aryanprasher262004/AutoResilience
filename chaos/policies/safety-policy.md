# Chaos injection safety (Contract)

What AutoResilience guarantees before and during a LitmusChaos fault. Backend policy
values live in `apps/api/app/domain/safety_policy.py`; this is the chaos-side view.

## Before a ChaosEngine is created (`POST /experiments/{id}/inject`)

1. Experiment is in `INJECTING`, i.e. it passed validation (static + cluster checks)
   and has a `CAPTURED` baseline. Any other state returns 409 and touches nothing.
2. Fault type is `pod-delete` (the only supported type; others fail validation).
3. Cluster checks are re-run against live state (workload exists, ready pods,
   ready − affected ≥ `min_healthy_replicas`); a failure → `INJECTION_FAILED`.
4. Target pods = the first `affected_replicas` ready pods by name (deterministic).
5. The provider refuses `SYSTEM_NAMESPACES` (kube-system, kube-public,
   kube-node-lease, litmus, monitoring) independently of validation.
6. The namespace must already contain the vetted `pod-delete` ChaosExperiment
   (`chaos/templates/pod-delete.yaml`) and the `autoresilience-chaos` ServiceAccount
   (`chaos/rbac/pod-delete-rbac.yaml`); otherwise `INJECTION_FAILED`.

## The ChaosEngine

Built only from typed fields (no user YAML): `appinfo` = validated namespace, workload
selector and kind; `TARGET_PODS` = the chosen pods; `TOTAL_CHAOS_DURATION` =
`CHAOS_INTERVAL` = `duration_seconds` (exactly one deletion round); `FORCE=false`
(graceful delete). Named `ar-<experiment id>`, labelled
`app.kubernetes.io/managed-by=autoresilience`. Runs as `autoresilience-chaos`, whose
Role only allows deleting pods in its own namespace.

## After creation

`OBSERVING` is entered only when Litmus reports the experiment `Running`/`Completed`
**and** the target pods are gone or terminating. If Litmus reports failure, the
pods are not deleted within `CHAOS_START_TIMEOUT_SECONDS`, or status cannot be read,
the engine is stopped (`engineState: stop`) and the experiment is `INJECTION_FAILED`.
The engine name, target pods and last Litmus status are persisted in `experiments.chaos`.

## Not yet covered

No live abort during `OBSERVING` (`services/safety/live_monitor.py`), and no automatic
cleanup of completed ChaosEngine/ChaosResult objects (kept as evidence).
