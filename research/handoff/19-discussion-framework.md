# 19 · Discussion Framework

| | |
|---|---|
| **Purpose** | For each research question: the evidence, observations, figures and tables that address it; expected conclusions; and possible interpretations, including alternative and negative ones. |
| **Source of truth** | [02](02-research-context.md) (RQs and hypotheses), [15](15-observation-catalogue.md) (observations), [16](16-final-experiment-matrix.md) (planned evidence). |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | [17-required-figures](17-required-figures.md), [18-required-tables](18-required-tables.md), [20-threats-to-validity](20-threats-to-validity.md), [25-research-integrity](25-research-integrity.md) |

"Expected conclusions" are **conditional on Level A results**. They are written as
if/then statements so the discussion can be filled honestly after the campaign. Nothing here is
a result.

---

## RQ1 · Safety enforcement

| Element | Content |
|---|---|
| Evidence (now) | Level C: layered safety implementation ([06](06-safety-framework.md)); tests for forbidden namespaces, sandbox confinement, request-field independence, policy and cluster change before injection. B1: six engines each list exactly one target pod (O-13). |
| Evidence (planned) | S1 (T-11); engine audit from E1–E3 |
| Observations | O-13, O-15 |
| Figures / tables | F-06; T-04, T-05, T-11 |
| Expected conclusion | **If** all S1 scenarios end in VALIDATION_FAILED with no engine and no restarts, and the E-block audits show deleted pods ⊆ `target_pods`, **then** the system enforces its declared safety envelope for pod-delete on this environment. |
| Interpretations | (a) Positive: namespace-bound policies plus live checks prevent misconfiguration. (b) Limitation: the guarantees are code-level; the API itself runs with admin kubeconfig rights, so RBAC does not enforce them ([20](20-threats-to-validity.md) E-03). (c) Scope: no live monitor, so harm during a valid run is bounded only by the blast radius (1 pod) and duration. |
| Pitfalls | Do not generalise to other fault types. Do not call it "safe" in an absolute sense; say "enforces the configured policy". |

## RQ2 · Client vs Kubernetes/server evidence

| Element | Content |
|---|---|
| Evidence (now) | B1: O-01, O-02, O-03, O-12. B2: O-04, O-05, O-08. |
| Evidence (planned) | E1–E4 (T-09, T-10, T-15), C1 (T-12) |
| Figures / tables | F-12, F-13, F-14; T-09, T-12, T-15 |
| Expected conclusion | **If** sampled availability detects sub-scrape outages at a rate consistent with outage/scrape interval while client counters detect all of them, and C1 shows small measurement error, **then** client-side measurement is necessary for short disruptions, and sampled K8s metrics should not be the sole impact signal. |
| Interpretations | (a) The 15 s scrape interval is a configuration choice; shorter intervals reduce but do not remove the issue (an inference to state carefully). (b) Server metrics cannot observe failed connections by construction (B2). (c) A single sequential client is one vantage point; real user populations may differ. |
| Negative-result handling | If C1 shows a large error, report the instrument's limits and weaken the v3 claims accordingly. |

## RQ3 · Score discrimination and methodology

| Element | Content |
|---|---|
| Evidence (now) | B2: O-07 (versions disagree; v2 ordering flip), O-08. B1: O-09 (baseline contamination), O-10 (constant Litmus component). C: formula ([09](09-scoring-methodology.md)). |
| Evidence (planned) | E1–E4, V1 (T-09, T-10, T-14) |
| Figures / tables | F-10, F-11, F-15, F-16; T-07, T-08, T-10, T-14 |
| Expected conclusion | **If** v3 separates single-replica from multi-replica cells and decreases with readiness delay, while v2 shows higher within-cell variance driven by the availability component, **then** v3 is a more stable instrument for these configurations. |
| Interpretations | (a) The score is a composite of author-chosen weights; it is not calibrated against business impact. (b) The recovery-time component mostly reflects readiness configuration (O-12). (c) The overlap between `request_failures` and `client_outage` double-weights the same outage. (d) The Litmus component is near-constant without probes. |
| Pitfalls | Do not claim validity or accuracy. Frame the score as explainable and versioned, with known limitations. Present the evolution as design iterations driven by observed measurement problems. |

## RQ4 · Lifecycle reliability

| Element | Content |
|---|---|
| Evidence (now) | C: orchestration tests (deadlines, restart, abort, cleanup). B2: documented auto, restart and abort runs. B1: O-11, O-14. |
| Evidence (planned) | R1 (T-13), decision latency over E-blocks (T-16) |
| Figures / tables | F-04, F-05; T-06, T-13, T-16 |
| Expected conclusion | **If** every R1 run ends in the expected state with exactly one engine and completed cleanup, and E-block runs show no platform-UNKNOWN, **then** the persistent reconciler reliably drives and recovers experiments in this environment. |
| Interpretations | (a) Single-process assumption: no evidence for multiple API replicas. (b) UNKNOWN is a feature: reporting uncertainty instead of guessing. (c) Decision latency (~100 s for a 30 s fault, O-14) is dominated by Litmus start-up and stability sampling. |

## Cross-cutting discussion themes

| Theme | Supporting material |
|---|---|
| Evidence-first design (never invent values; UNAVAILABLE vs ERROR; uncertainty as an outcome) | [07](07-evidence-framework.md) §6 |
| Methodology versioning as a reproducibility mechanism | [09](09-scoring-methodology.md) §1, §5 |
| Self-service UX with server-authoritative safety | [04](04-component-design.md) §1, [06](06-safety-framework.md) |
| Lessons learned: the loss of development evidence, and data management | O-16, [25](25-research-integrity.md) §7 |
| Generalisability (single node, sample apps, modelled warm-up) | [20](20-threats-to-validity.md) |

---

## Related documents
[02-research-context](02-research-context.md) · [15-observation-catalogue](15-observation-catalogue.md) · [20-threats-to-validity](20-threats-to-validity.md) · [22-paper-writing-guide](22-paper-writing-guide.md)

## Missing information
- All Level A results; literature for positioning the interpretations.

## Open questions
- Should negative or neutral results (e.g. no mode effect) be featured? Yes; report them as findings.
