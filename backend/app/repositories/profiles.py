from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExternalLink, Profile, User


async def get_by_user(db: AsyncSession, user_id: UUID) -> Profile:
    return (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one()


async def get_public(db: AsyncSession, username: str) -> Row | None:
    # Deliberately selects the link state only: destination_url never enters this path.
    stmt = (
        select(Profile, User.is_active.label("user_active"), ExternalLink.is_active.label("link_active"))
        .join(User, Profile.user_id == User.id)
        .outerjoin(ExternalLink, ExternalLink.profile_id == Profile.id)
        .where(Profile.username == username)
    )
    return (await db.execute(stmt)).one_or_none()


async def get_redirect_target(db: AsyncSession, username: str) -> Row | None:
    stmt = (
        select(Profile.id, ExternalLink.destination_url)
        .join(User, Profile.user_id == User.id)
        .join(ExternalLink, ExternalLink.profile_id == Profile.id)
        .where(
            Profile.username == username,
            Profile.is_active,
            User.is_active,
            ExternalLink.is_active,
        )
    )
    return (await db.execute(stmt)).one_or_none()


async def get_active_id(db: AsyncSession, username: str) -> UUID | None:
    stmt = (
        select(Profile.id)
        .join(User, Profile.user_id == User.id)
        .where(Profile.username == username, Profile.is_active, User.is_active)
    )
    return await db.scalar(stmt)


async def list_for_sitemap(db: AsyncSession, limit: int) -> Sequence[Row]:
    stmt = (
        select(Profile.username, Profile.updated_at)
        .join(User, Profile.user_id == User.id)
        .where(Profile.is_active, User.is_active)
        .order_by(Profile.updated_at.desc())
        .limit(limit)
    )
    return (await db.execute(stmt)).all()
