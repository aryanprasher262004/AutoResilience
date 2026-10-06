# 22 · Paper Writing Guide

| | |
|---|---|
| **Purpose** | For every paper section: purpose, expected length, evidence, figures, tables, references, common mistakes, and a checklist before writing. Applicable to IEEE, ACM, Springer, journal and dissertation formats. |
| **Source of truth** | This knowledge base. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | All; especially [25-research-integrity](25-research-integrity.md), [17-required-figures](17-required-figures.md), [18-required-tables](18-required-tables.md) |

Lengths assume an 8–10 page two-column conference paper. Multiply by about 2 for a journal
paper, and by about 4–6 for a dissertation chapter set.

---

## 0. Global rules

1. Every number comes from `research/experiment-results.*` (B-level, labelled) or from campaign exports (A-level). Never from chat logs or memory.
2. Every novelty claim carries a citation, or is removed. "Requires literature validation" items are not claims.
3. Use the terminology in [appendix/glossary](appendix/glossary.md) consistently: *experiment*, *run*, *client outage*, *time to recovery (TTR)*, *UNKNOWN (cause)*, *Resilience Score v3*.
4. Describe the implementation in the present tense ("AutoResilience validates…"); describe results in the past tense ("we observed…").
5. Report n everywhere.

## 1. Section guide

### Title and abstract
| | |
|---|---|
| Purpose | State the problem, approach, evaluation and key result |
| Length | Abstract 150–250 words |
| Evidence | Only Level A results in the result sentence |
| Mistakes | Claiming "safe" or "accurate" without qualification; numbers from B-level data presented as results |
| Checklist | ☐ Campaign done ☐ One headline number with n ☐ No unsupported "first/novel" |

### 1. Introduction
| | |
|---|---|
| Purpose | Motivation (M1–M4), gap (cited), contributions (C1–C5) |
| Length | ~1 page |
| Evidence | [02](02-research-context.md) §1–2, §6; optionally one motivating observation (O-03, labelled "in preliminary runs") |
| Figures | none, or F-01 |
| References | chaos engineering, Kubernetes resilience, observability ([23](23-reference-collection-guide.md) A, B, D) |
| Mistakes | A gap without citations; listing future-work features as contributions |
| Checklist | ☐ Every gap sentence cited ☐ Contributions map to sections |

### 2. Background and related work
| | |
|---|---|
| Purpose | Define Kubernetes self-healing, pod deletion, chaos experiments, SLIs and SLOs; position against tools and scoring approaches |
| Length | ~1 page |
| Evidence | Literature only |
| Tables | T-19 |
| Mistakes | Describing tools without sources; strawman comparisons |
| Checklist | ☐ T-19 filled from the literature ☐ Comparison criteria defined before filling |

### 3. System design
| | |
|---|---|
| Purpose | Architecture, lifecycle, safety framework, evidence model |
| Length | 1.5–2 pages |
| Evidence | Level C: [03](03-system-architecture.md), [05](05-system-workflows.md), [06](06-safety-framework.md), [07](07-evidence-framework.md) |
| Figures | F-01, F-04/F-05, F-06, F-07 |
| Tables | T-04, T-05, T-06 |
| Mistakes | Implying a live safety monitor, other faults, Alertmanager, or in-cluster deployment; overstating RBAC as a guarantee |
| Checklist | ☐ The single-writer and read-only properties stated with their enforcement level ☐ Future work separated |

### 4. Recovery and scoring methodology
| | |
|---|---|
| Purpose | Formal recovery rule, UNKNOWN taxonomy, score v3 formula, versioning |
| Length | 1–1.5 pages |
| Evidence | Level C: [08](08-recovery-framework.md), [09](09-scoring-methodology.md); worked example A or B (labelled as a reconstruction from a documented development run) |
| Figures | F-08, F-10, F-11 |
| Tables | T-07, T-08 |
| Mistakes | Calling the score "validated"; omitting the TTR definition; omitting missing-data handling |
| Checklist | ☐ Formulas match `resilience_score.py` ☐ Thresholds table ☐ Version evolution motivated by observations |

