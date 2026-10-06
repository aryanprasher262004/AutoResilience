from typing import Literal

from pydantic import BaseModel

ReadinessReason = Literal["database_unreachable", "schema_missing", "schema_outdated"]


class ReadinessCheck(BaseModel):
    name: Literal["database"]
    status: Literal["pass", "fail"]
    # Machine-readable cause when status is "fail".
    reason: ReadinessReason | None
    # Human-readable; names host:port/database, never credentials.
    detail: str


class Readiness(BaseModel):
    status: Literal["ready", "not_ready"]
    checks: list[ReadinessCheck]
