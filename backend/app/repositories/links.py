from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExternalLink


async def get_for_profile(db: AsyncSession, profile_id: UUID) -> ExternalLink | None:
    return await db.scalar(select(ExternalLink).where(ExternalLink.profile_id == profile_id))


async def get_owned(db: AsyncSession, link_id: UUID, profile_id: UUID) -> ExternalLink | None:
    stmt = select(ExternalLink).where(
        ExternalLink.id == link_id, ExternalLink.profile_id == profile_id
    )
    return await db.scalar(stmt)
