# AutoResilience Research Knowledge Base (handoff)

| | |
|---|---|
| **Purpose** | The master source of truth for every research document about AutoResilience (papers, journal articles, dissertation, theses, presentations). It explains how to read, use and update this folder. |
| **Source of truth** | The repository at the commit stated in each file; `research/experiment-results.*`; committed docs. |
| **Last generated from commit** | `92e33dd` |
| **Dependencies on other files** | All files in this folder |

This folder is **not** software documentation, an SRS, or a paper. It is the verified
knowledge a writer needs, with every statement labelled by evidence level
([25-research-integrity](25-research-integrity.md)).

---

## 1. Read this first

1. **There is no controlled experimental evidence yet (Level A = 0 runs).** Everything quantitative today is pre-experimental (Level B) and must not appear as a result. Run the campaign in [16](16-final-experiment-matrix.md) first.
2. Every number must come from `research/experiment-results.*` (B-level, labelled) or from future campaign exports. Never take numbers from development chat logs or memory.
3. "Not verified from implementation." and "Requires literature validation." are deliberate markers. Do not delete them without verifying the statement.

## 2. Recommended reading order

```mermaid
flowchart LR
    R0[README] --> R25[25 Research integrity]
    R25 --> R01[01 Overview] --> R02[02 Research context]
    R02 --> R03[03 Architecture] --> R05[05 Workflows]
    R05 --> R06[06 Safety] --> R07[07 Evidence] --> R08[08 Recovery] --> R09[09 Scoring]
    R09 --> R12[12 Environment] --> R13[13 Methodology] --> R16[16 Matrix]
    R16 --> R14[14 Current evidence] --> R15[15 Observations]
    R15 --> R19[19 Discussion] --> R20[20 Threats] --> R22[22 Writing guide]
```

