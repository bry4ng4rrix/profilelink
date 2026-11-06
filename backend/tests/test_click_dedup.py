from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.api.redirect import VISITOR_COOKIE
from app.core.db import SessionLocal
from app.core.security import hash_ip, hash_token
from app.models import ClickEvent
from app.repositories import events
from tests.conftest import DESTINATION, client, create_va

ALICE = {"X-Real-IP": "198.51.100.1"}
BOB = {"X-Real-IP": "198.51.100.2"}


async def clicks() -> list[ClickEvent]:
    async with SessionLocal() as db:
        return list((await db.scalars(select(ClickEvent))).all())


async def test_the_same_person_is_counted_once_but_always_redirected(admin, visitor):
    await create_va(admin)

    for _ in range(3):
        response = await visitor.get("/r/bryan", headers=ALICE)
        assert response.status_code == 302
        assert response.headers["location"] == DESTINATION

    assert len(await clicks()) == 1


async def test_two_browsers_on_the_same_address_count_once(admin):
    await create_va(admin)

    async with client() as phone, client() as computer:
        await phone.get("/r/bryan", headers=ALICE)
        await computer.get("/r/bryan", headers=ALICE)

    assert len(await clicks()) == 1


async def test_the_same_browser_on_another_network_counts_once(admin, visitor):
    await create_va(admin)

    await visitor.get("/r/bryan", headers=ALICE)
    await visitor.get("/r/bryan", headers=BOB)

    assert len(await clicks()) == 1


async def test_two_different_people_count_twice(admin):
    await create_va(admin)

    async with client() as alice, client() as bob:
        await alice.get("/r/bryan", headers=ALICE)
        await bob.get("/r/bryan", headers=BOB)

    assert len(await clicks()) == 2


async def test_the_same_phone_model_is_not_mistaken_for_the_same_person(admin):
    await create_va(admin)
    iphone = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Instagram 300.0"

    async with client() as alice, client() as bob:
        await alice.get("/r/bryan", headers=ALICE | {"User-Agent": iphone})
        await bob.get("/r/bryan", headers=BOB | {"User-Agent": iphone})

    assert len(await clicks()) == 2


async def test_each_va_counts_separately(admin, visitor):
    await create_va(admin, first_name="Bryan")
    await create_va(admin, first_name="Marie")

    await visitor.get("/r/bryan", headers=ALICE)
    await visitor.get("/r/marie", headers=ALICE)

    assert len(await clicks()) == 2


async def test_clicks_recorded_before_this_rule_still_count_by_address(admin, visitor):
    await create_va(admin)
    await visitor.get("/r/bryan", headers=ALICE)
    async with SessionLocal() as db:
        (await db.scalar(select(ClickEvent))).visitor_hash = None
        await db.commit()

    async with client() as fresh:
        await fresh.get("/r/bryan", headers=ALICE)

    assert len(await clicks()) == 1


async def test_the_cookie_is_protected_and_only_its_hash_is_stored(admin, visitor):
    await create_va(admin)

    response = await visitor.get("/r/bryan", headers=ALICE)

    cookie = response.headers["set-cookie"]
    assert cookie.startswith(f"{VISITOR_COOKIE}=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Max-Age=31536000" in cookie
    token = response.cookies[VISITOR_COOKIE]
    [click] = await clicks()
    assert click.visitor_hash == hash_token(token)
    assert click.ip_hash == hash_ip("198.51.100.1")


async def test_the_cookie_stays_the_same_across_clicks(admin, visitor):
    await create_va(admin)

    first = await visitor.get("/r/bryan")
    second = await visitor.get("/r/bryan")

    assert first.cookies[VISITOR_COOKIE] == second.cookies[VISITOR_COOKIE]


async def test_a_visitor_who_does_not_click_gets_no_cookie(admin, visitor):
    await create_va(admin)

    page = await visitor.get("/api/v1/public/profiles/bryan")
    visit = await visitor.post("/api/v1/public/profiles/bryan/visit")

    assert "set-cookie" not in page.headers
    assert "set-cookie" not in visit.headers


async def test_no_cookie_when_there_is_nowhere_to_go(visitor):
    response = await visitor.get("/r/nobody")

    assert "set-cookie" not in response.headers


async def test_a_counting_failure_does_not_block_the_visitor(admin, visitor, monkeypatch):
    await create_va(admin)

    async def failing(*args):
        raise SQLAlchemyError("database unavailable")

    monkeypatch.setattr(events, "click_seen", failing)

    response = await visitor.get("/r/bryan")

    assert response.status_code == 302
    assert response.headers["location"] == DESTINATION
