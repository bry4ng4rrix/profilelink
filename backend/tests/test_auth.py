from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.db import SessionLocal, utcnow
from app.models import AuthSession, Profile, User
from tests.conftest import PASSWORD

REGISTER = "/api/v1/auth/register"
LOGIN = "/api/v1/auth/login"


def payload(**overrides) -> dict:
    return {
        "email": "bryan@example.com",
        "password": PASSWORD,
        "password_confirm": PASSWORD,
        "username": "bryan",
    } | overrides


async def test_register_creates_account_profile_and_session(anonymous):
    response = await anonymous.post(REGISTER, json=payload(email="Bryan@Example.com"))

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "bryan@example.com"
    assert body["username"] == "bryan"
    cookie = response.headers["set-cookie"]
    assert cookie.startswith("pl_session=")
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie

    me = await anonymous.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "bryan"


async def test_password_is_stored_as_argon2id(anonymous):
    await anonymous.post(REGISTER, json=payload())

    async with SessionLocal() as db:
        stored = await db.scalar(select(User.password_hash))
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


@pytest.mark.parametrize(
    "overrides",
    [
        {"password": "short", "password_confirm": "short"},
        {"password_confirm": "different-password"},
        {"email": "not-an-email"},
        {"username": "ab"},
        {"username": "_next"},
        {"username": "robots.txt"},
        {"password": "x" * 129, "password_confirm": "x" * 129},
    ],
)
async def test_register_rejects_invalid_input(anonymous, overrides):
    assert (await anonymous.post(REGISTER, json=payload(**overrides))).status_code == 422


@pytest.mark.parametrize("username", ["dashboard", "login", "register", "api", "conditions"])
async def test_register_rejects_reserved_usernames(anonymous, username):
    response = await anonymous.post(REGISTER, json=payload(username=username))

    assert response.status_code == 422
    assert response.json()["detail"] == "reserved_username"


async def test_register_rejects_duplicates(anonymous, owner_factory):
    await owner_factory("bryan", "bryan@example.com")

    same_email = await anonymous.post(REGISTER, json=payload(username="other"))
    same_username = await anonymous.post(REGISTER, json=payload(email="other@example.com"))

    assert (same_email.status_code, same_email.json()["detail"]) == (409, "email_taken")
    assert (same_username.status_code, same_username.json()["detail"]) == (409, "username_taken")


async def test_failed_registration_leaves_no_orphan_account(anonymous, owner_factory):
    await owner_factory("bryan", "bryan@example.com")

    await anonymous.post(REGISTER, json=payload(email="other@example.com"))

    async with SessionLocal() as db:
        assert await db.scalar(select(User).where(User.email == "other@example.com")) is None


async def test_login_with_valid_credentials(owner_factory, anonymous):
    await owner_factory()

    response = await anonymous.post(
        LOGIN, json={"email": "BRYAN@example.com", "password": PASSWORD}
    )

    assert response.status_code == 200
    assert (await anonymous.get("/api/v1/auth/me")).status_code == 200


@pytest.mark.parametrize(
    "email,password",
    [("bryan@example.com", "wrong-password"), ("unknown@example.com", PASSWORD)],
)
async def test_login_failures_are_indistinguishable(owner_factory, anonymous, email, password):
    await owner_factory()

    response = await anonymous.post(LOGIN, json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


async def test_suspended_account_cannot_login_and_loses_sessions(owner, anonymous):
    async with SessionLocal() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()

    login = await anonymous.post(LOGIN, json={"email": "bryan@example.com", "password": PASSWORD})

    assert login.status_code == 401
    assert (await owner.get("/api/v1/auth/me")).status_code == 401


async def test_logout_revokes_session_on_the_server(owner):
    token = owner.cookies["pl_session"]

    assert (await owner.post("/api/v1/auth/logout")).status_code == 204

    owner.cookies.set("pl_session", token)
    assert (await owner.get("/api/v1/auth/me")).status_code == 401


async def test_refresh_rotates_token_and_revokes_the_old_one(owner):
    old_token = owner.cookies["pl_session"]

    response = await owner.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    new_token = response.cookies["pl_session"]
    assert new_token != old_token
    owner.cookies.clear()
    owner.cookies.set("pl_session", old_token)
    assert (await owner.get("/api/v1/auth/me")).status_code == 401
    owner.cookies.clear()
    owner.cookies.set("pl_session", new_token)
    assert (await owner.get("/api/v1/auth/me")).status_code == 200


async def test_expired_session_is_refused(owner):
    async with SessionLocal() as db:
        await db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()

    assert (await owner.get("/api/v1/auth/me")).status_code == 401


async def test_expired_sessions_are_purged_on_login(owner, anonymous):
    async with SessionLocal() as db:
        await db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(days=1)))
        await db.commit()

    await anonymous.post(LOGIN, json={"email": "bryan@example.com", "password": PASSWORD})

    async with SessionLocal() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 1


async def test_only_the_token_hash_is_stored(owner):
    token = owner.cookies["pl_session"]

    async with SessionLocal() as db:
        stored = await db.scalar(select(AuthSession.token_hash))
    assert stored != token and len(stored) == 64


async def test_deleting_a_user_cascades(owner):
    from tests.conftest import add_link

    await add_link(owner)
    async with SessionLocal() as db:
        user = await db.scalar(select(User))
        await db.delete(user)
        await db.commit()
        assert await db.scalar(select(Profile)) is None