### 5. Implementation
| | |
|---|---|
| Purpose | Stack, environment, reproducibility |
| Length | 0.5 page (conference); full chapter (dissertation) |
| Evidence | [10](10-implementation.md), [11](11-technology-stack.md), [12](12-experimental-environment.md) |
| Tables | T-01, T-02, T-03 |
| Mistakes | Unverified versions; omitting the modelled warm-up |
| Checklist | ☐ Pinned vs observed versions labelled |

### 6. Evaluation: setup and methodology
| | |
|---|---|
| Purpose | RQs, variables, protocol, metrics |
| Length | ~1 page |
| Evidence | [13](13-experimental-methodology.md), [16](16-final-experiment-matrix.md) |
| Tables | matrix summary |
| Mistakes | Changing the protocol after seeing the data without saying so |
| Checklist | ☐ Spacing rule stated ☐ Commit recorded ☐ n per cell |

### 7. Results
| | |
|---|---|
| Purpose | Answer RQ1–RQ4 with Level A data |
| Length | 1.5–2 pages |
| Evidence | **Level A only** |
| Figures | F-12, F-14, F-15, F-16 |
| Tables | T-09 to T-16 |
| Mistakes | Mixing B1 development observations into the results; statistics without n; colour-only encodings |
| Checklist | ☐ Every number traceable to an export and a script ☐ UNKNOWN runs reported, not dropped |

### 8. Discussion
| | |
|---|---|
| Purpose | Interpret per RQ; alternatives; implications |
| Length | ~1 page |
| Evidence | [19](19-discussion-framework.md) |
| Mistakes | Generalising beyond a single-node kind cluster and sample apps |
| Checklist | ☐ Negative results discussed ☐ Interpretations labelled as such |

### 9. Threats to validity
| | |
|---|---|
| Purpose | Honest limitations |
| Length | 0.5 page |
| Evidence | [20](20-threats-to-validity.md) (X-01, X-03, C-01, M-01, S-01 at minimum) |
| Tables | T-18 (optional) |

### 10. Conclusion and future work
| | |
|---|---|
| Purpose | Summarise contributions and results; future work from [21](21-future-work.md) |
| Length | 0.3–0.5 page |
| Mistakes | New claims not in the results |

### Artefact / data availability (if required)
Point to the repository commit, `research/raw/` exports and analysis scripts. A licence is
not present in the repository (Not verified from implementation that one has been chosen).

## 2. Dissertation mapping

| Chapter | Sources |
|---|---|
| Introduction | [01](01-project-overview.md), [02](02-research-context.md) |
| Literature review | [23](23-reference-collection-guide.md) + literature |
| Requirements and design | [03](03-system-architecture.md)–[09](09-scoring-methodology.md), [24](24-engineering-decisions.md) |
| Implementation | [10](10-implementation.md), [11](11-technology-stack.md), appendix |
| Evaluation | [12](12-experimental-environment.md), [13](13-experimental-methodology.md), [16](16-final-experiment-matrix.md), campaign results |
| Discussion and limitations | [19](19-discussion-framework.md), [20](20-threats-to-validity.md) |
| Conclusion and future work | [21](21-future-work.md) |
| Appendices | `appendix/*`, [14](14-current-evidence.md) (development evidence, labelled) |

## 3. Presentation mapping

| Slide | Source |
|---|---|
| Problem and motivation | [01](01-project-overview.md) §1–2 |
| Architecture | F-01 |
| Lifecycle and safety | F-04, F-06 |
| Evidence and score | F-07, F-10 |
| Results | F-12, F-14 (Level A) |
| Demo | live console (builder → room → report) |
| Limitations and future work | [20](20-threats-to-validity.md), [21](21-future-work.md) |

---

## Related documents
[17-required-figures](17-required-figures.md) · [18-required-tables](18-required-tables.md) · [19-discussion-framework](19-discussion-framework.md) · [23-reference-collection-guide](23-reference-collection-guide.md) · [25-research-integrity](25-research-integrity.md)

## Missing information
- The target venue and its page limits and template.

## Open questions
- A single paper covering RQ1–RQ4, or two papers (system plus measurement study)? Recommended: one systems paper; a measurement-focused follow-up if C1 and E4 are strong.
