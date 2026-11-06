from datetime import UTC, date, datetime, timedelta

from sqlalchemy import insert, select

from app.core.db import SessionLocal
from app.models import ClickEvent, ProfileVisit, VaProfile
from app.services import revalidate
from app.services.analytics import LOCAL_TZ
from tests.conftest import ADMIN, client, create_va

OVERVIEW = "/api/v1/admin/analytics/overview"
CLICKS = "/api/v1/admin/analytics/clicks"
VISITS = "/api/v1/admin/analytics/visits"


async def click_from(ip: str, username: str = "bryan") -> None:
    """Another person: another address, and a browser with no cookie yet."""
    async with client() as person:
        await person.get(f"/r/{username}", headers={"X-Real-IP": ip})


async def first_va_id():
    async with SessionLocal() as db:
        return await db.scalar(select(VaProfile.id))


async def seed(model, times: list[datetime], va_id=None) -> None:
    va_id = va_id or await first_va_id()
    column = "clicked_at" if model is ClickEvent else "visited_at"
    async with SessionLocal() as db:
        await db.execute(
            insert(model),
            [{"va_profile_id": va_id, column: moment, "ip_hash": "a" * 64} for moment in times],
        )
        await db.commit()


async def test_overview_starts_empty_without_invented_data(admin):
    body = (await admin.get(OVERVIEW)).json()

    assert body == {
        "total_visits": 0,
        "total_clicks": 0,
        "conversion_rate": None,
        "va_count": 0,
        "active_va_count": 0,
        "recent_activity": [],
    }


async def test_overview_covers_all_vas(admin, visitor):
    await create_va(admin, first_name="Bryan")
    marie = await create_va(admin, first_name="Marie")
    await admin.patch(f"{ADMIN}/{marie['id']}/status", json={"is_active": False})
    for _ in range(4):
        await visitor.post("/api/v1/public/profiles/bryan/visit?ref=google.com")
    await visitor.get("/r/bryan?ref=l.instagram.com")

    body = (await admin.get(OVERVIEW)).json()

    assert body["total_visits"] == 4
    assert body["total_clicks"] == 1
    assert body["conversion_rate"] == 0.25
    assert (body["va_count"], body["active_va_count"]) == (2, 1)
    assert body["recent_activity"][0]["type"] == "click"
    assert body["recent_activity"][0]["va_username"] == "bryan"
    assert body["recent_activity"][0]["referer_domain"] == "l.instagram.com"
    assert len(body["recent_activity"]) == 5


async def test_statistics_can_be_scoped_to_one_va(admin, visitor):
    bryan = await create_va(admin, first_name="Bryan")
    marie = await create_va(admin, first_name="Marie")
    await click_from("198.51.100.1")
    await click_from("198.51.100.2")
    await click_from("198.51.100.3", "marie")

    every = (await admin.get(OVERVIEW)).json()
    only_marie = (await admin.get(f"{OVERVIEW}?va_id={marie['id']}")).json()
    clicks = (await admin.get(f"{CLICKS}?va_id={bryan['id']}")).json()

    assert every["total_clicks"] == 3
    assert only_marie["total_clicks"] == 1
    assert only_marie["recent_activity"][0]["va_username"] == "marie"
    assert clicks["total"] == 2
    assert {row["va_username"] for row in clicks["history"]} == {"bryan"}


async def test_conversion_rate_is_not_clamped(admin, visitor):
    await create_va(admin)
    await visitor.post("/api/v1/public/profiles/bryan/visit")
    await click_from("198.51.100.1")
    await click_from("198.51.100.2")

    assert (await admin.get(OVERVIEW)).json()["conversion_rate"] == 2.0


async def test_recent_activity_is_limited_to_ten(admin, visitor):
    await create_va(admin)
    for _ in range(12):
        await visitor.post("/api/v1/public/profiles/bryan/visit")

    assert len((await admin.get(OVERVIEW)).json()["recent_activity"]) == 10


async def test_daily_series_is_zero_filled(admin):
    await create_va(admin)
    await seed(
        ClickEvent, [datetime(2026, 3, 2, 9, tzinfo=UTC), datetime(2026, 3, 4, 9, tzinfo=UTC)]
    )

    body = (await admin.get(f"{CLICKS}?from=2026-03-01&to=2026-03-04")).json()

    assert body["total"] == 2
    assert body["timezone"] == "Indian/Antananarivo"
    assert body["series"] == [
        {"bucket": "2026-03-01", "count": 0},
        {"bucket": "2026-03-02", "count": 1},
        {"bucket": "2026-03-03", "count": 0},
        {"bucket": "2026-03-04", "count": 1},
    ]


