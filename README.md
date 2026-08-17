# AutoResilience Documentation

> A self-service resilience testing platform for Kubernetes: configure a controlled failure, validate safety, observe the impact, measure recovery, calculate an explainable Resilience Score, and produce evidence-backed reports.

![Architecture](assets/architecture.svg)

## Why this repository exists

This repository is the **documentation and product-understanding source of truth**. It intentionally stays separate from the application repository so a new teammate, evaluator, or user can understand AutoResilience without reading implementation code.

## Start here

1. [Project overview](docs/01-project-overview.md)
2. [Product glossary](docs/02-glossary.md)
3. [Local setup](docs/03-local-setup.md)
4. [Git and collaboration workflow](docs/04-git-workflow.md)
5. [Product UX](docs/05-product-ux.md)
6. [Architecture decisions](docs/06-decisions.md)

## Product flow

![Product flow](assets/product-flow.svg)

## Current scope

- Kubernetes target environment
- LitmusChaos-based failure execution
- Prometheus + Alertmanager observability
- FastAPI orchestration and analysis
- PostgreSQL experiment history
- React/Next.js product UI
- Baseline -> failure -> recovery analysis
- Explainable Resilience Score
- Reports and CI reliability gates

## Documentation rule

Every important behavior must be documented as one of:

- **Concept:** what a term means
- **Decision:** why the team chose an approach
- **Runbook:** how to operate or debug it
- **Contract:** what data/API is expected

Do not duplicate implementation details that are already obvious from code. Document the things a future teammate would otherwise have to ask someone to explain.
