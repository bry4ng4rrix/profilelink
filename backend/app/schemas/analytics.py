from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Granularity = Literal["day", "week", "month"]


class Activity(BaseModel):
    type: Literal["click", "visit"]
    va_username: str
    occurred_at: datetime
    referer_domain: str | None


class OverviewOut(BaseModel):
    total_visits: int
    total_clicks: int
    conversion_rate: float | None
    va_count: int
    active_va_count: int
    recent_activity: list[Activity]


class SeriesPoint(BaseModel):
    bucket: date
    count: int


class VisitsOut(BaseModel):
    granularity: Granularity
    timezone: str
    total: int
    series: list[SeriesPoint]


class ClickEntry(BaseModel):
    va_username: str
    clicked_at: datetime
    referer_domain: str | None
    user_agent: str | None


class ClicksOut(VisitsOut):
    history: list[ClickEntry]
