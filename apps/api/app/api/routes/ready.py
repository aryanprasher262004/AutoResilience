"""GET /ready: dependency readiness, distinct from the process liveness of GET /health."""

from typing import Annotated

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.readiness import Readiness
from app.services.readiness import readiness

router = APIRouter(tags=["health"])


@router.get(
    "/ready",
    response_model=Readiness,
    responses={
        503: {"model": Readiness, "description": "A required dependency failed"}
    },
)
def get_readiness(db: Annotated[Session, Depends(get_db)]) -> JSONResponse:
    """200 when the database is reachable and migrated to this API's head, else 503.

    `/health` only says the process is up; use this to know whether normal
    operations (experiments, history, services) can work.
    """
    result = Readiness.model_validate(readiness(db))
    return JSONResponse(
        status_code=200 if result.status == "ready" else 503,
        content=result.model_dump(mode="json"),
    )
