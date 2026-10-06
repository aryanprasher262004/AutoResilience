# 14 · Current Evidence

| | |
|---|---|
| **Purpose** | An inventory of **all** evidence that exists today, separated into controlled experiments, development runs, automated tests and implementation verification, with evidence level, source, confidence and gaps. |
| **Source of truth** | `research/experiment-results.json` and `.csv` (extracted 2026-10-06/07, read-only); `research/evidence-audit.md`; committed docs; test suites. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [25-research-integrity](25-research-integrity.md) (levels), [15-observation-catalogue](15-observation-catalogue.md) (findings), [appendix/experiment-json-schema](appendix/experiment-json-schema.md) |

Use **only** the numbers in this file and in `research/experiment-results.*`. Do not take
numbers from development chat logs.

---

## 1. Summary

| Category | Count | Level | Usable for |
|---|---|---|---|
| Controlled experiments (complete AutoResilience records) | **0** | A | — |
| Development runs identified by surviving ChaosEngines | 6 | B1 | motivation, preliminary observations |
| Real disruptions in retained telemetry, unattributed | 16 (13 fragile, 3 checkout) | B1 | motivation, preliminary observations |
| Development runs documented only in committed docs | 6 | B2 | motivation (with caveat) |
| Manual infrastructure probe | 1 | B2 | instrument sensitivity (anecdotal) |
| Automated tests | 431 backend + 39 frontend | C | correctness claims |
| Implementation verification (code reading, CI config, mutation checks) | — | C | system description |

## 2. Controlled experiments (Level A)

**None.** The AutoResilience database (`localhost:5432/autoresilience`, revision
`08697f19aec0`) contained 0 experiments at the audit. All development-verification runs were
stored in temporary databases deleted during cleanup ([25](25-research-integrity.md) §7).

## 3. Development runs identified by ChaosEngines (Level B1)

**Source.**
- Six `ChaosEngine`/`ChaosResult` objects in `resilience-sandbox`, labelled `app.kubernetes.io/managed-by=autoresilience` with `autoresilience.io/experiment-id`; read with `kubectl get`.
- Recovery and client values re-derived from raw Prometheus samples.
- Scores copied from committed docs.

All six target `resilience-sandbox/fragile`, Deployment, 1 replica: pod-delete, 30 s, 1
affected replica, Litmus `Completed`/`Pass`.

| Record | Engine created (UTC) | Mode | Pod template | TTR (s) | Client failures (conn/timeout) | Client outage (s) | Sampled min avail. | Documented scores | Code (before commit) |
|---|---|---|---|---|---|---|---|---|---|
| LIT-9d95d794 | 2026-10-06T10:51:16Z | GRACEFUL | no warm-up | 0 | 0 | not instrumented | 1/1 | 100 (version unstated) | `9b6613e` |
| LIT-e89d2585 | 10:52:48Z | FORCE | no warm-up | 1 | 0 | not instrumented | 1/1 | 100 (version unstated) | `9b6613e` |
| LIT-d406ca22 | 10:58:45Z | GRACEFUL | 10 s warm-up | 11 | 19 (13/6) | not instrumented | 0/1 | v2 71.2, v1 74.7 | `a0482fa` |
| LIT-4a44f687 | 11:05:22Z | FORCE | 10 s warm-up | 10 | 22 (14/8) | not instrumented | 1/1 | v2 80.5, v1 100.0 | `a0482fa` |
| LIT-66d86b9a | 11:19:30Z | GRACEFUL | 10 s warm-up | 11 | 20 (13/7) | 8.358 CONTINUOUS | 0/1 | **v3 80.4**, v2 67.2, v1 74.7 | `e1b6923` |
| LIT-7ea2e0f7 | 11:26:07Z | FORCE | 10 s warm-up | 10 | 23 (15/8) | 10.479 CONTINUOUS | 1/1 | **v3 76.8**, v2 79.2, v1 100.0 | `e1b6923` |

- "Not instrumented" means the outage metrics were added at 11:14:57Z (commit `40782d1`).
- "Code (before commit)" means the run used the uncommitted working tree that became that commit.

