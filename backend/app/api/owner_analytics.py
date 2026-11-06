from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentProfile, Db
from app.schemas.analytics import ClicksOut, Granularity, OverviewOut, VisitsOut
from app.services import analytics

router = APIRouter(prefix="/api/v1/owner/analytics", tags=["owner"])

From = Annotated[date | None, Query(alias="from")]
To = Annotated[date | None, Query(alias="to")]


@router.get("/overview")
async def overview(profile: CurrentProfile, db: Db) -> OverviewOut:
    return await analytics.overview(db, profile)


@router.get("/clicks")
async def clicks(
    profile: CurrentProfile,
    db: Db,
    granularity: Granularity = "day",
    start: From = None,
    end: To = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ClicksOut:
    return await analytics.clicks(db, profile, granularity, start, end, limit, offset)


@router.get("/visits")
async def visits(
    profile: CurrentProfile,
    db: Db,
    granularity: Granularity = "day",
    start: From = None,
    end: To = None,
) -> VisitsOut:
    return await analytics.visits(db, profile, granularity, start, end)
