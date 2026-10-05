from fastapi import FastAPI

from app.api.routes.experiments import router as experiments_router
from app.api.routes.health import router as health_router
from app.core.config import get_settings

app = FastAPI(title=get_settings().app_name)

app.include_router(health_router)
app.include_router(experiments_router)
