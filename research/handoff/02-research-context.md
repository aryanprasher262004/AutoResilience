# 02 · Research Context

| | |
|---|---|
| **Purpose** | Define the research motivation, gap, questions, objectives, hypotheses and expected contributions, constrained to what the implementation can actually investigate. |
| **Source of truth** | Implementation (what can be measured); [14-current-evidence](14-current-evidence.md) (what has been observed). No literature has been reviewed. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [25-research-integrity](25-research-integrity.md), [13-experimental-methodology](13-experimental-methodology.md), [16-final-experiment-matrix](16-final-experiment-matrix.md), [23-reference-collection-guide](23-reference-collection-guide.md) |

> **Literature status.** No literature search has been performed for this knowledge base.
> Every statement about the state of the art, a gap or novelty is a **hypothesis about the
> literature** and is marked "Requires literature validation."

---

## 1. Research motivation

| # | Motivation | Type |
|---|---|---|
| M1 | Fault injection on shared clusters needs safety guarantees before and during injection. | Design rationale (D) |
| M2 | Client-perceived impact can differ from what Kubernetes state and server metrics show, especially for outages shorter than the scrape interval. | Observed in development (B1, O-03) |
| M3 | Resilience results should be comparable across runs and explainable per component, with methodology changes kept reproducible. | Design rationale (D); implemented as versioned scoring (C) |
| M4 | Uncertain outcomes (platform failures, missing data, conflicting evidence) should be reported as such, not silently counted as success or failure. | Design rationale (D); implemented as UNKNOWN with cause (C) |

## 2. Research gap (hypothesised)

| Gap statement | Status |
|---|---|
| Existing chaos-engineering tools inject faults and report an experiment verdict, but give limited client-side, evidence-based judgments of recovery quality. | Requires literature validation. |
| Resilience scores, where they exist, are rarely decomposed into explainable components with explicit handling of missing data and uncertainty. | Requires literature validation. |
| Safety in self-service chaos tools is often configuration-based rather than enforced by a policy engine bound to the target namespace plus live cluster checks. | Requires literature validation. |
| Scrape-interval sampling of Kubernetes state systematically under-detects short outages. | Partly supported by B1 observation O-03. The general claim requires literature validation and Level A evidence. |

## 3. Research questions

Each question is answerable with the implemented system and the matrix in
[16](16-final-experiment-matrix.md).

| ID | Research question | Measured by | Experiments |
|---|---|---|---|
| **RQ1** | Can a self-service workflow enforce safety for pod-delete experiments, i.e. block unsafe configurations before any cluster change and constrain injection to the validated blast radius? | Validation outcomes per unsafe scenario; whether any non-target pod was deleted; engine labels and targets | S1, E1–E3 (audit of `chaos.target_pods`) |
| **RQ2** | How does client-observed impact (failed requests, outage duration) compare with Kubernetes-sampled availability and server-side metrics in detecting and quantifying short disruptions? | Client outage seconds and failures vs `min_available_replicas` and server 5xx | E1–E4, C1 |
| **RQ3** | Does the Resilience Score (v3) discriminate between configurations that differ in redundancy, start-up delay and deletion mode, and how do the v1, v2 and v3 methodologies differ on identical evidence? | Score distributions per cell; per-component contributions; recomputed v1/v2 | E1–E4, V1 |
| **RQ4** | Does the orchestrated lifecycle determine outcomes reliably and handle interruptions (abort, API restart, chaos-platform timeout) without duplicate injections or unsafe residue? | Final states, reason codes, engine count per run, cleanup outcome | R1, all blocks |

## 4. Research objectives

| ID | Objective | Linked RQ |
|---|---|---|
| OBJ1 | Design and implement a safety framework combining namespace-bound policies, static checks, live cluster checks and pre-injection re-validation. | RQ1 |
| OBJ2 | Design a multi-source evidence model (Kubernetes, Prometheus server metrics, client load generator, Litmus) for each experiment. | RQ2 |
| OBJ3 | Define an explicit recovery rule with an uncertainty outcome (UNKNOWN with cause). | RQ4, RQ3 |
| OBJ4 | Define an explainable, versioned Resilience Score and evaluate its behaviour. | RQ3 |
| OBJ5 | Automate the lifecycle in a restart-safe orchestrator and expose it through a self-service console. | RQ4 |
| OBJ6 | Evaluate the system empirically on a controlled Kubernetes environment. | RQ1–RQ4 |

