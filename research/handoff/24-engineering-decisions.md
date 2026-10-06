# 24 · Engineering Decisions

| | |
|---|---|
| **Purpose** | Record every major architectural decision: decision, alternatives, rationale, trade-offs and future implications. |
| **Source of truth** | Code at `92e33dd`; decision sections in `docs/orchestration.md`, `docs/history-and-reports.md`, `docs/services.md`, `docs/readiness.md`, `docs/ci.md`, `docs/scoring/*.md`, `chaos/policies/safety-policy.md`; commit history. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [03-system-architecture](03-system-architecture.md), [06-safety-framework](06-safety-framework.md), [09-scoring-methodology](09-scoring-methodology.md) |

**"Why chosen" sources.**
- Taken from the repository's own documentation or code comments where available, cited.
- Marked *(rationale not documented)* where the repository states no reason. In that case the reason given is an engineering inference, not a recorded decision.

---

| # | Decision | Alternatives | Why chosen | Trade-offs | Future implications |
|---|---|---|---|---|---|
| D-01 | **In-process reconciler thread** driving auto experiments from persisted state | Task queue (Celery, RQ); a Kubernetes operator; client-driven polling | `docs/orchestration.md`: no task queue; all progress in PostgreSQL, so it is stateless and restart-safe | Simple and restart-safe; but single-process only (in-memory locks) | Multi-replica needs DB row locks (`FOR UPDATE SKIP LOCKED`) |
| D-02 | **Deterministic engine name `ar-<id>`**; on conflict, stop and fail | Random names; adopt the existing engine | `docs/orchestration.md`: "A run is never executed twice" | Sacrifices the interrupted run, for safety | Keep it as an invariant for new fault types |
| D-03 | **Safety policies in code, selected only by namespace** | Policies in the DB or a CRD; chosen per request | `chaos/policies/safety-policy.md`: no API field can choose or alter a policy; code review is the change process | Strong auditability; no runtime flexibility | A persisted policy model would need review and approval workflows (placeholder exists) |
| D-04 | **Sandbox namespace with its own policy** (min healthy 0, allowlisted) | Lower the default policy; disable checks for tests | Reproduce client-visible outages without weakening the default (`sandbox.yaml`, safety doc) | Experiments on single replicas confined to one namespace | Pattern for other "unsafe by design" test zones |
| D-05 | **Re-validate at injection** (same policy, live cluster check) | Trust the validation result | `safety-policy.md` §"Before a ChaosEngine is created" | Extra API calls; may fail late | Required for any delayed execution (scheduling) |
| D-06 | **Read-only Kubernetes adapter; single writer = chaos provider** | A general Kubernetes client used everywhere | `kubernetes_adapter.py` docstring; tests assert read-only | Clear audit boundary; enforced in code, not RBAC | A least-privilege API identity would make it enforceable |
| D-07 | **Client load generator as a first-class evidence source** | Server metrics only; synthetic HTTP probes outside the cluster | `resilience-score-v2.md`: server metrics and scrapes miss client-visible failures | An extra component per target; one vantage point | More clients, real traffic replay |
| D-08 | **Exact counter differences from raw samples** (no `rate()`/`increase()` extrapolation) | PromQL `increase()` | `recovery.py` docstrings: exact counts; scrape gaps lose no failures | Custom logic; must handle resets | Reusable for other counters |
| D-09 | **Outage duration measured by the client** (v3) | Sampled availability | `resilience-score-v3.md`: sampled availability depended on scrape timing | Depends on load-generator correctness (C1 needed) | The basis for future SLO-based scoring |
| D-10 | **Recovery from pod timestamps + stable streak**, not client success | Client-success-based recovery | *(rationale not documented)*. Inference: a Kubernetes-level, client-independent definition that works for targets without clients | Can declare COMPLETED while client impact is still analysed separately | An optional client criterion is possible ([21](21-future-work.md)) |
| D-11 | **UNKNOWN with cause; platform UNKNOWN never scored** | Treat timeouts as failure (score 0) | `score_experiment` explanation: platform or conflicting evidence "says nothing reliable about the target's resilience" | Fewer scored runs | The UNKNOWN taxonomy can extend |
| D-12 | **Versioned, pure, explainable score; never change a version's semantics** | One mutable formula; ML-based scoring | `CLAUDE.md` rule; scoring docs | Multiple versions to maintain; recomputation possible | v4 for baseline-contamination handling |
| D-13 | **Weight re-normalization over applicable components** | Treat missing as 0 or as 1 | Scoring docs (NOT_APPLICABLE re-normalization) | Scores across targets with different evidence are less comparable | Report the applicable components with each score |
| D-14 | **One `experiments` table with JSON evidence columns** | Normalised evidence tables | *(rationale not documented)*. Inference: evidence shapes evolved quickly across milestones; JSON avoided migrations per field | Weak schema enforcement for evidence; SQL analytics need JSON paths | Normalise if analytics grow |
| D-15 | **Console reaches the API through a Next.js rewrite** (`/api/backend/*`) | CORS; a separate gateway | `apps/web/README.md`: no CORS setup needed | The target is baked in at build time | Configure at deploy time |
| D-16 | **Generated API types from OpenAPI with a CI drift check** | Hand-written types | `scripts/gen-api-contracts.sh`, `docs/ci.md` | Regeneration step for every API change | Contract-first evolution |
| D-17 | **Runtime-checked evidence readers in the UI; "No data" instead of guesses** | Trust the JSON shapes | `CLAUDE.md` (evidence readers rule) | More UI code | Safe evolution of evidence JSON |
| D-18 | **Server-side aggregation for history, dashboard and services** | Client-side aggregation | `docs/history-and-reports.md` "Decision: aggregate on the server" | API surface grows | Same numbers in all clients |
| D-19 | **Dashboard statistics on the current score version only** | Mix versions | `docs/history-and-reports.md`: never mix methodologies | Older runs excluded from averages | Re-score older runs explicitly if needed |
| D-20 | **`/health` (no I/O) vs `/ready` (DB + migration head)** | A single health endpoint | `docs/readiness.md` | Two endpoints to understand | Add dependencies to readiness deliberately |
| D-21 | **DB failures mapped to 503 with the cause** | Generic 500 | Commit `730ea81`: the opaque 500 hid an unprovisioned DB | — | Consistent error contract |
| D-22 | **Persistent Docker PostgreSQL for development** (`dev-db.sh`) | Ad hoc databases | `730ea81` | — | Prevents evidence loss (O-16) |
| D-23 | **Exactly one deletion round per experiment** (`CHAOS_INTERVAL = TOTAL_CHAOS_DURATION`) | Periodic deletions within the duration | `build_pod_delete_engine` docstring: "blast radius is the validated affected_replicas" | Duration mostly extends the observation | Periodic faults would need new safety analysis |
| D-24 | **Deterministic target choice: the first N ready pods by name** | Random, or Litmus `PODS_AFFECTED_PERC` | `injection._prepare` comment | Always hits the same pod name order | Randomisation could be an experiment factor |
| D-25 | **Load generator uses a new connection per request** | Keep-alive | `loadgen.py` docstring: each request load-balanced like an independent client | More connection overhead | Matches per-request routing semantics |
| D-26 | **Sample workloads and a modelled warm-up** | Realistic applications | `sandbox.yaml` comment; `a0482fa` | Limits external validity | Benchmark applications in future work |
| D-27 | **CI without a cluster**; only migrations need a service container | Run kind in CI | `docs/ci.md` "Decision: what CI does not need" | No end-to-end CI | Optional nightly kind job |

---

## Related documents
[03-system-architecture](03-system-architecture.md) · [06-safety-framework](06-safety-framework.md) · [09-scoring-methodology](09-scoring-methodology.md) · [21-future-work](21-future-work.md)

## Missing information
- Rationale for D-10 and D-14 is not documented in the repository.

## Open questions
- Should D-10 be revisited (client-aware recovery) as part of a v4 methodology?
