from fastapi import HTTPException, UploadFile
from sqlalchemy import Row
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.usernames import ensure_allowed
from app.models import Profile
from app.schemas.profile import ProfileUpdate, PublicProfileOut
from app.services import photos, revalidate


def public_view(row: Row) -> PublicProfileOut:
    profile = row.Profile
    is_active = profile.is_active and row.user_active
    if not is_active:
        return PublicProfileOut(
            id=profile.id,
            username=profile.username,
            first_name=None,
            last_name=None,
            bio=None,
            photo_url=None,
            is_active=False,
            link_available=False,
        )
    return PublicProfileOut(
        id=profile.id,
        username=profile.username,
        first_name=profile.first_name,
        last_name=profile.last_name,
        bio=profile.bio,
        photo_url=profile.photo_url,
        is_active=True,
        link_available=bool(row.link_active),
    )


async def update(db: AsyncSession, profile: Profile, data: ProfileUpdate) -> Profile:
    old_username = profile.username
    if data.username != old_username:
        ensure_allowed(data.username)
    for field, value in data.model_dump().items():
        setattr(profile, field, value)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(409, "username_taken") from exc
    await revalidate.notify(old_username, profile.username)
    return profile


async def set_status(db: AsyncSession, profile: Profile, is_active: bool) -> Profile:
    profile.is_active = is_active
    await db.commit()
    await revalidate.notify(profile.username)
    return profile


async def set_photo(db: AsyncSession, profile: Profile, upload: UploadFile) -> str:
    previous = profile.photo_url
    profile.photo_url = await photos.store(upload)
    await db.commit()
    photos.remove(previous)
    await revalidate.notify(profile.username)
    return profile.photo_url
