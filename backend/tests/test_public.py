from sqlalchemy import select

from app.core.config import settings
from app.core.db import SessionLocal
from app.core.security import hash_ip
from app.models import ProfileVisit
from app.schemas.va import PublicProfileOut
from tests.conftest import ADMIN, DESTINATION, INSTAGRAM, create_va

PROFILE = "/api/v1/public/profiles/bryan"
PUBLIC_FIELDS = {
    "id",
    "username",
    "first_name",
    "last_name",
    "age",
    "photo_url",
    "is_active",
    "link_available",
}


async def test_visitor_reads_a_page_without_cookie_or_jwt(admin, visitor):
    await create_va(admin)

    response = await visitor.get(PROFILE)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == PUBLIC_FIELDS
    assert body["first_name"] == "Bryan"
    assert body["last_name"] == "Rakoto"
    assert body["age"] == 27
    assert body["is_active"] is True
    assert body["link_available"] is True


async def test_username_is_case_insensitive(admin, visitor):
    await create_va(admin)

    assert (await visitor.get("/api/v1/public/profiles/BRYAN")).status_code == 200


async def test_unknown_or_malformed_username_is_404(visitor):
    assert (await visitor.get("/api/v1/public/profiles/nobody")).status_code == 404
    assert (await visitor.get("/api/v1/public/profiles/a")).status_code == 404


async def test_link_available_follows_the_link_state(admin, visitor):
    va = await create_va(admin)

    await admin.patch(f"{ADMIN}/{va['id']}/link/status", json={"is_active": False})

    assert (await visitor.get(PROFILE)).json()["link_available"] is False


async def test_disabled_va_exposes_nothing_personal(admin, visitor):
    va = await create_va(admin)
    await admin.patch(f"{ADMIN}/{va['id']}/status", json={"is_active": False})

    response = await visitor.get(PROFILE)

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False and body["link_available"] is False
    for field in ("first_name", "last_name", "age", "photo_url"):
        assert body[field] is None, field


async def test_neither_link_reaches_the_public_json(admin, visitor):
    await create_va(admin)

    body = (await visitor.get(PROFILE)).text

    assert INSTAGRAM not in body and "instagram" not in body
    assert DESTINATION not in body and "destination" not in body


async def test_public_schema_is_an_allow_list():
    assert set(PublicProfileOut.model_fields) == PUBLIC_FIELDS


async def test_visit_is_recorded_with_hashed_ip_and_clean_domain(admin, visitor):
    await create_va(admin)

    response = await visitor.post(
        f"{PROFILE}/visit?ref=L.Instagram.com", headers={"User-Agent": "UA/" + "x" * 600}
    )

    assert response.status_code == 204
    async with SessionLocal() as db:
        visit = await db.scalar(select(ProfileVisit))
    assert visit.referer_domain == "l.instagram.com"
    assert visit.ip_hash == hash_ip("203.0.113.7")
    assert len(visit.user_agent) == 512


async def test_nginx_real_ip_header_is_used_for_the_hash(admin, visitor):
    await create_va(admin)

    await visitor.post(f"{PROFILE}/visit", headers={"X-Real-IP": "198.51.100.9"})

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit.ip_hash)) == hash_ip("198.51.100.9")


async def test_invalid_ref_is_dropped(admin, visitor):
    await create_va(admin)

    await visitor.post(f"{PROFILE}/visit?ref=https://evil.test/path%0d%0aX:1")

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit.referer_domain)) is None


async def test_visit_to_unknown_or_disabled_va_records_nothing(admin, visitor):
    va = await create_va(admin)
    await admin.patch(f"{ADMIN}/{va['id']}/status", json={"is_active": False})

    assert (await visitor.post(f"{PROFILE}/visit")).status_code == 204
    assert (await visitor.post("/api/v1/public/profiles/nobody/visit")).status_code == 204

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit)) is None


async def test_no_public_listing_of_the_vas_exists(admin, visitor):
    await create_va(admin)

    assert (await visitor.get("/api/v1/public/sitemap")).status_code == 404
    assert (await visitor.get("/api/v1/public/profiles")).status_code == 404


async def test_health(visitor):
    response = await visitor.get("/health")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})


async def test_frontend_origin_is_the_only_allowed_origin():
    assert settings.frontend_origin == "https://profil.test"
