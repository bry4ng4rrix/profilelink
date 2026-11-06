from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ExternalLink, Profile
from app.repositories import links
from app.services import destinations, revalidate


async def _owned(db: AsyncSession, link_id: UUID, profile: Profile) -> ExternalLink:
    link = await links.get_owned(db, link_id, profile.id)
    if link is None:
        raise HTTPException(404, "not_found")
    return link


async def create(db: AsyncSession, profile: Profile, raw_url: str) -> ExternalLink:
    link = ExternalLink(
        profile_id=profile.id, destination_url=await destinations.validate(raw_url)
    )
    db.add(link)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "link_exists") from exc
    await revalidate.notify(profile.username)
    return link


async def update(db: AsyncSession, profile: Profile, link_id: UUID, raw_url: str) -> ExternalLink:
    link = await _owned(db, link_id, profile)
    link.destination_url = await destinations.validate(raw_url)
    await db.commit()
    await revalidate.notify(profile.username)
    return link


async def set_status(
    db: AsyncSession, profile: Profile, link_id: UUID, is_active: bool
) -> ExternalLink:
    link = await _owned(db, link_id, profile)
    link.is_active = is_active
    await db.commit()
    await revalidate.notify(profile.username)
    return link


async def delete(db: AsyncSession, profile: Profile, link_id: UUID) -> None:
    await db.delete(await _owned(db, link_id, profile))
    await db.commit()
    await revalidate.notify(profile.username)
