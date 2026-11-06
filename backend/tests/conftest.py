import os
import socket
import tempfile
from collections.abc import AsyncIterator, Awaitable, Callable

os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+asyncpg://profilelink:profilelink@localhost:5433/profilelink_test",
    ),
    IP_HASH_KEY="test-ip-key",
    REVALIDATE_SECRET="test-revalidate-secret",
    FRONTEND_ORIGIN="https://profil.test",
    API_PUBLIC_URL="https://api.profil.test",
    MEDIA_DIR=tempfile.mkdtemp(prefix="profilelink-media-"),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.services import destinations, revalidate  # noqa: E402

PASSWORD = "correct-horse-battery"
BASE_URL = "http://api.profil.test"

Client = httpx.AsyncClient
OwnerFactory = Callable[..., Awaitable[Client]]


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    config = Config("alembic.ini")
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
async def clean_database() -> AsyncIterator[None]:
    yield
    async with engine.begin() as connection:
        await connection.execute(text("TRUNCATE users CASCADE"))


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


def _client(**headers: str) -> Client:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.7", 1234)),
        base_url=BASE_URL,
        headers={"Origin": settings.frontend_origin, **headers},
        follow_redirects=False,
    )


@pytest.fixture
async def visitor() -> AsyncIterator[Client]:
    """No cookie, and no Origin header either: this is a plain browser navigation."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, client=("203.0.113.7", 1234)),
        base_url=BASE_URL,
        follow_redirects=False,
    ) as client:
        yield client


@pytest.fixture
async def anonymous() -> AsyncIterator[Client]:
    """Sends the allowed Origin but no session."""
    async with _client() as client:
        yield client


@pytest.fixture
async def owner_factory() -> AsyncIterator[OwnerFactory]:
    clients: list[Client] = []

    async def create(username: str = "bryan", email: str | None = None) -> Client:
        client = _client()
        clients.append(client)
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email or f"{username}@example.com",
                "password": PASSWORD,
                "password_confirm": PASSWORD,
                "username": username,
            },
        )
        assert response.status_code == 201, response.text
        return client

    yield create
    for client in clients:
        await client.aclose()


@pytest.fixture
async def owner(owner_factory: OwnerFactory) -> Client:
    return await owner_factory()


async def add_link(client: Client, url: str = "https://destination.example.com/page") -> dict:
    response = await client.post("/api/v1/owner/links", json={"destination_url": url})
    assert response.status_code == 201, response.text
    return response.json()
