import pytest
from sqlalchemy import select

from app.services.admins import AdminError, create_admin, reset_password
from app.core.db import SessionLocal
from app.models import AuthSession, User
from tests.conftest import ADMIN_EMAIL, ADMIN_PASSWORD

NEW_PASSWORD = "another-long-password"


async def test_create_admin_stores_an_argon2id_hash():
    await create_admin("Boss@Example.com", ADMIN_PASSWORD)

    async with SessionLocal() as db:
        user = await db.scalar(select(User))
    assert user.email == "boss@example.com"
    assert user.password_hash.startswith("$argon2id$")
    assert ADMIN_PASSWORD not in user.password_hash


async def test_create_admin_refuses_duplicates():
    await create_admin(ADMIN_EMAIL, ADMIN_PASSWORD)

    with pytest.raises(AdminError, match="existe déjà"):
        await create_admin(ADMIN_EMAIL, ADMIN_PASSWORD)


@pytest.mark.parametrize(
    "email,password",
    [("not-an-email", ADMIN_PASSWORD), (ADMIN_EMAIL, "short"), (ADMIN_EMAIL, "x" * 129)],
)
async def test_create_admin_refuses_bad_input(email, password):
    with pytest.raises(AdminError):
        await create_admin(email, password)


async def test_reset_password_replaces_it_and_closes_sessions(admin, anonymous):
    await reset_password(ADMIN_EMAIL, NEW_PASSWORD)

    async with SessionLocal() as db:
        assert await db.scalar(select(AuthSession)) is None
    old = await anonymous.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
    )
    new = await anonymous.post(
        "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": NEW_PASSWORD}
    )
    assert old.status_code == 401
    assert new.status_code == 200


async def test_reset_password_needs_an_existing_account():
    with pytest.raises(AdminError, match="Aucun compte"):
        await reset_password("nobody@example.com", NEW_PASSWORD)
