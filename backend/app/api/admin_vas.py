from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Form, UploadFile, status

from app.api.deps import Db, current_session
from app.repositories import vas as repository
from app.schemas.va import LinkUpdate, StatusUpdate, VaCreate, VaFields, VaOut
from app.services import vas

# Router-level guard: a route added here cannot be left unprotected by mistake.
router = APIRouter(
    prefix="/api/v1/admin/vas", tags=["admin"], dependencies=[Depends(current_session)]
)


@router.get("")
async def list_vas(db: Db) -> list[VaOut]:
    return [VaOut.model_validate(va) for va in await repository.list_all(db)]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_va(data: Annotated[VaCreate, Form()], photo: UploadFile, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.create(db, data, photo))


@router.get("/{va_id}")
async def get_va(va_id: UUID, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.get(db, va_id))


@router.put("/{va_id}")
async def update_va(va_id: UUID, data: VaFields, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.update(db, va_id, data))


@router.delete("/{va_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_va(va_id: UUID, db: Db) -> None:
    await vas.delete(db, va_id)


@router.post("/{va_id}/photo")
async def upload_photo(va_id: UUID, file: UploadFile, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.set_photo(db, va_id, file))


@router.patch("/{va_id}/status")
async def update_status(va_id: UUID, data: StatusUpdate, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.set_status(db, va_id, data.is_active))


@router.put("/{va_id}/link")
async def update_link(va_id: UUID, data: LinkUpdate, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.set_destination(db, va_id, data.destination_url))


@router.patch("/{va_id}/link/status")
async def update_link_status(va_id: UUID, data: StatusUpdate, db: Db) -> VaOut:
    return VaOut.model_validate(await vas.set_link_status(db, va_id, data.is_active))
