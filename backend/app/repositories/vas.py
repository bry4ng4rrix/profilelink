from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Row, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models import VaExternalLink, VaProfile


async def list_all(db: AsyncSession) -> Sequence[VaProfile]:
    # shortcut: no pagination, an admin manages tens of VA. Add limit/offset beyond a few hundred.
    stmt = select(VaProfile).options(joinedload(VaProfile.link)).order_by(VaProfile.created_at.desc())
    return (await db.scalars(stmt)).all()


async def get(db: AsyncSession, va_id: UUID) -> VaProfile | None:
    stmt = select(VaProfile).options(joinedload(VaProfile.link)).where(VaProfile.id == va_id)
    return await db.scalar(stmt)


async def username_taken(db: AsyncSession, username: str) -> bool:
    return await db.scalar(select(VaProfile.id).where(VaProfile.username == username)) is not None


async def remove(db: AsyncSession, va_id: UUID) -> None:
    await db.execute(delete(VaProfile).where(VaProfile.id == va_id))


async def get_public(db: AsyncSession, username: str) -> Row | None:
    # Selects the link state only: destination_url never enters this path.
    stmt = (
        select(VaProfile, VaExternalLink.is_active.label("link_active"))
        .outerjoin(VaExternalLink, VaExternalLink.va_profile_id == VaProfile.id)
        .where(VaProfile.username == username)
    )
    return (await db.execute(stmt)).one_or_none()


async def get_redirect_target(db: AsyncSession, username: str) -> Row | None:
    stmt = (
        select(VaProfile.id, VaExternalLink.destination_url)
        .join(VaExternalLink, VaExternalLink.va_profile_id == VaProfile.id)
        .where(VaProfile.username == username, VaProfile.is_active, VaExternalLink.is_active)
    )
    return (await db.execute(stmt)).one_or_none()


async def get_active_id(db: AsyncSession, username: str) -> UUID | None:
    stmt = select(VaProfile.id).where(VaProfile.username == username, VaProfile.is_active)
    return await db.scalar(stmt)


async def counts(db: AsyncSession) -> tuple[int, int]:
    stmt = select(func.count(), func.count().filter(VaProfile.is_active)).select_from(VaProfile)
    return tuple((await db.execute(stmt)).one())
