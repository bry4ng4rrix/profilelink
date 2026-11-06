from uuid import UUID

from fastapi import APIRouter, status

from app.api.deps import CurrentProfile, Db
from app.repositories.links import get_for_profile
from app.schemas.link import LinkIn, LinkOut
from app.schemas.profile import StatusUpdate
from app.services import links

router = APIRouter(prefix="/api/v1/owner/links", tags=["owner"])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_link(data: LinkIn, profile: CurrentProfile, db: Db) -> LinkOut:
    return LinkOut.model_validate(await links.create(db, profile, data.destination_url))


@router.get("")
async def list_links(profile: CurrentProfile, db: Db) -> list[LinkOut]:
    link = await get_for_profile(db, profile.id)
    return [LinkOut.model_validate(link)] if link else []


@router.put("/{link_id}")
async def update_link(link_id: UUID, data: LinkIn, profile: CurrentProfile, db: Db) -> LinkOut:
    return LinkOut.model_validate(
        await links.update(db, profile, link_id, data.destination_url)
    )


@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: UUID, profile: CurrentProfile, db: Db) -> None:
    await links.delete(db, profile, link_id)


@router.patch("/{link_id}/status")
async def update_status(
    link_id: UUID, data: StatusUpdate, profile: CurrentProfile, db: Db
) -> LinkOut:
    return LinkOut.model_validate(await links.set_status(db, profile, link_id, data.is_active))
