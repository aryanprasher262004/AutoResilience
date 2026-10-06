from collections.abc import Callable, Iterator

import pytest
from fastapi.testclient import TestClient
from psycopg import errors as pg_errors
from sqlalchemy.exc import OperationalError, ProgrammingError
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.main import app


def failing_db(exc: Exception) -> Callable[[], Iterator[Session]]:
    def get_db_override() -> Iterator[Session]:
        raise exc
        yield  # pragma: no cover

    return get_db_override


@pytest.mark.parametrize(
    "path", ["/experiments", "/experiments/history", "/dashboard/summary"]
)
def test_unreachable_database_is_503_with_cause(client: TestClient, path: str) -> None:
    refused = OperationalError(
        "SELECT 1", {}, Exception("connection failed: Connection refused\n\tIs ...")
    )
    app.dependency_overrides[get_db] = failing_db(refused)

    response = client.get(path)

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail.startswith("Database unavailable at localhost:5432/autoresilience")
    assert "Connection refused" in detail
    assert "postgres:postgres" not in detail  # credentials never leak


def test_unmigrated_database_is_503(client: TestClient) -> None:
    missing = ProgrammingError(
        "SELECT", {}, pg_errors.UndefinedTable('relation "experiments" does not exist')
    )
    app.dependency_overrides[get_db] = failing_db(missing)

    response = client.get("/experiments")

    assert response.status_code == 503
    assert "alembic upgrade head" in response.json()["detail"]


def test_other_programming_errors_stay_500(client: TestClient) -> None:
    bug = ProgrammingError("SELECT", {}, Exception("syntax error at or near"))
    app.dependency_overrides[get_db] = failing_db(bug)

    with pytest.raises(ProgrammingError):
        client.get("/experiments")


def test_health_does_not_need_the_database(client: TestClient) -> None:
    refused = OperationalError("SELECT 1", {}, Exception("Connection refused"))
    app.dependency_overrides[get_db] = failing_db(refused)

    assert client.get("/health").json() == {"status": "ok"}
