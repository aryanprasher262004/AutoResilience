"""Turn database outages into explicit 503 responses instead of opaque 500s.

Only two well-understood conditions are mapped; every other error still propagates
as a 500 so real bugs stay visible.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from psycopg import errors as pg_errors
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError, ProgrammingError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


def database_location() -> str:
    url = make_url(get_settings().database_url)  # never includes the password
    return f"{url.host or 'localhost'}:{url.port or 5432}/{url.database}"


def error_cause(exc: Exception) -> str:
    orig = getattr(exc, "orig", None) or exc
    lines = str(orig).strip().splitlines()
    return lines[0] if lines else type(orig).__name__


def _unavailable(detail: str) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": detail})


async def database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Database unavailable: %s", error_cause(exc))
    return _unavailable(
        f"Database unavailable at {database_location()}: {error_cause(exc)}. "
        "Start it with scripts/dev-db.sh or set DATABASE_URL."
    )


async def database_error(request: Request, exc: Exception) -> JSONResponse:
    if isinstance(getattr(exc, "orig", None), pg_errors.UndefinedTable):
        logger.error("Database schema missing: %s", error_cause(exc))
        return _unavailable(
            f"Database {database_location()} has no AutoResilience schema ({error_cause(exc)}). "
            "Run `uv run alembic upgrade head` in apps/api."
        )
    raise exc  # a genuine bug: keep the 500


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(OperationalError, database_unavailable)
    app.add_exception_handler(ProgrammingError, database_error)
