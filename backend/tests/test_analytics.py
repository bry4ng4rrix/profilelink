from datetime import UTC, date, datetime, timedelta

from sqlalchemy import insert, select

from app.core.db import SessionLocal
from app.models import ClickEvent, Profile, ProfileVisit
from app.services import revalidate
from app.services.analytics import LOCAL_TZ
from tests.conftest import add_link

OVERVIEW = "/api/v1/owner/analytics/overview"
CLICKS = "/api/v1/owner/analytics/clicks"
VISITS = "/api/v1/owner/analytics/visits"


async def profile_id():
    async with SessionLocal() as db:
        return await db.scalar(select(Profile.id))


async def seed(model, times: list[datetime]) -> None:
    pid = await profile_id()
    column = "clicked_at" if model is ClickEvent else "visited_at"
    async with SessionLocal() as db:
        await db.execute(
            insert(model),
            [{"profile_id": pid, column: moment, "ip_hash": "a" * 64} for moment in times],
        )
        await db.commit()


async def test_overview_starts_empty_without_invented_data(owner):
    body = (await owner.get(OVERVIEW)).json()

    assert body["total_visits"] == 0
    assert body["total_clicks"] == 0
    assert body["conversion_rate"] is None
    assert body["recent_activity"] == []
    assert body["link_is_active"] is False
    assert body["profile_is_active"] is True


async def test_overview_counts_real_events(owner, visitor):
    await add_link(owner)
    for _ in range(4):
        await visitor.post("/api/v1/public/profiles/bryan/visit?ref=google.com")
    await visitor.get("/r/bryan?ref=l.instagram.com")

    body = (await owner.get(OVERVIEW)).json()

    assert body["total_visits"] == 4
    assert body["total_clicks"] == 1
    assert body["conversion_rate"] == 0.25
    assert body["link_is_active"] is True
    assert body["recent_activity"][0]["type"] == "click"
    assert body["recent_activity"][0]["referer_domain"] == "l.instagram.com"
    assert len(body["recent_activity"]) == 5


async def test_conversion_rate_is_not_clamped(owner, visitor):
    await add_link(owner)
    await visitor.post("/api/v1/public/profiles/bryan/visit")
    await visitor.get("/r/bryan")
    await visitor.get("/r/bryan")

    assert (await owner.get(OVERVIEW)).json()["conversion_rate"] == 2.0


async def test_recent_activity_is_limited_to_ten(owner, visitor):
    for _ in range(12):
        await visitor.post("/api/v1/public/profiles/bryan/visit")

    assert len((await owner.get(OVERVIEW)).json()["recent_activity"]) == 10


async def test_daily_series_is_zero_filled(owner):
    await seed(ClickEvent, [datetime(2026, 3, 2, 9, tzinfo=UTC), datetime(2026, 3, 4, 9, tzinfo=UTC)])

    body = (await owner.get(f"{CLICKS}?from=2026-03-01&to=2026-03-04")).json()

    assert body["total"] == 2
    assert body["timezone"] == "Indian/Antananarivo"
    assert body["series"] == [
        {"bucket": "2026-03-01", "count": 0},
        {"bucket": "2026-03-02", "count": 1},
        {"bucket": "2026-03-03", "count": 0},
        {"bucket": "2026-03-04", "count": 1},
    ]


async def test_days_follow_madagascar_time_not_utc(owner):
    # 22:30 UTC on 1 March is already 01:30 on 2 March in Antananarivo.
    await seed(ProfileVisit, [datetime(2026, 3, 1, 22, 30, tzinfo=UTC)])

    body = (await owner.get(f"{VISITS}?from=2026-03-01&to=2026-03-02")).json()

    assert body["series"] == [
        {"bucket": "2026-03-01", "count": 0},
        {"bucket": "2026-03-02", "count": 1},
    ]


async def test_range_bounds_use_local_days(owner):
    just_inside = datetime(2026, 3, 1, 21, 30, tzinfo=UTC)  # 00:30 on 2 March locally
    just_outside = datetime(2026, 3, 2, 21, 30, tzinfo=UTC)  # 00:30 on 3 March locally
    await seed(ClickEvent, [just_inside, just_outside])

    body = (await owner.get(f"{CLICKS}?from=2026-03-02&to=2026-03-02")).json()

    assert body["total"] == 1
    assert len(body["history"]) == 1


async def test_weekly_series_starts_on_monday(owner):
    await seed(ClickEvent, [datetime(2026, 3, 4, 9, tzinfo=UTC), datetime(2026, 3, 11, 9, tzinfo=UTC)])

    body = (await owner.get(f"{CLICKS}?granularity=week&from=2026-03-02&to=2026-03-15")).json()

    assert body["series"] == [
        {"bucket": "2026-03-02", "count": 1},
        {"bucket": "2026-03-09", "count": 1},
    ]


async def test_monthly_series_spans_years(owner):
    await seed(ProfileVisit, [datetime(2026, 1, 15, 9, tzinfo=UTC)])

    body = (await owner.get(f"{VISITS}?granularity=month&from=2025-12-10&to=2026-02-01")).json()

    assert body["series"] == [
        {"bucket": "2025-12-01", "count": 0},
        {"bucket": "2026-01-01", "count": 1},
        {"bucket": "2026-02-01", "count": 0},
    ]


async def test_default_range_is_thirty_days_ending_today(owner):
    body = (await owner.get(VISITS)).json()

    today = datetime.now(LOCAL_TZ).date()
    assert len(body["series"]) == 30
    assert body["series"][-1]["bucket"] == today.isoformat()
    assert date.fromisoformat(body["series"][0]["bucket"]) == today - timedelta(days=29)


async def test_click_history_is_paginated_and_hides_the_ip_hash(owner):
    base = datetime(2026, 3, 2, 9, tzinfo=UTC)
    await seed(ClickEvent, [base + timedelta(minutes=i) for i in range(3)])

    page = await owner.get(f"{CLICKS}?from=2026-03-01&to=2026-03-03&limit=2&offset=1")

    history = page.json()["history"]
    assert [item["clicked_at"] for item in history] == [
        "2026-03-02T09:01:00Z",
        "2026-03-02T09:00:00Z",
    ]
    assert "ip_hash" not in page.text


async def test_invalid_analytics_parameters(owner):
    assert (await owner.get(f"{CLICKS}?granularity=hour")).status_code == 422
    assert (await owner.get(f"{CLICKS}?from=2026-03-02&to=2026-03-01")).status_code == 422
    assert (await owner.get(f"{VISITS}?from=2000-01-01&to=2026-01-01")).status_code == 422
    assert (await owner.get(f"{CLICKS}?limit=1000")).status_code == 422


async def test_revalidation_failure_is_not_fatal(monkeypatch, caplog):
    monkeypatch.undo()
    monkeypatch.setattr("app.core.config.settings.frontend_internal_url", "http://127.0.0.1:9")

    await revalidate.notify("bryan")

    assert "revalidate_failed" in caplog.text