OBJ1–OBJ5 are implemented (Level C). OBJ6 is **not yet done** (Level A missing).

## 5. Hypotheses

Hypotheses are stated so that the matrix can confirm or refute them. The "prior" column
records existing B-level observations, which are **not** evidence for the hypothesis.

| ID | Hypothesis | Prior (non-confirmatory) | Test |
|---|---|---|---|
| H1 | Every unsafe configuration in S1 is blocked at validation, with no cluster mutation, and no experiment deletes pods outside its validated `target_pods`. | Implementation and tests (C) only; no retained or documented real-run evidence of a block | S1; audit of E1–E3 engines |
| H2a | For a single-replica workload with a readiness delay, the client observes a continuous outage whose duration approximately equals the readiness delay. | B1: 7.2–10.6 s outages with a 10 s delay (n = 15) | E1, E4 |
| H2b | With ≥ 2 replicas, a single pod deletion produces no client-visible outage. | B1 n = 3, B2 n = 2 | E2, E3 |
| H2c | 15 s availability sampling detects a sub-scrape-interval outage with probability ≈ outage/15 s, while client counters detect all of them. | B1: 9/17 vs 17/17 | E1, E4, C1 |
| H3a | v3 scores decrease monotonically with readiness delay. | none | E4 |
| H3b | v3 ranks single-replica configurations below multi-replica ones. | B1/B2 point values only | E1 vs E2 |
| H3c | v1 rates single-replica FORCE deletions higher than v3 does (v1 cannot see client impact). | B2: one run, v1 100.0 vs v3 76.8 | V1 |
| H4 | Abort, API restart and Litmus timeout end in ABORTED, COMPLETED (resumed) and UNKNOWN/NOT_SCORED respectively, each with exactly one ChaosEngine and successful cleanup. | B2: documented orchestration runs | R1 |

## 6. Expected contributions

Phrase these conservatively. All novelty "Requires literature validation."

| # | Contribution | Evidence needed | Status |
|---|---|---|---|
| C1 | A safety-gated, self-service chaos experiment workflow for Kubernetes (namespace-bound policies, static + live checks, re-validation, owned-resource cleanup). | Level C now; Level A from S1 and R1 | Implemented |
| C2 | A multi-source evidence model including exact client-side outage measurement independent of scrape intervals. | Level C now; Level A from E1–E4 and C1 | Implemented |
| C3 | An explicit recovery rule with an uncertainty outcome distinguishing platform, application and conflicting-evidence causes. | Level C now; Level A from R1 | Implemented |
| C4 | An explainable, versioned Resilience Score (v3) with documented evolution from v1 and v2 and re-computation on identical evidence. | Level C now; Level A from V1 and E4 | Implemented |
| C5 | An empirical evaluation on a controlled Kubernetes environment. | Level A | **Not yet done** |
| C6 | An open-source implementation. | Licence and repository publication | Not verified from implementation (no LICENSE file in the repository) |

---

## Related documents
[13-experimental-methodology](13-experimental-methodology.md) · [16-final-experiment-matrix](16-final-experiment-matrix.md) · [19-discussion-framework](19-discussion-framework.md) · [23-reference-collection-guide](23-reference-collection-guide.md) · [25-research-integrity](25-research-integrity.md)

## Missing information
- A literature review; any related-work comparison.
- Supervisor- or venue-specific research questions.

## Open questions
- Is RQ4 (engineering robustness) in scope for a research paper, or only for the dissertation? Recommended: dissertation, and a short paper subsection.
- Should the score be framed as a contribution in its own right, or as an instrument whose validity is itself evaluated (RQ3)? Recommended: an instrument with stated limitations.
