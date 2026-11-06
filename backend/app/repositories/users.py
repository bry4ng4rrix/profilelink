from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Profile, User


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


async def get_identity(db: AsyncSession, user_id: UUID) -> Row:
    stmt = select(User.id, User.email, Profile.username).join(Profile).where(User.id == user_id)
    return (await db.execute(stmt)).one()
