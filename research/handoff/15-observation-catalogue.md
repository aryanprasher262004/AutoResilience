# 15 · Observation Catalogue

| | |
|---|---|
| **Purpose** | One numbered entry per finding, with its evidence, level, importance, related research question, supporting data, potential figure and the validation still required. |
| **Source of truth** | `research/experiment-results.json` / `.csv`, committed docs, implementation. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [14-current-evidence](14-current-evidence.md), [25-research-integrity](25-research-integrity.md), [02-research-context](02-research-context.md) (RQs), [16-final-experiment-matrix](16-final-experiment-matrix.md) |

Every observation here is **pre-experimental** (Level B or C). None is a Level A result. In a
paper, they may motivate design decisions and hypotheses; they must not be presented as
evaluation results.

---

## Index

| ID | Short title | Level | RQ | Importance |
|---|---|---|---|---|
| O-01 | A single replica with a 10 s readiness delay gives a ~8 s continuous client outage per deletion | B1 | RQ2, RQ3 | High |
| O-02 | The client outage instrument is internally consistent and matches documented runs | B1 | RQ2 | High (instrument validity) |
| O-03 | 15 s availability sampling detected only about half of the outages | B1 | RQ2 | **Very high** |
| O-04 | Without a readiness delay, a single-replica deletion was invisible to clients | B1/B2 | RQ2 | Medium |
| O-05 | With 2 replicas, a single deletion caused no client-visible failures | B1/B2 | RQ2, RQ3 | High |
| O-06 | GRACEFUL vs FORCE: inconclusive | B1 | RQ3 | Medium |
| O-07 | v1, v2 and v3 disagree on identical evidence; v2 ordering depended on scrape timing | B2 | RQ3 | **Very high** |
| O-08 | Server-side metrics alone missed all client-visible failures | B2 | RQ2 | High |
| O-09 | Back-to-back runs contaminate the baseline | B1 | RQ3 (validity) | High (methodological) |
| O-10 | The Litmus verdict was always Pass and carries no target information without probes | B1 + C | RQ3 | Medium |
| O-11 | Litmus start-up adds ~13–14 s between engine creation and deletion | B1 | RQ4 | Low–medium |
| O-12 | TTR is dominated by the readiness configuration (10–11 s vs 0–1 s) | B1 | RQ2, RQ3 | Medium |
| O-13 | Cleanup never touched engines unknown to the database | B1 + C | RQ1, RQ4 | Medium |
| O-14 | An orchestrated 30 s fault took ~101 s to complete | B2 + C | RQ4 | Low |
| O-15 | The safety logic is verified by tests; no retained real-run evidence of a block | C | RQ1 | High (gap) |
| O-16 | Development records were lost: the evidence pipeline lacked persistence and export discipline | Process | all | High (integrity) |

---

### O-01 · Single replica with a 10 s readiness delay → ~8 s continuous client outage per deletion

| | |
|---|---|
| **Observation** | For `resilience-sandbox/fragile` (1 replica, `initialDelaySeconds: 10`), every observed pod replacement coincided with one continuous client outage and ~20 failed requests. |
| **Evidence** | n = 17 replacements. TTR 10–11 s (median 10). Client failures 18–24 (median 20; mostly connection errors, then timeouts). Client outage, n = 15 instrumented: 7.239–10.565 s, median 8.358 s, mean 8.43 s, sd 1.03 s; pattern CONTINUOUS in all 15. Records `LIT-d406ca22`, `LIT-4a44f687`, `LIT-66d86b9a`, `LIT-7ea2e0f7`, `TEL-fragile-*`. |
| **Level** | B1 (post-hoc telemetry; modes mostly unknown) |
| **Importance** | Establishes that the sandbox produces a reproducible, measurable client-visible outage, a prerequisite for evaluating the score. |
| **Related RQ** | RQ2, RQ3 |
| **Supporting experiments (future)** | E1, E4 |
| **Potential figure** | F-12 (outage distribution), F-09 (timeline) |
| **Future validation** | Confirm with complete records, 10 per mode (E1); vary the delay (E4) to test H2a (outage ≈ delay). |

### O-02 · The client outage instrument is internally consistent

| | |
|---|---|
| **Observation** | Outage durations from the client's own start and end timestamps equal the outage-seconds counter increase in every episode. Re-derived failure counts and outage windows match the committed documentation for every documented run. |
| **Evidence** | 15/15 episodes: gauge duration = counter increase (to the millisecond). Documented runs: `66d86b9a` 8.358 s and 20 failures (13 conn, 7 timeouts); `7ea2e0f7` 10.479 s and 23 failures (15/8); `d406ca22` 19 failures (13/6); `4a44f687` 22 (14/8). All match. |
| **Level** | B1 |
| **Importance** | Supports the reliability of the v3 input; it is not an accuracy claim, since both measures come from the same client. |
| **Related RQ** | RQ2 |
| **Potential figure** | — (a table row in T-12) |
| **Future validation** | C1 calibration against an independent ground truth (controlled scale-to-zero durations). |

