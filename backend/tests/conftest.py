import asyncio
import os
import socket
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable
from io import BytesIO

os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://profilelink:profilelink@localhost:5433/profilelink_test",
    ),
    IP_HASH_KEY="test-ip-key",
    REVALIDATE_SECRET="test-revalidate-secret",
    REGISTRATION_TOKEN="",  # never inherited from the developer's .env
    FRONTEND_ORIGIN="https://profil.test",
    API_PUBLIC_URL="https://api.profil.test",
    MEDIA_DIR=tempfile.mkdtemp(prefix="profilelink-media-"),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from PIL import Image  # noqa: E402
from sqlalchemy import pool, text  # noqa: E402
from sqlalchemy.ext.asyncio import create_async_engine  # noqa: E402

from app.cli import create_admin  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import destinations, revalidate  # noqa: E402

ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD = "correct-horse-battery"
BASE_URL = "http://api.profil.test"
DESTINATION = "https://destination.example.com/page"
INSTAGRAM = "https://www.instagram.com/bryan.rakoto"

Client = httpx.AsyncClient
ADMIN = "/api/v1/admin/vas"


def alembic_config() -> Config:
    return Config("alembic.ini")


async def _empty_schema() -> None:
    target = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with target.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await target.dispose()


def reset_database() -> None:
    assert settings.database_url.endswith("_test"), "refusing to wipe a non-test database"
    asyncio.run(_empty_schema())


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    reset_database()
    command.upgrade(alembic_config(), "head")


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    yield
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE users, va_profiles CASCADE"))


@pytest.fixture(autouse=True)
def fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    async def resolve(host: str, port: int) -> list[str]:
        if host == "internal.example.com":
            return ["93.184.216.34", "10.0.0.5"]
        if host == "metadata.example.com":
            return ["169.254.169.254"]
        if host == "missing.example.com":
            raise socket.gaierror("not found")
        return ["93.184.216.34"]

    monkeypatch.setattr(destinations, "resolve_host", resolve)


@pytest.fixture(autouse=True)
def revalidated(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, ...]]:
    calls: list[tuple[str, ...]] = []

    async def record(*usernames: str) -> None:
        calls.append(usernames)

    monkeypatch.setattr(revalidate, "notify", record)
    return calls


def client(**headers: str) -> Client:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.7", 1234)),
        base_url=BASE_URL,
        headers=headers,
        follow_redirects=False,
    )


@pytest.fixture
async def visitor() -> AsyncIterator[Client]:
    """No cookie and no Origin header: a plain browser navigation."""
    async with client() as instance:
        yield instance


@pytest.fixture
async def anonymous() -> AsyncIterator[Client]:
    """Sends the allowed Origin, but has no session."""
    async with client(Origin=settings.frontend_origin) as instance:
        yield instance


@pytest.fixture
async def admin() -> AsyncIterator[Client]:
    await create_admin(ADMIN_EMAIL, ADMIN_PASSWORD)
    async with client(Origin=settings.frontend_origin) as instance:
        response = await instance.post(
            "/api/v1/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200, response.text
        yield instance


def image_bytes(fmt: str = "PNG", size: tuple[int, int] = (800, 600), **options) -> bytes:
    output = BytesIO()
    Image.new("RGB", size, "red").save(output, fmt, **options)
    return output.getvalue()


def photo_file(data: bytes | None = None, content_type: str = "image/png") -> tuple:
    return ("photo.png", image_bytes() if data is None else data, content_type)


async def post_va(admin: Client, photo: bytes | None = None, **fields) -> httpx.Response:
    values = {
        "first_name": "Bryan",
        "last_name": "Rakoto",
        "age": 27,
        "instagram_url": INSTAGRAM,
        "destination_url": DESTINATION,
    } | fields
    return await admin.post(ADMIN, data=values, files={"photo": photo_file(photo)})


CreateVa = Callable[..., Awaitable[dict]]


async def create_va(admin: Client, **fields) -> dict:
    response = await post_va(admin, **fields)
    assert response.status_code == 201, response.text
    return response.json()
