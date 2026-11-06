from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import ClickEvent
from tests.conftest import ADMIN, create_va

DESTINATION = "https://destination.example.com/page?a=1"
PROFILE_PAGE = f"{settings.frontend_origin}/bryan"


async def clicks() -> list[ClickEvent]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(ClickEvent))).all())


async def test_redirects_with_302_without_authentication(admin, visitor):
    await create_va(admin, destination_url=DESTINATION)

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
    assert response.content == b""


async def test_redirect_is_never_cacheable(admin, visitor):
    await create_va(admin)

    headers = (await visitor.get("/r/bryan")).headers

    assert headers["cache-control"] == "no-store"
    assert "noindex" in headers["x-robots-tag"]


async def test_click_is_recorded_with_ref(admin, visitor):
    await create_va(admin)

    await visitor.get("/r/bryan?ref=l.instagram.com", headers={"User-Agent": "Test/1.0"})

    [click] = await clicks()
    assert click.referer_domain == "l.instagram.com"
    assert click.user_agent == "Test/1.0"
    assert len(click.ip_hash) == 64 and "203.0.113.7" not in click.ip_hash


async def test_changed_destination_applies_immediately(admin, visitor):
    va = await create_va(admin)
    await visitor.get("/r/bryan")

    await admin.put(
        f"{ADMIN}/{va['id']}/link", json={"destination_url": "https://other.example.com/"}
    )

    assert (await visitor.get("/r/bryan")).headers["location"] == "https://other.example.com/"


async def test_disabled_va_returns_to_its_page(admin, visitor):
    va = await create_va(admin)
    await admin.patch(f"{ADMIN}/{va['id']}/status", json={"is_active": False})

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == PROFILE_PAGE
    assert await clicks() == []


async def test_disabled_link_returns_to_the_page(admin, visitor):
    va = await create_va(admin)
    await admin.patch(f"{ADMIN}/{va['id']}/link/status", json={"is_active": False})

    response = await visitor.get("/r/bryan")

    assert response.headers["location"] == PROFILE_PAGE
    assert await clicks() == []


async def test_unknown_username_returns_to_the_frontend_404(visitor):
    response = await visitor.get("/r/nobody")

    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.frontend_origin}/nobody"


async def test_malformed_username_is_404_and_cannot_steer_the_redirect(visitor):
    for path in ("/r/a", "/r/..%2Fevil", "/r/%0d%0aX-Injected:1", "/r/evil.test"):
        response = await visitor.get(path)
        assert response.status_code == 404, path
        assert "location" not in response.headers


async def test_query_string_cannot_change_the_destination(admin, visitor):
    await create_va(admin, destination_url=DESTINATION)

    response = await visitor.get(
        "/r/bryan?url=https://evil.test&destination_url=https://evil.test&next=https://evil.test"
    )

    assert response.headers["location"] == DESTINATION


async def test_stats_failure_does_not_block_the_visitor(admin, visitor, monkeypatch):
    await create_va(admin, destination_url=DESTINATION)

    async def failing_commit(self):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