**Confidence: high for the measured values.**
- Client failure counts and outage windows re-derived from raw telemetry match the committed docs exactly.
- Outage seconds from the gauges equal the counter increase.

**Gaps.**
- Validation results, stored baselines, the system's own observation windows and request totals, final states and full component breakdowns were not retained.
- Final state: inferred COMPLETED for the scored runs (inference: only COMPLETED or application-UNKNOWN runs are scored).

## 4. Unattributed real disruptions (Level B1)

**Source.** Retained raw Prometheus samples (kube-state-metrics pod timestamps; load-generator
counters and gauges), extracted read-only. Each event is a single-pod replacement with an
unchanged pod template, during development-verification windows. Each is consistent with an
AutoResilience pod-delete run, but the **run id, mode, validation, baseline, score and final
state are unknown**.

| Record | Pod created (UTC) | Workload | TTR (s) | Outage (s) | Pattern | Failures | Sampled min | Pre-fault outage in 300 s baseline (s) | Code (before commit) |
|---|---|---|---|---|---|---|---|---|---|
| TEL-fragile-113926 | 11:39:26 | fragile | 10 | 7.239 | CONT | 18 | 0 | 0 | `29d493d` |
| TEL-fragile-114632 | 11:46:32 | fragile | 10 | 8.359 | CONT | 20 | 0 | 0 | `29d493d` |
| TEL-fragile-114824 | 11:48:24 | fragile | 11 | 8.457 | CONT | 21 | 0 | **8.359** | `29d493d` |
| TEL-fragile-120438 | 12:04:38 | fragile | 11 | 8.372 | CONT | 20 | 0 | 0 | `b544e08` |
| TEL-checkout-121906 | 12:19:06 | checkout | 1 | 0.0 | NONE | 0 | 2 | 0 | `30628f0` |
| TEL-fragile-124207 | 12:42:07 | fragile | 11 | 8.359 | CONT | 20 | 1 | 0 | `1306d68` |
| TEL-fragile-124428 | 12:44:28 | fragile | 10 | 8.243 | CONT | 19 | 0 | **8.359** | `1306d68` |
| TEL-fragile-124605 | 12:46:05 | fragile | 10 | 7.353 | CONT | 19 | 1 | **16.602** | `1306d68` |
| TEL-fragile-150501 | 15:05:01 | fragile | 10 | 8.346 | CONT | 20 | 0 | 0 | `45e0014` |
| TEL-checkout-150501 | 15:05:01 | checkout | 1 | 0.0 | NONE | 0 | 2 | 0 | `45e0014` |
| TEL-fragile-150641 | 15:06:41 | fragile | 11 | 10.565 | CONT | 24 | 1 | **8.346** | `45e0014` |
| TEL-fragile-150812 | 15:08:12 | fragile | 10 | 7.359 | CONT | 19 | 1 | **18.911** | `45e0014` |
| TEL-fragile-151243 | 15:12:43 | fragile | 10 | 7.257 | CONT | 18 | 1 | **7.359** | `45e0014` |
| TEL-fragile-151643 | 15:16:43 | fragile | 11 | 9.356 | CONT | 21 | 1 | **7.257** | `45e0014` |
| TEL-fragile-153906 | 15:39:06 | fragile | 11 | 8.353 | CONT | 20 | 0 | 0 | `74d064c` |
| TEL-checkout-153911 | 15:39:11 | checkout | 1 | 0.0 | NONE | 0 | 2 | 0 | `74d064c` |

- "Failures" are counted in a fixed post-hoc window: replacement created − 15 s to Ready + 20 s. Failure counts are robust to this choice; request totals are not.
- All runs after 11:28Z used the committed v3 measurement code (methodology files are unchanged to HEAD).

**Confidence.** High for the telemetry values. **None** for attribution (which experiment,
which mode).

## 5. Documented runs without raw data (Level B2)

