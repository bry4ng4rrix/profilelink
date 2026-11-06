from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.core.db import SessionLocal, utcnow
from app.models import AuthSession, User
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD, create_va

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"


async def test_there_is_no_public_registration(anonymous):
    for path in ("/api/v1/auth/register", "/api/v1/register", "/register"):
        response = await anonymous.post(
            path,
            json={
                "email": "new@example.com",
                "password": "a-long-enough-password",
                "password_confirm": "a-long-enough-password",
                "username": "newcomer",
            },
        )
        assert response.status_code in (403, 404, 405), path

    async with SessionLocal() as db:
        assert await db.scalar(select(User)) is None


async def test_login_sets_a_protected_session_cookie(admin, anonymous):
    response = await anonymous.post(LOGIN, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert response.status_code == 200
    assert response.json()["email"] == ADMIN_EMAIL
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie


async def test_login_ignores_email_case(admin, anonymous):
    response = await anonymous.post(
        LOGIN, json={"email": ADMIN_EMAIL.upper(), "password": ADMIN_PASSWORD}
    )

    assert response.status_code == 200
    assert (await anonymous.get(ME)).json()["email"] == ADMIN_EMAIL


@pytest.mark.parametrize(
    "email,password",
    [(ADMIN_EMAIL, "wrong-password"), ("unknown@example.com", ADMIN_PASSWORD)],
)
async def test_login_failures_are_indistinguishable(admin, anonymous, email, password):
    response = await anonymous.post(LOGIN, json={"email": email, "password": password})

    assert response.status_code == 401
    assert response.json()["detail"] == "invalid_credentials"


async def test_a_va_can_never_log_in(admin, anonymous):
    va = await create_va(admin)

    for password in ("", "bryan", va["username"], ADMIN_PASSWORD):
        response = await anonymous.post(
            LOGIN, json={"email": "bryan@example.com", "password": password}
        )
        assert response.status_code == 401


async def test_creating_a_va_creates_no_account(admin):
    await create_va(admin)

    async with SessionLocal() as db:
        accounts = (await db.scalars(select(User.email))).all()
    assert accounts == [ADMIN_EMAIL]


async def test_suspended_admin_cannot_log_in_and_loses_sessions(admin, anonymous):
    async with SessionLocal() as db:
        await db.execute(update(User).values(is_active=False))
        await db.commit()

    login = await anonymous.post(LOGIN, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    assert login.status_code == 401
    assert (await admin.get(ME)).status_code == 401


async def test_logout_revokes_the_session_on_the_server(admin):
    token = admin.cookies["pl_session"]

    assert (await admin.post("/api/v1/auth/logout")).status_code == 204

    admin.cookies.set("pl_session", token)
    assert (await admin.get(ME)).status_code == 401


async def test_refresh_rotates_the_token(admin):
    old_token = admin.cookies["pl_session"]

    response = await admin.post("/api/v1/auth/refresh")

    assert response.status_code == 200
    new_token = response.cookies["pl_session"]
    assert new_token != old_token
    admin.cookies.clear()
    admin.cookies.set("pl_session", old_token)
    assert (await admin.get(ME)).status_code == 401
    admin.cookies.clear()
    admin.cookies.set("pl_session", new_token)
    assert (await admin.get(ME)).status_code == 200


async def test_expired_session_is_refused(admin):
    async with SessionLocal() as db:
        await db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(seconds=1)))
        await db.commit()

    assert (await admin.get(ME)).status_code == 401


async def test_expired_sessions_are_purged_on_login(admin, anonymous):
    async with SessionLocal() as db:
        await db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(days=1)))
        await db.commit()

    await anonymous.post(LOGIN, json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})

    async with SessionLocal() as db:
        assert len((await db.scalars(select(AuthSession))).all()) == 1


async def test_only_the_token_hash_is_stored(admin):
    token = admin.cookies["pl_session"]

    async with SessionLocal() as db:
        stored = await db.scalar(select(AuthSession.token_hash))
    assert stored != token and len(stored) == 64
