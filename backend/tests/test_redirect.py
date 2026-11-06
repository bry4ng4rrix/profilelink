from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import ClickEvent
from tests.conftest import add_link

DESTINATION = "https://destination.example.com/page?a=1"
PROFILE_PAGE = f"{settings.frontend_origin}/bryan"


async def clicks() -> list[ClickEvent]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(ClickEvent))).all())


async def test_redirects_with_302_without_authentication(owner, visitor):
    await add_link(owner, DESTINATION)

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
    assert response.content == b""


async def test_redirect_is_never_cacheable(owner, visitor):
    await add_link(owner, DESTINATION)

    headers = (await visitor.get("/r/bryan")).headers

    assert headers["cache-control"] == "no-store"
    assert "noindex" in headers["x-robots-tag"]


async def test_click_is_recorded_with_ref(owner, visitor):
    await add_link(owner, DESTINATION)

    await visitor.get("/r/bryan?ref=l.instagram.com", headers={"User-Agent": "Test/1.0"})

    [click] = await clicks()
    assert click.referer_domain == "l.instagram.com"
    assert click.user_agent == "Test/1.0"
    assert len(click.ip_hash) == 64 and "203.0.113.7" not in click.ip_hash


async def test_changed_destination_applies_immediately(owner, visitor):
    link = await add_link(owner, DESTINATION)
    await visitor.get("/r/bryan")

    await owner.put(
        f"/api/v1/owner/links/{link['id']}",
        json={"destination_url": "https://other.example.com/"},
    )

    assert (await visitor.get("/r/bryan")).headers["location"] == "https://other.example.com/"


async def test_disabled_profile_returns_to_the_profile_page(owner, visitor):
    await add_link(owner, DESTINATION)
    await owner.patch("/api/v1/owner/profile/status", json={"is_active": False})

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == PROFILE_PAGE
    assert await clicks() == []


async def test_disabled_link_returns_to_the_profile_page(owner, visitor):
    link = await add_link(owner, DESTINATION)
    await owner.patch(f"/api/v1/owner/links/{link['id']}/status", json={"is_active": False})

    response = await visitor.get("/r/bryan")

    assert response.headers["location"] == PROFILE_PAGE
    assert await clicks() == []


async def test_deleted_link_returns_to_the_profile_page(owner, visitor):
    link = await add_link(owner, DESTINATION)
    await owner.delete(f"/api/v1/owner/links/{link['id']}")

    assert (await visitor.get("/r/bryan")).headers["location"] == PROFILE_PAGE


async def test_unknown_username_returns_to_the_frontend_404(visitor):
    response = await visitor.get("/r/nobody")

    assert response.status_code == 302
    assert response.headers["location"] == f"{settings.frontend_origin}/nobody"


async def test_malformed_username_is_404_and_cannot_steer_the_redirect(visitor):
    for path in ("/r/a", "/r/..%2Fevil", "/r/%0d%0aX-Injected:1", "/r/evil.test"):
        response = await visitor.get(path)
        assert response.status_code == 404, path
        assert "location" not in response.headers


async def test_query_string_cannot_change_the_destination(owner, visitor):
    await add_link(owner, DESTINATION)

    response = await visitor.get(
        "/r/bryan?url=https://evil.test&destination_url=https://evil.test&next=https://evil.test"
    )

    assert response.headers["location"] == DESTINATION


async def test_stats_failure_does_not_block_the_visitor(owner, visitor, monkeypatch):
    await add_link(owner, DESTINATION)

    async def failing_commit(self):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