### O-03 · 15 s availability sampling detected only about half of the outages

| | |
|---|---|
| **Observation** | Kubernetes-sampled availability (`kube_deployment_status_replicas_available`, 15 s scrapes) dropped to 0 in only 9 of 17 fragile disruptions. The client recorded failures in 17/17 and an outage in all 15 instrumented runs. |
| **Evidence** | `k8s_sampled_min_available` column in `research/experiment-results.csv` (fragile with warm-up rows). Detection 9/17 = 53%. The naive expectation ≈ outage/scrape interval ≈ 8.4/15 ≈ 56% (inference). |
| **Level** | B1 |
| **Importance** | The core empirical motivation for client-side measurement and for score v3 (sampled availability is a coin flip for sub-scrape outages). |
| **Related RQ** | RQ2 |
| **Potential figure** | F-13 (sampling illustration), F-14 (detection-rate bar) |
| **Future validation** | E1 + E4 with complete records; report the proportion with a Wilson CI; relate it to outage duration. |

### O-04 · Without a readiness delay, single-replica deletion was invisible to clients

| | |
|---|---|
| **Observation** | Before the warm-up was modelled (pod template `844c559bb8`), fragile replacements were Ready in 0–1 s and clients saw 0 failures, in both GRACEFUL and FORCE. |
| **Evidence** | `LIT-9d95d794` (GRACEFUL: TTR 0, 0 failures), `LIT-e89d2585` (FORCE: TTR 1, 0 failures), B1. The doc states "0/740 client failures, and a score of 100" for both (B2, `chaos/policies/safety-policy.md`), with explanations: kube-proxy serving-terminating endpoints; the 2 s kubelet minimum termination; the replacement Ready before the old container stops. |
| **Level** | B1 (telemetry) + B2 (explanation) |
| **Importance** | Shows that client impact depends on start-up behaviour, not merely on replica count. This motivates factor E4. |
| **Related RQ** | RQ2 |
| **Future validation** | E4 level 0 s. |

### O-05 · With 2 replicas, a single deletion caused no client-visible failures

| | |
|---|---|
| **Observation** | For `shop/checkout` (2 replicas), single-pod replacements gave 0 client failures, no outage (pattern NONE), sampled availability 2/2, and TTR 1 s. |
| **Evidence** | B1: `TEL-checkout-121906`, `-150501`, `-153911`. B2: `DOC-v2-checkout-graceful` (740 requests, 0 failed) and `DOC-v2-checkout-force` (739 requests, 0 failed); v2 100.0 for both modes. |
| **Level** | B1 + B2 |
| **Importance** | The redundancy contrast with O-01; the basis of H2b. |
| **Related RQ** | RQ2, RQ3 |
| **Potential figure** | F-12 (side by side with fragile) |
| **Future validation** | E2 (checkout), E3 (frontend, 3 replicas). |

### O-06 · GRACEFUL vs FORCE: inconclusive

| | |
|---|---|
| **Observation** | In the only pair with outage data, FORCE had the longer outage (10.479 s vs 8.358 s) and more failures (23 vs 20). Two unattributed episodes are also ~10.5 s (11:26Z identified FORCE; 15:06Z unknown mode). |
| **Evidence** | `LIT-66d86b9a`, `LIT-7ea2e0f7`; `TEL-fragile-150641`. |
| **Level** | B1, n = 1 per mode |
| **Importance** | Do **not** claim a mode effect. The doc offers a mechanism (B2): with FORCE the container kept serving ~1 s after the object was deleted. |
| **Related RQ** | RQ3 |
| **Future validation** | E1 with 10 repetitions per mode and interleaved order. |

### O-07 · v1, v2 and v3 disagree on identical evidence

| | |
|---|---|
| **Observation** | The same two runs scored very differently across methodologies, and v2 reversed their ordering because of scrape timing. |
| **Evidence** | GRACEFUL `66d86b9a`: v1 74.7, v2 67.2, v3 80.4. FORCE `7ea2e0f7`: v1 100.0, v2 79.2, v3 76.8. v2's availability component was 0/15 vs 15/15, depending only on whether a scrape landed inside the outage (sampled 0/1 vs 1/1). All six numbers reproduce exactly from the documented inputs with the implemented formulas ([09](09-scoring-methodology.md) §8). |
| **Level** | B2 (documented scores), reconstruction consistent (C) |
| **Importance** | Central design-science argument for v3: a score must not depend on sampling phase. |
| **Related RQ** | RQ3 |
| **Potential figure** | F-15 (per-version stacked components for the two runs) |
| **Future validation** | V1 over all E-block runs: the rank correlation between versions, and the variance attributable to the availability component. |

### O-08 · Server-side metrics alone missed all client-visible failures

