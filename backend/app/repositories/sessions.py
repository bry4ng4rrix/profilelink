from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuthSession, User


def add(db: AsyncSession, user_id: UUID, token_hash: str, expires_at: datetime) -> None:
    db.add(AuthSession(user_id=user_id, token_hash=token_hash, expires_at=expires_at))


async def get_valid(db: AsyncSession, token_hash: str) -> AuthSession | None:
    stmt = (
        select(AuthSession)
        .join(User)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.expires_at > func.now(),
            User.is_active,
        )
    )
    return await db.scalar(stmt)


async def purge_expired(db: AsyncSession) -> None:
    await db.execute(delete(AuthSession).where(AuthSession.expires_at <= func.now()))
