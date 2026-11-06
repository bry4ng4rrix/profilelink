from fastapi import APIRouter, UploadFile

from app.api.deps import CurrentProfile, Db
from app.schemas.profile import OwnerProfileOut, PhotoOut, ProfileUpdate, StatusUpdate
from app.services import profiles

router = APIRouter(prefix="/api/v1/owner/profile", tags=["owner"])


@router.get("")
async def get_profile(profile: CurrentProfile) -> OwnerProfileOut:
    return OwnerProfileOut.model_validate(profile)


@router.put("")
async def update_profile(data: ProfileUpdate, profile: CurrentProfile, db: Db) -> OwnerProfileOut:
    return OwnerProfileOut.model_validate(await profiles.update(db, profile, data))


@router.post("/photo")
async def upload_photo(file: UploadFile, profile: CurrentProfile, db: Db) -> PhotoOut:
    return PhotoOut(photo_url=await profiles.set_photo(db, profile, file))


@router.patch("/status")
async def update_status(data: StatusUpdate, profile: CurrentProfile, db: Db) -> OwnerProfileOut:
    return OwnerProfileOut.model_validate(await profiles.set_status(db, profile, data.is_active))
