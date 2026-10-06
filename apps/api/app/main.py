import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.errors import register_error_handlers
from app.api.routes.experiments import (
    get_chaos_provider,
    get_kubernetes_adapter,
    get_observation_config,
    get_prometheus_client,
)
from app.api.routes.experiments import router as experiments_router
from app.api.routes.health import router as health_router
from app.api.routes.reports import router as history_router
from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain.safety_policy import policy_for_namespace
from app.services.orchestration.orchestrator import (
    Dependencies,
    OrchestratorConfig,
    Reconciler,
)


def build_reconciler() -> Reconciler:
    settings = get_settings()
    return Reconciler(
        session_factory=SessionLocal,
        deps=Dependencies(
            kubernetes=get_kubernetes_adapter(),
            prometheus=get_prometheus_client(),
            chaos=get_chaos_provider(),
            policies=policy_for_namespace,
        ),
        config=OrchestratorConfig(
            interval_seconds=settings.orchestrator_interval_seconds,
            baseline_window_seconds=settings.baseline_window_seconds,
            baseline_timeout_seconds=settings.baseline_timeout_seconds,
            injection_timeout_seconds=settings.chaos_start_timeout_seconds,
            max_runtime_seconds=settings.orchestration_max_seconds,
            cleanup_grace_seconds=settings.cleanup_grace_seconds,
            observation=get_observation_config(),
        ),
    )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    stop = threading.Event()
    thread = None
    if get_settings().orchestrator_enabled:
        thread = threading.Thread(
            target=build_reconciler().run_forever,
            args=(stop,),
            name="reconciler",
            daemon=True,
        )
        thread.start()
    yield
    stop.set()
    if thread is not None:
        thread.join(timeout=30)


app = FastAPI(title=get_settings().app_name, lifespan=lifespan)
register_error_handlers(app)

app.include_router(health_router)
# Before experiments_router: /experiments/history must not match /{experiment_id}.
app.include_router(history_router)
app.include_router(experiments_router)
