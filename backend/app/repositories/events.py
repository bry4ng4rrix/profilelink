from collections.abc import Sequence
from datetime import datetime
from uuid import UUID

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, ProfileVisit, VaProfile

TIMEZONE = "Indian/Antananarivo"
Event = type[ClickEvent] | type[ProfileVisit]


def _time(model: Event):
    return model.clicked_at if model is ClickEvent else model.visited_at


def _scope(model: Event, va_id: UUID | None) -> tuple:
    return () if va_id is None else (model.va_profile_id == va_id,)


async def count(db: AsyncSession, model: Event, va_id: UUID | None) -> int:
    stmt = select(func.count()).select_from(model).where(*_scope(model, va_id))
    return await db.scalar(stmt) or 0


async def series(
    db: AsyncSession,
    model: Event,
    va_id: UUID | None,
    granularity: str,
    start: datetime,
    end: datetime,
) -> dict[datetime, int]:
    time = _time(model)
    bucket = func.date_trunc(granularity, func.timezone(TIMEZONE, time)).label("bucket")
    stmt = (
        select(bucket, func.count())
        .where(*_scope(model, va_id), time >= start, time < end)
        .group_by("bucket")
    )
    return {row[0]: row[1] for row in await db.execute(stmt)}


async def recent(
    db: AsyncSession, model: Event, va_id: UUID | None, limit: int
) -> Sequence[Row]:
    time = _time(model).label("occurred_at")
    stmt = (
        select(time, model.referer_domain, VaProfile.username.label("va_username"))
        .join(VaProfile, VaProfile.id == model.va_profile_id)
        .where(*_scope(model, va_id))
        .order_by(time.desc())
        .limit(limit)
    )
    return (await db.execute(stmt)).all()


async def click_history(
    db: AsyncSession,
    va_id: UUID | None,
    start: datetime,
    end: datetime,
    limit: int,
    offset: int,
) -> Sequence[Row]:
    stmt = (
        select(
            ClickEvent.clicked_at,
            ClickEvent.referer_domain,
            ClickEvent.user_agent,
            VaProfile.username.label("va_username"),
        )
        .join(VaProfile, VaProfile.id == ClickEvent.va_profile_id)
        .where(
            *_scope(ClickEvent, va_id),
            ClickEvent.clicked_at >= start,
            ClickEvent.clicked_at < end,
        )
        .order_by(ClickEvent.clicked_at.desc())
        .limit(limit)
        .offset(offset)
    )
    return (await db.execute(stmt)).all()