async def test_days_follow_madagascar_time_not_utc(admin):
    await create_va(admin)
    # 22:30 UTC on 1 March is already 01:30 on 2 March in Antananarivo.
    await seed(ProfileVisit, [datetime(2026, 3, 1, 22, 30, tzinfo=UTC)])

    body = (await admin.get(f"{VISITS}?from=2026-03-01&to=2026-03-02")).json()

    assert body["series"] == [
        {"bucket": "2026-03-01", "count": 0},
        {"bucket": "2026-03-02", "count": 1},
    ]


async def test_range_bounds_use_local_days(admin):
    await create_va(admin)
    just_inside = datetime(2026, 3, 1, 21, 30, tzinfo=UTC)  # 00:30 on 2 March locally
    just_outside = datetime(2026, 3, 2, 21, 30, tzinfo=UTC)  # 00:30 on 3 March locally
    await seed(ClickEvent, [just_inside, just_outside])

    body = (await admin.get(f"{CLICKS}?from=2026-03-02&to=2026-03-02")).json()

    assert body["total"] == 1
    assert len(body["history"]) == 1


async def test_weekly_series_starts_on_monday(admin):
    await create_va(admin)
    await seed(
        ClickEvent, [datetime(2026, 3, 4, 9, tzinfo=UTC), datetime(2026, 3, 11, 9, tzinfo=UTC)]
    )

    body = (await admin.get(f"{CLICKS}?granularity=week&from=2026-03-02&to=2026-03-15")).json()

    assert body["series"] == [
        {"bucket": "2026-03-02", "count": 1},
        {"bucket": "2026-03-09", "count": 1},
    ]


async def test_monthly_series_spans_years(admin):
    await create_va(admin)
    await seed(ProfileVisit, [datetime(2026, 1, 15, 9, tzinfo=UTC)])

    body = (await admin.get(f"{VISITS}?granularity=month&from=2025-12-10&to=2026-02-01")).json()

    assert body["series"] == [
        {"bucket": "2025-12-01", "count": 0},
        {"bucket": "2026-01-01", "count": 1},
        {"bucket": "2026-02-01", "count": 0},
    ]


async def test_default_range_is_thirty_days_ending_today(admin):
    body = (await admin.get(VISITS)).json()

    today = datetime.now(LOCAL_TZ).date()
    assert len(body["series"]) == 30
    assert body["series"][-1]["bucket"] == today.isoformat()
    assert date.fromisoformat(body["series"][0]["bucket"]) == today - timedelta(days=29)


async def test_click_history_is_paginated_and_hides_the_ip_hash(admin):
    await create_va(admin)
    base = datetime(2026, 3, 2, 9, tzinfo=UTC)
    await seed(ClickEvent, [base + timedelta(minutes=i) for i in range(3)])

    page = await admin.get(f"{CLICKS}?from=2026-03-01&to=2026-03-03&limit=2&offset=1")

    history = page.json()["history"]
    assert [item["clicked_at"] for item in history] == [
        "2026-03-02T09:01:00Z",
        "2026-03-02T09:00:00Z",
    ]
    assert history[0]["va_username"] == "bryan"
    assert "ip_hash" not in page.text


async def test_invalid_analytics_parameters(admin):
    assert (await admin.get(f"{CLICKS}?granularity=hour")).status_code == 422
    assert (await admin.get(f"{CLICKS}?from=2026-03-02&to=2026-03-01")).status_code == 422
    assert (await admin.get(f"{VISITS}?from=2000-01-01&to=2026-01-01")).status_code == 422
    assert (await admin.get(f"{CLICKS}?limit=1000")).status_code == 422
    assert (await admin.get(f"{OVERVIEW}?va_id=not-a-uuid")).status_code == 422


async def test_revalidation_failure_is_not_fatal(monkeypatch, caplog):
    monkeypatch.undo()
    monkeypatch.setattr("app.core.config.settings.frontend_internal_url", "http://127.0.0.1:9")

    await revalidate.notify("bryan")

    assert "revalidate_failed" in caplog.text
