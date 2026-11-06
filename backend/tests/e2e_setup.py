"""Prepares the Playwright database: empty schema, migrations, one administrator."""

import asyncio
import os

from alembic import command
from alembic.config import Config
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.cli import create_admin
from app.core.config import settings
from app.core.db import engine


async def empty_schema() -> None:
    assert settings.database_url.endswith("_test"), "refusing to wipe a non-test database"
    target = create_async_engine(settings.database_url, poolclass=pool.NullPool)
    async with target.begin() as connection:
        await connection.execute(text("DROP SCHEMA public CASCADE"))
        await connection.execute(text("CREATE SCHEMA public"))
    await target.dispose()


async def add_admin() -> None:
    await create_admin(os.environ["E2E_ADMIN_EMAIL"], os.environ["E2E_ADMIN_PASSWORD"])
    await engine.dispose()


asyncio.run(empty_schema())
command.upgrade(Config("alembic.ini"), "head")
asyncio.run(add_admin())