| | |
|---|---|
| **Observation** | v1 (server 5xx and K8s evidence) gave the FORCE fragile run 100.0, although the client saw 22–23 failed requests. |
| **Evidence** | `LIT-4a44f687`: v1 100.0 with 22 client failures (`chaos/policies/safety-policy.md`); `LIT-7ea2e0f7`: v1 100.0 with 23 failures. Explanation (B2, `resilience-score-v2.md`): refused or reset connections during termination never reach server metrics. |
| **Level** | B2 |
| **Related RQ** | RQ2 |
| **Future validation** | V1: count runs where v1 = 100 but client failures > 0. |

### O-09 · Back-to-back runs contaminate the baseline

| | |
|---|---|
| **Observation** | When runs were less than 300 s apart, the next run's 300 s baseline window already contained the previous outage. Score v3 subtracts `expected = baseline_outage/300 · W`, so contamination inflates v3. |
| **Evidence** | 7 of 13 unattributed fragile runs had a pre-fault outage of 7.257–18.911 s in their 300 s window (`prefault_baseline_outage_s_300s`). |
| **Level** | B1 (telemetry) + C (formula) |
| **Importance** | A methodological threat for the campaign; it motivates the spacing rule in [13](13-experimental-methodology.md). It is a possible v4 consideration. |
| **Related RQ** | RQ3 (validity) |
| **Future validation** | Control by spacing; optionally a dedicated test of contaminated vs clean baselines. |

### O-10 · The Litmus verdict carries no target information without probes

| | |
|---|---|
| **Observation** | All six surviving ChaosResults show verdict Pass with `probeSuccessPercentage: "100"`, but no probes are defined (`chaos/templates/pod-delete.yaml`; engines built without probes). |
| **Level** | B1 + C |
| **Importance** | The `litmus_verdict` component (10 points) is nearly constant, which weakens discriminative power. Report it as a limitation. |
| **Related RQ** | RQ3 |
| **Future validation** | Configure Litmus probes (future work), or analyse the score without that component. |

### O-11 · Litmus start-up latency

| | |
|---|---|
| **Observation** | Engine creation → replacement pod creation = 13–14 s in all six identified runs. |
| **Level** | B1 |
| **Importance** | Explains why the observation window contains a quiet pre-deletion phase. TTR is unaffected by definition. |
| **Related RQ** | RQ4 |

### O-12 · TTR is dominated by readiness configuration

| | |
|---|---|
| **Observation** | TTR 10–11 s for fragile with a 10 s delay; 0–1 s without the delay; 1 s for checkout. |
| **Level** | B1 |
| **Importance** | The recovery-time component mostly measures start-up readiness. That is expected, and it should be stated in the paper. |
| **Related RQ** | RQ2, RQ3 |
| **Future validation** | E4. |

### O-13 · Cleanup never touched engines unknown to the database

| | |
|---|---|
| **Observation** | Six engines whose database records were lost remain in the cluster. The orchestrator only cleans up engines of experiments it knows, after verifying their labels. |
| **Level** | B1 + C (`delete_owned`, `_needs_work`) |
| **Importance** | Supports the ownership-safety claim; also shows the operational cost (orphans need manual cleanup). |
| **Related RQ** | RQ1, RQ4 |

### O-14 · Decision latency

| | |
|---|---|
| **Observation** | One documented automatic sandbox run (30 s fault) reached COMPLETED in 101 s. This is consistent with the timing analysis: Litmus start ~14 s + 30 s duration + ~45–60 s of stability sampling (inference). |
| **Level** | B2 + C |
| **Related RQ** | RQ4 |
| **Future validation** | The decision-latency metric across all E-block runs. |

### O-15 · Safety logic verified by tests only

| | |
|---|---|
| **Observation** | Blocking of system namespaces, policy confinement, policy-change refusal and cluster re-checks are covered by tests. No retained record or committed document preserves a real blocked run. |
| **Level** | C |
| **Importance** | RQ1 currently rests on implementation verification alone. |
| **Future validation** | S1. |

### O-16 · Development records were lost

| | |
|---|---|
| **Observation** | No AutoResilience experiment record from development survives. The verification workflow used temporary databases and did not export results. |
| **Level** | Process observation |
| **Importance** | Integrity; motivates the data-management rules in [13](13-experimental-methodology.md) §8 and `scripts/dev-db.sh`. |

---

## Related documents
[14-current-evidence](14-current-evidence.md) · [16-final-experiment-matrix](16-final-experiment-matrix.md) · [17-required-figures](17-required-figures.md) · [19-discussion-framework](19-discussion-framework.md) · [25-research-integrity](25-research-integrity.md)

## Missing information
- Mode attribution for unattributed runs (affects O-06).
- Ground-truth calibration (affects O-02).

## Open questions
- Should O-03 be framed as a general claim about scrape-based monitoring? Only after E-block replication and literature validation.
