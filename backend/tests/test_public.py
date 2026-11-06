from sqlalchemy import select, update

from app.core.db import SessionLocal
from app.core.security import hash_ip
from app.models import ProfileVisit, User
from app.schemas.profile import PublicProfileOut
from tests.conftest import add_link

PROFILE = "/api/v1/public/profiles/bryan"
PUBLIC_FIELDS = {
    "id", "username", "first_name", "last_name", "bio", "photo_url", "is_active", "link_available",
}


async def fill_profile(owner) -> None:
    response = await owner.put(
        "/api/v1/owner/profile",
        json={"username": "bryan", "first_name": "Bryan", "last_name": "Rakoto", "bio": "Bio"},
    )
    assert response.status_code == 200


async def test_visitor_reads_a_profile_without_cookie_or_jwt(owner, visitor):
    await fill_profile(owner)

    response = await visitor.get(PROFILE)

    assert response.status_code == 200
    body = response.json()
    assert set(body) == PUBLIC_FIELDS
    assert body["first_name"] == "Bryan" and body["is_active"] is True


async def test_username_is_case_insensitive(owner, visitor):
    assert (await visitor.get("/api/v1/public/profiles/BRYAN")).status_code == 200


async def test_unknown_or_malformed_username_is_404(visitor):
    assert (await visitor.get("/api/v1/public/profiles/nobody")).status_code == 404
    assert (await visitor.get("/api/v1/public/profiles/a")).status_code == 404


async def test_link_available_follows_the_link_state(owner, visitor):
    assert (await visitor.get(PROFILE)).json()["link_available"] is False

    link = await add_link(owner)
    assert (await visitor.get(PROFILE)).json()["link_available"] is True

    await owner.patch(f"/api/v1/owner/links/{link['id']}/status", json={"is_active": False})
    assert (await visitor.get(PROFILE)).json()["link_available"] is False


async def test_disabled_profile_exposes_nothing_personal(owner, visitor):
    await fill_profile(owner)
    await add_link(owner)
    await owner.patch("/api/v1/owner/profile/status", json={"is_active": False})

    response = await visitor.get(PROFILE)

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False and body["link_available"] is False
    assert body["first_name"] is None and body["bio"] is None and body["photo_url"] is None


async def test_suspended_account_is_treated_as_disabled(owner, visitor):
    await fill_profile(owner)
    async with SessionLocal() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()

    assert (await visitor.get(PROFILE)).json()["is_active"] is False


async def test_public_schema_is_an_allow_list():
    assert set(PublicProfileOut.model_fields) == PUBLIC_FIELDS


async def test_visit_is_recorded_with_hashed_ip_and_clean_domain(owner, visitor):
    response = await visitor.post(
        f"{PROFILE}/visit?ref=L.Instagram.com", headers={"User-Agent": "UA/" + "x" * 600}
    )

    assert response.status_code == 204
    async with SessionLocal() as db:
        visit = await db.scalar(select(ProfileVisit))
    assert visit.referer_domain == "l.instagram.com"
    assert visit.ip_hash == hash_ip("203.0.113.7")
    assert len(visit.user_agent) == 512


async def test_nginx_real_ip_header_is_used_for_the_hash(owner, visitor):
    await visitor.post(f"{PROFILE}/visit", headers={"X-Real-IP": "198.51.100.9"})

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit.ip_hash)) == hash_ip("198.51.100.9")


async def test_invalid_ref_is_dropped(owner, visitor):
    await visitor.post(f"{PROFILE}/visit?ref=https://evil.test/path%0d%0aX:1")

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit.referer_domain)) is None


async def test_visit_to_unknown_or_disabled_profile_records_nothing(owner, visitor):
    await owner.patch("/api/v1/owner/profile/status", json={"is_active": False})

    assert (await visitor.post(f"{PROFILE}/visit")).status_code == 204
    assert (await visitor.post("/api/v1/public/profiles/nobody/visit")).status_code == 204

    async with SessionLocal() as db:
        assert await db.scalar(select(ProfileVisit)) is None


async def test_sitemap_lists_active_profiles_only(owner_factory, visitor):
    await owner_factory("bryan")
    hidden = await owner_factory("hidden")
    await hidden.patch("/api/v1/owner/profile/status", json={"is_active": False})

    body = (await visitor.get("/api/v1/public/sitemap")).json()

    assert [entry["username"] for entry in body] == ["bryan"]
    assert set(body[0]) == {"username", "updated_at"}


async def test_health(visitor):
    response = await visitor.get("/health")

    assert (response.status_code, response.json()) == (200, {"status": "ok"})
