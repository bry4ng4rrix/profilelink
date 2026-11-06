from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ClickEvent, ProfileVisit
from app.repositories import events, vas
from app.schemas.analytics import (
    Activity,
    ClickEntry,
    ClicksOut,
    Granularity,
    OverviewOut,
    SeriesPoint,
    VisitsOut,
)

# Madagascar stays on UTC+3 all year; this also avoids needing tzdata in the image.
LOCAL_TZ = timezone(timedelta(hours=3))
DEFAULT_DAYS = 30
MAX_RANGE_DAYS = 1830
RECENT_LIMIT = 10


def _resolve_range(start: date | None, end: date | None) -> tuple[date, date]:
    end = end or datetime.now(LOCAL_TZ).date()
    start = start or end - timedelta(days=DEFAULT_DAYS - 1)
    if start > end or (end - start).days > MAX_RANGE_DAYS:
        raise HTTPException(422, "invalid_range")
    return start, end


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return (
        datetime.combine(start, time.min, LOCAL_TZ).astimezone(UTC),
        datetime.combine(end + timedelta(days=1), time.min, LOCAL_TZ).astimezone(UTC),
    )


def _truncate(day: date, granularity: Granularity) -> date:
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    return day.replace(day=1) if granularity == "month" else day


def _buckets(start: date, end: date, granularity: Granularity) -> Iterator[date]:
    current = _truncate(start, granularity)
    while current <= end:
        yield current
        if granularity == "month":
            current = (current + timedelta(days=32)).replace(day=1)
        else:
            current += timedelta(days=7 if granularity == "week" else 1)


async def _series(
    db: AsyncSession,
    model: type[ClickEvent] | type[ProfileVisit],
    va_id: UUID | None,
    granularity: Granularity,
    start: date,
    end: date,
) -> tuple[int, list[SeriesPoint]]:
    counts = await events.series(db, model, va_id, granularity, *_bounds(start, end))
    by_day = {bucket.date(): count for bucket, count in counts.items()}
    # A period without events is a true zero, so it is returned rather than left out.
    points = [
        SeriesPoint(bucket=bucket, count=by_day.get(bucket, 0))
        for bucket in _buckets(start, end, granularity)
    ]
    return sum(by_day.values()), points


async def overview(db: AsyncSession, va_id: UUID | None) -> OverviewOut:
    total_visits = await events.count(db, ProfileVisit, va_id)
    total_clicks = await events.count(db, ClickEvent, va_id)
    va_count, active_va_count = await vas.counts(db)
    activity = [
        Activity(
            type=kind,
            va_username=row.va_username,
            occurred_at=row.occurred_at,
            referer_domain=row.referer_domain,
        )
        for kind, model in (("click", ClickEvent), ("visit", ProfileVisit))
        for row in await events.recent(db, model, va_id, RECENT_LIMIT)
    ]
    activity.sort(key=lambda a: a.occurred_at, reverse=True)
    return OverviewOut(
        total_visits=total_visits,
        total_clicks=total_clicks,
        conversion_rate=round(total_clicks / total_visits, 4) if total_visits else None,
        va_count=va_count,
        active_va_count=active_va_count,
        recent_activity=activity[:RECENT_LIMIT],
    )


async def visits(
    db: AsyncSession,
    va_id: UUID | None,
    granularity: Granularity,
    start: date | None,
    end: date | None,
) -> VisitsOut:
    first, last = _resolve_range(start, end)
    total, series = await _series(db, ProfileVisit, va_id, granularity, first, last)
    return VisitsOut(
        granularity=granularity, timezone=events.TIMEZONE, total=total, series=series
    )


async def clicks(
    db: AsyncSession,
    va_id: UUID | None,
    granularity: Granularity,
    start: date | None,
    end: date | None,
    limit: int,
    offset: int,
) -> ClicksOut:
    first, last = _resolve_range(start, end)
    total, series = await _series(db, ClickEvent, va_id, granularity, first, last)
    rows = await events.click_history(db, va_id, *_bounds(first, last), limit, offset)
    return ClicksOut(
        granularity=granularity,
        timezone=events.TIMEZONE,
        total=total,
        series=series,
        history=[
            ClickEntry(
                va_username=row.va_username,
                clicked_at=row.clicked_at,
                referer_domain=row.referer_domain,
                user_agent=row.user_agent,
            )
            for row in rows
        ],
    )
