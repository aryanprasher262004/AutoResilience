from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "AutoResilience API"
    environment: str = "development"
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
    # kubeconfig context for the target cluster; None uses the current context.
    kube_context: str | None = None
    kube_request_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