| Pass | Files | Time |
|---|---|---|
| Orientation (1 h) | README, 25, 01, 02, 03 | understand what exists and what can be claimed |
| Method (2 h) | 05, 06, 07, 08, 09 | the system and its methodology |
| Evaluation (1–2 h) | 12, 13, 16, 14, 15 | environment, plan, current evidence |
| Writing (1 h) | 17, 18, 19, 20, 21, 22, 23 | figures, tables, discussion, threats, guide, literature |
| Reference (as needed) | 04, 10, 11, 24, appendix/* | component detail, implementation, versions, decisions, API, schema, glossary |

## 3. File index

| # | File | Content |
|---|---|---|
| — | [README](README.md) | This guide |
| 01 | [project-overview](01-project-overview.md) | Problem, motivation, goals, scope, status, non-goals, evolution |
| 02 | [research-context](02-research-context.md) | Motivation, gap (to validate), RQ1–RQ4, objectives, hypotheses, contributions |
| 03 | [system-architecture](03-system-architecture.md) | High-level, deployment, data flow, backend, frontend, persistence, sequence, state |
| 04 | [component-design](04-component-design.md) | Per-component design |
| 05 | [system-workflows](05-system-workflows.md) | Sequence diagrams for all workflows |
| 06 | [safety-framework](06-safety-framework.md) | Policies, checks, blast radius, RBAC, abort, cleanup, live-safety gap |
| 07 | [evidence-framework](07-evidence-framework.md) | Evidence sources, merging, philosophy, limits |
| 08 | [recovery-framework](08-recovery-framework.md) | Recovery rule, TTR, UNKNOWN taxonomy, timeouts |
| 09 | [scoring-methodology](09-scoring-methodology.md) | v1–v3 formulas, thresholds, missing data, worked examples |
| 10 | [implementation](10-implementation.md) | Repository, modules, status (verified / incomplete) |
| 11 | [technology-stack](11-technology-stack.md) | Exact versions, CI |
| 12 | [experimental-environment](12-experimental-environment.md) | Reproducible environment and setup |
| 13 | [experimental-methodology](13-experimental-methodology.md) | Variables, metrics (JSON paths), protocol, data management |
| 14 | [current-evidence](14-current-evidence.md) | All existing evidence by category and level |
| 15 | [observation-catalogue](15-observation-catalogue.md) | O-01 … O-16 |
| 16 | [final-experiment-matrix](16-final-experiment-matrix.md) | E1–E4, S1, R1, C1, V1 |
| 17 | [required-figures](17-required-figures.md) | F-01 … F-20 |
| 18 | [required-tables](18-required-tables.md) | T-01 … T-20 |
| 19 | [discussion-framework](19-discussion-framework.md) | Per-RQ discussion scaffolding |
| 20 | [threats-to-validity](20-threats-to-validity.md) | Internal, external, construct, conclusion, engineering, measurement, infrastructure |
| 21 | [future-work](21-future-work.md) | Planned work only |
| 22 | [paper-writing-guide](22-paper-writing-guide.md) | Per-section guidance and checklists |
| 23 | [reference-collection-guide](23-reference-collection-guide.md) | Literature areas (no citations) |
| 24 | [engineering-decisions](24-engineering-decisions.md) | D-01 … D-27 |
| 25 | [research-integrity](25-research-integrity.md) | Evidence levels A–D; what can and cannot be claimed |
| A | [appendix/api-overview](appendix/api-overview.md) | Endpoints and status codes |
| A | [appendix/repository-map](appendix/repository-map.md) | Every directory and research-critical file |
| A | [appendix/kubernetes-topology](appendix/kubernetes-topology.md) | Cluster topology |
| A | [appendix/environment-versions](appendix/environment-versions.md) | Flat version list |
| A | [appendix/experiment-json-schema](appendix/experiment-json-schema.md) | Stored record and research dataset schemas |
| A | [appendix/glossary](appendix/glossary.md) | Terminology |

## 4. Which files feed which output

| Output | Primary inputs | Supporting |
|---|---|---|
| **Conference research paper** (IEEE, ACM, Springer LNCS) | 02, 03, 06–09, 12, 13, 16 (+ campaign results), 17, 18, 19, 20, 22, 25 | 23 (literature), 24 (selected decisions) |
| **Journal paper** | All of the above + 05, 10, 11, 14 (development evidence as a labelled preliminary study), 21, 24 | appendix |
| **Dissertation / thesis** | All files; chapter mapping in [22](22-paper-writing-guide.md) §2 | `research/evidence-audit.md`, the repository |
| **Presentation** | 01, 03 (F-01), 06 (F-06), 07 (F-07), 09 (F-10), campaign figures, 20, 21; slide map in [22](22-paper-writing-guide.md) §3 | live demo of the console |
| **Artefact / data appendix** | 12, 13 §8, appendix/experiment-json-schema, appendix/environment-versions | `research/raw/` (after the campaign) |

## 5. How to update these files

| When | Update |
|---|---|
| Code changes that affect behaviour | The relevant design files (03–10), the header commit, [24](24-engineering-decisions.md) if it is a decision; re-check [25](25-research-integrity.md) §3–4 |
| Methodology change (scoring, recovery, evidence) | [07](07-evidence-framework.md), [08](08-recovery-framework.md) or [09](09-scoring-methodology.md); add a **new score version** rather than editing one (project rule); update the glossary |
| After each campaign block | [14](14-current-evidence.md) (move items to Level A), [15](15-observation-catalogue.md) (confirm or refute observations), [16](16-final-experiment-matrix.md) status, [18](18-required-tables.md) / [17](17-required-figures.md) status |
| New literature | [23](23-reference-collection-guide.md); replace "Requires literature validation" markers only with cited statements |
| Environment change | [11](11-technology-stack.md), [12](12-experimental-environment.md), appendix/environment-versions, appendix/kubernetes-topology |

**Rules.**
1. Keep the header (Purpose, Source of truth, Last generated from commit, Dependencies) and the footer (Related documents, Missing information, Open questions) in every file.
2. Never upgrade an evidence level without the evidence.
3. Regenerate numeric tables from data with scripts, not by hand.
4. Change the "Last generated from commit" only after re-verifying the file against that commit.

## 6. Key facts at a glance (verified)

| Fact | Value | Level |
|---|---|---|
| Fault types supported | pod-delete only (GRACEFUL / FORCE) | C |
| Lifecycle | 11 states; UNKNOWN with cause | C |
| Score | v3: recovery 35, client outage 15, request failures 30, restarts 10, Litmus 10 | C |
| Tests | 431 backend, 39 frontend | C |
| Controlled experiments | 0 | — |
| Development evidence | 6 identified runs, 16 unattributed disruptions, 6 documented runs | B1/B2 |
| Strongest preliminary observation | 15 s sampled availability caught 9/17 outages; the client caught 17/17 | B1 |

---

## Related documents
[25-research-integrity](25-research-integrity.md) · [22-paper-writing-guide](22-paper-writing-guide.md) · `research/evidence-audit.md` · `research/experiment-results.json`

## Missing information
- Level A evidence; literature; venue selection.

## Open questions
- Who owns keeping this folder in sync with the code after each milestone? Recommended: the author of each behaviour-changing commit.
