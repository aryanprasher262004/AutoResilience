"""Read-only history and dashboard endpoints (services/analysis/history.py)."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.experiment import FaultType
from app.domain.state_machine import ExperimentState
from app.schemas.history import DashboardSummary, ExperimentPage, ExperimentSummary
from app.services.analysis.history import (
    Order,
    SortKey,
    dashboard_summary,
    query_history,
    summarize,
)

router = APIRouter(tags=["history"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("/experiments/history", response_model=ExperimentPage)
def experiment_history(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    state: Annotated[list[ExperimentState] | None, Query()] = None,
    fault_type: Annotated[list[FaultType] | None, Query()] = None,
    namespace: Annotated[list[str] | None, Query()] = None,
    sort: SortKey = "created_at",
    order: Order = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ExperimentPage:
    """Filtered, sorted, paginated experiment summaries (no evidence payloads).

    Repeat `state`, `fault_type` or `namespace` to match any of several values;
    `q` matches name, workload or namespace (case-insensitive substring).
    """
    items, total = query_history(
        db,
        q=q,
        states=state,
        fault_types=fault_type,
        namespaces=namespace,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    return ExperimentPage(
        items=[ExperimentSummary.model_validate(summarize(e)) for e in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
def get_dashboard_summary(db: DbSession) -> DashboardSummary:
    """Counts, score/recovery statistics and recent runs from persisted experiments."""
    return DashboardSummary.model_validate(dashboard_summary(db))
