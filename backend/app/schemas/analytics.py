from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel

Granularity = Literal["day", "week", "month"]


class Activity(BaseModel):
    type: Literal["click", "visit"]
    occurred_at: datetime
    referer_domain: str | None


class OverviewOut(BaseModel):
    total_visits: int
    total_clicks: int
    conversion_rate: float | None
    profile_is_active: bool
    link_is_active: bool
    public_url: str
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
    clicked_at: datetime
    referer_domain: str | None
    user_agent: str | None


class ClicksOut(VisitsOut):
    history: list[ClickEntry]
