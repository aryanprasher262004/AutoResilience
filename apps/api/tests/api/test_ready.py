"""GET /ready (dependency readiness) vs GET /health (process liveness)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app
from app.services.readiness import migration_head


def stamp(db: Session, revision: str | None) -> None:
    """What `alembic upgrade` leaves behind (the test schema is built without Alembic)."""
    db.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL)"))
    if revision is not None:
        db.execute(text("INSERT INTO alembic_version VALUES (:r)"), {"r": revision})
    db.commit()


class UnreachableSession:
    def execute(self, *args: Any, **kwargs: Any) -> None:
        raise OperationalError(
            "SELECT 1", {}, Exception("connection failed: Connection refused\nmore")
        )

    def rollback(self) -> None:
        pass


def test_migration_head_comes_from_the_alembic_scripts() -> None:
    assert migration_head() == "08697f19aec0"


def test_ready_when_database_is_at_head(
    client: TestClient, db_session: Session
) -> None:
    stamp(db_session, migration_head())

    response = client.get("/ready")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["checks"] == [
        {
            "name": "database",
            "status": "pass",
            "reason": None,
            "detail": f"localhost:5432/autoresilience at revision {migration_head()}",
        }
    ]


@pytest.mark.parametrize(
    ("revision", "reason"),
    [("0123456789ab", "schema_outdated"), (None, "schema_missing")],
)
def test_not_ready_when_schema_is_not_at_head(
    client: TestClient, db_session: Session, revision: str | None, reason: str
) -> None:
    stamp(db_session, revision)

    response = client.get("/ready")

    assert response.status_code == 503
    check = response.json()["checks"][0]
    assert (check["status"], check["reason"]) == ("fail", reason)
    assert "alembic upgrade head" in check["detail"]


def test_not_ready_without_migration_table(client: TestClient) -> None:
    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["checks"][0]["reason"] == "schema_missing"


def test_not_ready_when_database_is_unreachable(client: TestClient) -> None:
    app.dependency_overrides[get_db] = UnreachableSession

    response = client.get("/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    check = body["checks"][0]
    assert check["reason"] == "database_unreachable"
    assert check["detail"] == (
        "Cannot connect to localhost:5432/autoresilience: "
        "connection failed: Connection refused"
    )
    assert "postgres:postgres" not in response.text


def test_health_stays_up_while_not_ready(client: TestClient) -> None:
    app.dependency_overrides[get_db] = UnreachableSession

    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
