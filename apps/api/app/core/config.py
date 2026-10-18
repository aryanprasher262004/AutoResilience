import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.domain.safety_policy import SYSTEM_NAMESPACES

_NAMESPACE = re.compile(r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$")


class DiscoveryCluster(BaseModel):
    """A kubeconfig context the operator authorized for read-only discovery.

    The engine only lists resources in `namespaces` there and never runs chaos on it:
    experiments always target KUBE_CONTEXT. Credentials come from the kubeconfig
    (in the local stack: a read-only ServiceAccount created by `ar cluster import`).
    """

    context: str = Field(min_length=1, max_length=253)
    namespaces: list[str] = Field(min_length=1, max_length=50)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AutoResilience API"
    environment: str = "development"
    # "local-stack": the containerised stack managed by tools/ar (compose.yaml);
    # "development": host processes. See check_runtime().
    runtime_mode: Literal["development", "local-stack"] = "development"
    database_url: str = (
        "postgresql+psycopg://postgres:postgres@localhost:5432/autoresilience"
    )
    prometheus_url: str = "http://localhost:9090"
    prometheus_timeout_seconds: float = 5.0
    # How much steady-state history the baseline summarizes.
    baseline_window_seconds: int = 300
    # How long to wait for Litmus to actually delete the target pods.
    chaos_start_timeout_seconds: float = 120.0
    chaos_poll_interval_seconds: float = 2.0
    # Observation / recovery (see services/orchestration/recovery.py for the rule).
    observation_grace_seconds: float = 180.0
    recovery_timeout_seconds: float = 300.0
    recovery_stable_samples: int = 4
    recovery_max_sample_gap_seconds: float = 40.0
    recovery_error_ratio_tolerance: float = 0.01
    # Orchestrator (services/orchestration/orchestrator.py): in-process reconciler.
    orchestrator_enabled: bool = True
    orchestrator_interval_seconds: float = 5.0
    baseline_timeout_seconds: float = 180.0
    # Hard cap per auto run from /run until a terminal state (stops the engine).
    orchestration_max_seconds: float = 1800.0
    # How long a finished run's ChaosEngine may still be running before cleanup.
    cleanup_grace_seconds: float = 120.0
    frontend_origin: str = "http://localhost:3000"
    # kubeconfig context for the target cluster; None uses the current context
    # (development only: the local stack refuses to start without it).
    kube_context: str | None = None
    kube_request_timeout_seconds: float = 5.0
    # Further contexts for read-only discovery (JSON list of DiscoveryCluster), e.g.
    # [{"context": "kind-staging", "namespaces": ["shop"]}]. Written by `ar cluster
    # import` in the local stack; never selectable or extendable through the API.
    discovery_clusters: list[DiscoveryCluster] = []
    # Imported applications (P7, docs/imports.md). A kubeconfig for the dedicated
    # provisioner ServiceAccount (infra/rbac/provisioner.yaml) on the execution
    # cluster; None: imports can be reviewed but not deployed.
    provisioner_kubeconfig: str | None = None
    provisioner_context: str | None = None
    import_deploy_timeout_seconds: float = 300.0
    # Same image as the sample load generator (infra/versions.env LOADGEN_IMAGE).
    loadgen_image: str = "python:3.12.11-alpine3.22"


class ConfigurationError(Exception):
    """The settings are unsafe or incomplete for the selected runtime mode."""


def check_runtime(settings: Settings) -> None:
    """Refuse configurations a packaged stack must never run with."""
    if settings.runtime_mode == "local-stack" and not settings.kube_context:
        # The current-context fallback could silently target the wrong cluster.
        raise ConfigurationError(
            "RUNTIME_MODE=local-stack requires an explicit KUBE_CONTEXT "
            "(the stack sets kind-autoresilience; run `ar install` to generate "
            "its kubeconfig)"
        )
    seen: set[str] = set()
    for cluster in settings.discovery_clusters:
        if cluster.context == settings.kube_context or cluster.context in seen:
            raise ConfigurationError(
                f"DISCOVERY_CLUSTERS: context {cluster.context!r} is listed twice "
                "or is the execution context (KUBE_CONTEXT)"
            )
        seen.add(cluster.context)
        for namespace in cluster.namespaces:
            if not _NAMESPACE.match(namespace) or len(namespace) > 63:
                raise ConfigurationError(
                    f"DISCOVERY_CLUSTERS: {namespace!r} is not a namespace name"
                )
            if namespace in SYSTEM_NAMESPACES:
                raise ConfigurationError(
                    f"DISCOVERY_CLUSTERS: {namespace!r} is a system namespace"
                )


@lru_cache
def get_settings() -> Settings:
    return Settings()
