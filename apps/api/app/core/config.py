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
    frontend_origin: str = "http://localhost:3000"
    # kubeconfig context for the target cluster; None uses the current context.
    kube_context: str | None = None
    kube_request_timeout_seconds: float = 5.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
