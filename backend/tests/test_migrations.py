import asyncio

import pytest
from alembic import command
from sqlalchemy import pool, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from tests.conftest import alembic_config


def run_sql(statement: str) -> None:
    async def main() -> None:
        engine = create_async_engine(settings.database_url, poolclass=pool.NullPool)
        async with engine.begin() as connection:
            await connection.execute(text(statement))
        await engine.dispose()

    asyncio.run(main())


@pytest.fixture
def at_head():
    yield
    command.upgrade(alembic_config(), "head")


def test_migrations_run_both_ways(at_head):
    config = alembic_config()

    command.downgrade(config, "base")
    command.upgrade(config, "head")
    command.check(config)


def test_upgrade_refuses_to_turn_existing_accounts_into_admins(at_head):
    config = alembic_config()
    command.downgrade(config, "0001")
    run_sql("INSERT INTO users (email, password_hash) VALUES ('old@example.com', 'x')")

    with pytest.raises(RuntimeError, match="users contains rows"):
        command.upgrade(config, "head")

    run_sql("DELETE FROM users")


def test_downgrade_refuses_to_delete_vas(at_head):
    run_sql(
        "INSERT INTO va_profiles (username, first_name, last_name, age, instagram_url, photo_url) "
        "VALUES ('bryan', 'Bryan', 'Rakoto', 27, 'https://instagram.com/bryan', 'x')"
    )

    with pytest.raises(RuntimeError, match="va_profiles contains rows"):
        command.downgrade(alembic_config(), "0002")