| Record | Target | Mode | Documented values | Source |
|---|---|---|---|---|
| DOC-v1-checkout | shop/checkout | GRACEFUL (inferred) | TTR 0 s, min availability 2/2, 163 requests, 0 5xx, 0 restarts, Litmus Pass; v1 100.0 | `docs/scoring/resilience-score-v1.md` |
| DOC-v2-checkout-graceful | shop/checkout | GRACEFUL | 740 requests, 0 failed, p95 4.75 ms; 2/2; replacement 1 s; v1 100, v2 100 | `docs/scoring/resilience-score-v2.md` |
| DOC-v2-checkout-force | shop/checkout | FORCE | 739 requests, 0 failed; pod gone after 5 ms; replacement 1 s; v2 100 | same |
| DOC-orch-auto | fragile | — | `/run` only; COMPLETED in 101 s; v3 85.8 | `docs/orchestration.md` |
| DOC-orch-restart | fragile | — | API killed in OBSERVING, restarted 26 s later; resumed → COMPLETED; one engine | same |
| DOC-orch-abort | fragile | — | aborted in OBSERVING; Litmus stopped/"Forcefully Aborted"; engine deleted | same |
| PROBE-checkout-scale0 | shop/checkout | (manual, not an experiment) | scaled to 0 for ~20 s: 23 connection errors, 17 timeouts | `docs/scoring/resilience-score-v2.md` |

**Confidence: medium.** The values were written by the developer at the time; no raw data
remains. The two DOC-v2 GRACEFUL tables may describe the same run.

## 6. Automated tests (Level C)

| Suite | Count | Environment | What it establishes |
|---|---|---|---|
| Backend pytest (`apps/api/tests`) | 431 | In-memory SQLite; `FakeKubernetes`, `FakePrometheus` (synthetic samples), `FakeChaos` (scripted Litmus statuses), controllable clock | State machine, safety logic, adapter read-only property, baseline, injection guards, recovery rule, client counting, outage pattern, v1/v2/v3 scoring, orchestration (deadlines, restart, abort, cleanup), history, services, readiness, DB error mapping |
| Frontend Vitest (`apps/web/src/**/*.test.tsx`) | 39 | happy-dom; `fetch` stubbed with contract-typed fixtures | Builder (validation display, confirmation, duplicate-submit protection, navigation), readiness indicator, history (filters, URL state, paging), live room (all state families, polling stops, NOT_SCORED, abort) |
| Mutation check (frontend) | 9 mutations | local | Each of 9 deliberately broken behaviours was caught |

Test fixtures (e.g. score 83.6 in `apps/web/src/test/fixtures.ts`, the `FakePrometheus` series)
are **synthetic** and must never be reported as observations.

## 7. Implementation verification (Level C)

| Item | Status |
|---|---|
| Code reading for this knowledge base | done at `92e33dd` |
| Methodology stability (scoring, observation, recovery, baseline, manifests) | unchanged from `e1b6923` (v3) to HEAD (`git diff`) |
| CI workflow | validated with actionlint; all job commands executed locally on a fresh clone; **not yet run on GitHub** |
| Contract determinism | regenerated twice, identical |

## 8. Evidence gaps (what Level A must supply)

| Gap | Matrix block |
|---|---|
| Any complete record with validation, baseline, observation, recovery and score | all |
| Mode effect with n ≥ 10 per mode | E1 |
| Redundancy effect (2 and 3 replicas) with complete records | E2, E3 |
| Score sensitivity to start-up delay | E4 |
| Safety blocking, systematically | S1 |
| Robustness outcomes | R1 |
| Instrument calibration | C1 |
| v1/v2/v3 comparison on identical stored evidence, systematically | V1 |

---

## Related documents
[15-observation-catalogue](15-observation-catalogue.md) · [16-final-experiment-matrix](16-final-experiment-matrix.md) · [25-research-integrity](25-research-integrity.md) · `research/evidence-audit.md` · `research/experiment-results.json`

## Missing information
- Mode and identity of the 16 unattributed disruptions.
- Complete records of every development run.
- Prometheus telemetry will expire around 2026-10-08T11:14Z. The extracted values are preserved in `research/experiment-results.json`.

## Open questions
- Should B1 values appear in the paper as a "preliminary study" table? Recommended: only in the motivation or design-rationale section, with the level stated.
