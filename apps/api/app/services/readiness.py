"""Readiness: can the API serve normal product operations right now?

Only dependencies every operation needs are checked: the database is reachable and its
schema is at the migration head this code expects. Kubernetes and Prometheus are not
part of readiness; the operations that use them report their errors per request.
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.api.errors import database_location, error_cause

ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


@lru_cache
def migration_head() -> str | None:
    return ScriptDirectory.from_config(Config(str(ALEMBIC_INI))).get_current_head()


def _fail(reason: str, detail: str) -> dict[str, Any]:
    return {"name": "database", "status": "fail", "reason": reason, "detail": detail}


def check_database(db: Session) -> dict[str, Any]:
    head = migration_head()
    try:
        db.execute(text("SELECT 1"))
    except DBAPIError as exc:
        db.rollback()
        return _fail(
            "database_unreachable",
            f"Cannot connect to {database_location()}: {error_cause(exc)}",
        )
    try:
        revision = db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except DBAPIError as exc:  # reachable, so this is a missing table, not an outage
        db.rollback()
        return _fail(
            "schema_missing",
            f"{database_location()} has no migration history ({error_cause(exc)}); "
            "run `uv run alembic upgrade head`",
        )
    finally:
        db.rollback()  # read-only probe: never leave a transaction open
    if revision != head:
        return _fail(
            "schema_outdated" if revision else "schema_missing",
            f"{database_location()} is at revision {revision or 'none'}, "
            f"this API expects {head}; run `uv run alembic upgrade head`",
        )
    return {
        "name": "database",
        "status": "pass",
        "reason": None,
        "detail": f"{database_location()} at revision {revision}",
    }


def readiness(db: Session) -> dict[str, Any]:
    checks = [check_database(db)]
    ready = all(c["status"] == "pass" for c in checks)
    return {"status": "ready" if ready else "not_ready", "checks": checks}
