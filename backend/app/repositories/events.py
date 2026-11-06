from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, ProfileVisit

TIMEZONE = "Indian/Antananarivo"
Event = type[ClickEvent] | type[ProfileVisit]


def _time(model: Event):
    return model.clicked_at if model is ClickEvent else model.visited_at


async def count(db: AsyncSession, model: Event, profile_id: UUID) -> int:
    stmt = select(func.count()).select_from(model).where(model.profile_id == profile_id)
    return await db.scalar(stmt) or 0


async def series(
    db: AsyncSession, model: Event, profile_id: UUID, granularity: str, start: datetime, end: datetime
) -> dict[datetime, int]:
    time = _time(model)
    bucket = func.date_trunc(granularity, func.timezone(TIMEZONE, time)).label("bucket")
    stmt = (
        select(bucket, func.count())
        .where(model.profile_id == profile_id, time >= start, time < end)
        .group_by("bucket")
    )
    return {row[0]: row[1] for row in await db.execute(stmt)}


async def recent(db: AsyncSession, model: Event, profile_id: UUID, limit: int) -> Sequence[Row]:
    time = _time(model).label("occurred_at")
    stmt = (
        select(time, model.referer_domain)
        .where(model.profile_id == profile_id)
        .order_by(time.desc())
        .limit(limit)
    )
    return (await db.execute(stmt)).all()


async def click_history(
    db: AsyncSession, profile_id: UUID, start: datetime, end: datetime, limit: int, offset: int
) -> Sequence[ClickEvent]:
    stmt = (
        select(ClickEvent)
        .where(
            ClickEvent.profile_id == profile_id,
            ClickEvent.clicked_at >= start,
            ClickEvent.clicked_at < end,
        )
        .order_by(ClickEvent.clicked_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.scalars(stmt)).all()
