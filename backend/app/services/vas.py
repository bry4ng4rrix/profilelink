from uuid import UUID

from fastapi import HTTPException, UploadFile
from sqlalchemy import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.usernames import username_candidates
from app.models import VaExternalLink, VaProfile
from app.repositories import vas
from app.schemas.va import PublicProfileOut, VaCreate, VaFields
from app.services import destinations, photos, revalidate


def public_view(row: Row) -> PublicProfileOut:
    va = row.VaProfile
    if not va.is_active:
        return PublicProfileOut(
            username=va.username,
            first_name=None,
            last_name=None,
            age=None,
            photo_url=None,
            is_active=False,
            link_available=False,
        )
    return PublicProfileOut(
        username=va.username,
        first_name=va.first_name,
        last_name=va.last_name,
        age=va.age,
        photo_url=va.photo_url,
        is_active=True,
        link_available=bool(row.link_active),
    )


async def get(db: AsyncSession, va_id: UUID) -> VaProfile:
    va = await vas.get(db, va_id)
    if va is None:
        raise HTTPException(404, "not_found")
    return va


async def create(db: AsyncSession, data: VaCreate, photo: UploadFile) -> VaProfile:
    """All or nothing: links are checked first, and a failure leaves no photo behind."""
    instagram_url = destinations.validate_instagram(data.instagram_url)
    destination = await destinations.validate(data.destination_url)
    photo_url = await photos.store(photo)
    try:
        for username in username_candidates(data.first_name, data.last_name):
            if await vas.username_taken(db, username):
                continue
            va = VaProfile(
                username=username,
                first_name=data.first_name,
                last_name=data.last_name,
                age=data.age,
                instagram_url=instagram_url,
                photo_url=photo_url,
                link=VaExternalLink(destination_url=destination),
            )
            db.add(va)
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()  # taken between the check and the commit: try the next one
                continue
            await revalidate.notify(username)  # the name may have been a cached 404
            return va
    except Exception:
        photos.remove(photo_url)
        raise
    raise AssertionError("username_candidates never ends")


async def update(db: AsyncSession, va_id: UUID, data: VaFields) -> VaProfile:
    va = await get(db, va_id)
    instagram_url = destinations.validate_instagram(data.instagram_url)
    for field, value in data.model_dump().items():
        setattr(va, field, value)
    va.instagram_url = instagram_url
    await db.commit()
    await revalidate.notify(va.username)
    return va


async def set_photo(db: AsyncSession, va_id: UUID, photo: UploadFile) -> VaProfile:
    va = await get(db, va_id)
    previous = va.photo_url
    va.photo_url = await photos.store(photo)
    await db.commit()
    photos.remove(previous)
    await revalidate.notify(va.username)
    return va


async def set_status(db: AsyncSession, va_id: UUID, is_active: bool) -> VaProfile:
    va = await get(db, va_id)
    va.is_active = is_active
    await db.commit()
    await revalidate.notify(va.username)
    return va


async def set_destination(db: AsyncSession, va_id: UUID, raw_url: str) -> VaProfile:
    va = await get(db, va_id)
    va.link.destination_url = await destinations.validate(raw_url)
    await db.commit()
    await revalidate.notify(va.username)
    return va


async def set_link_status(db: AsyncSession, va_id: UUID, is_active: bool) -> VaProfile:
    va = await get(db, va_id)
    va.link.is_active = is_active
    await db.commit()
    await revalidate.notify(va.username)
    return va


async def delete(db: AsyncSession, va_id: UUID) -> None:
    va = await get(db, va_id)
    username, photo_url = va.username, va.photo_url
    await vas.remove(db, va_id)  # the link and the statistics go with it (ON DELETE CASCADE)
    await db.commit()
    photos.remove(photo_url)
    await revalidate.notify(username)
