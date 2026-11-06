from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.api.deps import Db, current_session
from app.schemas.analytics import ClicksOut, Granularity, OverviewOut, VisitsOut
from app.services import analytics

router = APIRouter(
    prefix="/api/v1/admin/analytics", tags=["admin"], dependencies=[Depends(current_session)]
)

From = Annotated[date | None, Query(alias="from")]
To = Annotated[date | None, Query(alias="to")]


@router.get("/overview")
async def overview(db: Db, va_id: UUID | None = None) -> OverviewOut:
    return await analytics.overview(db, va_id)


@router.get("/clicks")
async def clicks(
    db: Db,
    va_id: UUID | None = None,
    granularity: Granularity = "day",
    start: From = None,
    end: To = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClicksOut:
    return await analytics.clicks(db, va_id, granularity, start, end, limit, offset)


@router.get("/visits")
async def visits(
    db: Db,
    va_id: UUID | None = None,
    granularity: Granularity = "day",
    start: From = None,
    end: To = None,
) -> VisitsOut:
    return await analytics.visits(db, va_id, granularity, start, end)
