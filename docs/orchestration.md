# Experiment orchestration

Implementation: `apps/api/app/services/orchestration/orchestrator.py`.

## Concept

One call starts a run, and AutoResilience drives the whole lifecycle itself:

```
POST /experiments            -> CREATED
POST /experiments/{id}/run   -> marks it orchestration.mode = "auto"
   (reconciler)  VALIDATING -> BASELINING -> INJECTING -> OBSERVING -> RECOVERING
                 -> COMPLETED | UNKNOWN | VALIDATION_FAILED | INJECTION_FAILED | ABORTED
   (reconciler)  cleanup of the run's own ChaosEngine + ChaosResult
GET  /experiments/{id}       -> follow state, orchestration.events, score
POST /experiments/{id}/abort -> {"reason": "..."}: stop its own engine, ABORTED
```

The manual step endpoints (`/validate`, `/baseline`, `/inject`, `/observe`) still work for
experiments that were not started with `/run`. For auto runs they return 409.

## Decision: an in-process reconciler

A background thread started by the FastAPI lifespan calls `Reconciler.tick()` every
`ORCHESTRATOR_INTERVAL_SECONDS` (5 s). Each tick:
- loads auto experiments that are not finished, plus finished experiments whose ChaosEngine
  has not been cleaned up;
- advances each one bounded step, using the existing lifecycle functions unchanged (same
  safety checks, same evidence, same scoring).

No task queue is used. All progress lives in Postgres, so the reconciler is stateless and
**restart-safe**: after an API restart the next tick continues from the persisted state.
- `VALIDATING` resumes through `complete_validation`.
- `INJECTING` with a recorded engine resumes polling and never creates a second engine.
- `OBSERVING` and `RECOVERING` continue from their persisted deadlines.

A failing step is recorded in `orchestration.last_error` and retried; it does not block other
experiments.

**Assumption:** a single API process. Per-experiment locks serialize the reconciler with
`/run` and `/abort`. Running several API replicas would need a database lock instead
(e.g. `SELECT … FOR UPDATE SKIP LOCKED`).

## No duplicate chaos runs

Injection is split into `start_injection` (create the engine, persist its identity) and
`advance_injection` (one poll). The engine name is deterministic: `ar-<experiment id>`.

If the API dies after creating the engine but before committing, the retry gets
**AlreadyExists**. The experiment is then marked `INJECTION_FAILED` and that engine is stopped.
A run is never executed twice.

## Timeouts

| State | Deadline | Outcome |
|---|---|---|
| BASELINING | `BASELINE_TIMEOUT_SECONDS` (180) without a captured baseline | UNKNOWN, `BASELINE_TIMEOUT`, cause platform |
| INJECTING | `CHAOS_START_TIMEOUT_SECONDS` (120) after engine creation | INJECTION_FAILED, engine stopped |
| OBSERVING | duration + `OBSERVATION_GRACE_SECONDS` | UNKNOWN, `LITMUS_TIMEOUT`, engine stopped |
| RECOVERING | `RECOVERY_TIMEOUT_SECONDS` after Litmus finished | UNKNOWN (application or platform cause) |
| any active state | `ORCHESTRATION_MAX_SECONDS` (1800) after `/run` | UNKNOWN, `ORCHESTRATION_TIMEOUT` (ABORTED if still before baseline), engine stopped |

Platform uncertainty always ends in UNKNOWN, never COMPLETED.

## Abort

`POST /experiments/{id}/abort` with a reason (1–500 characters) works in any active state:
1. If an engine was created, it patches **that** engine (from `experiments.chaos`) to
   `engineState: stop`.
2. It records `orchestration.abort` with the reason, the time, and which engine was stopped
   or the stop error.
3. It transitions to `ABORTED`. Finished experiments return 409.

If the stop fails, the experiment is still ABORTED and cleanup keeps trying to delete the
engine.

## Cleanup (Runbook)

For every finished experiment with a recorded engine:
1. Wait until Litmus reports the engine `completed` or `stopped`, or until
   `CLEANUP_GRACE_SECONDS` (120) has passed.
2. Call `delete_owned(namespace, ar-<id>, id)`. It refuses system namespaces and any name
   other than `ar-<id>`.
3. It re-reads the engine and requires the labels `app.kubernetes.io/managed-by=autoresilience`
   and `autoresilience.io/experiment-id=<id>`.
4. It deletes that engine and `ar-<id>-pod-delete` (the ChaosResult). Objects already absent
   count as done.

The outcome is in `orchestration.cleanup`, and failures are retried on the next tick.
ChaosEngines unknown to the database (e.g. from deleted dev databases) are never touched.
The Litmus verdict and ChaosResult status were already persisted in `experiments.observation`
before deletion.

## Verified on kind (`resilience-sandbox/fragile`)

| Run | What happened |
|---|---|
| Automatic | `/run` only (no `/observe` calls): COMPLETED in 101 s, score v3 85.8; engine and result deleted |
| Restart | API killed in OBSERVING (1 engine), restarted 26 s later: resumed → COMPLETED, still one engine, then cleaned up |
| Abort | aborted in OBSERVING: own engine `engineState=stop` → Litmus `stopped / Forcefully Aborted`, then deleted |
| Unrelated | 6 pre-existing ChaosEngines not in the database and all shop/sandbox workloads were untouched throughout |
