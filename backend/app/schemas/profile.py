from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, BeforeValidator, ConfigDict, StringConstraints, computed_field

from app.core.config import settings
from app.schemas.auth import Username


def _blank_to_none(value: object) -> object:
    return value.strip() or None if isinstance(value, str) else value


Name = Annotated[
    Annotated[str, StringConstraints(max_length=100)] | None, BeforeValidator(_blank_to_none)
]
Bio = Annotated[
    Annotated[str, StringConstraints(max_length=500)] | None, BeforeValidator(_blank_to_none)
]


class PublicProfileOut(BaseModel):
    """Allow-list of what a visitor may see. Never add link or account data here."""

    id: UUID
    username: str
    first_name: str | None
    last_name: str | None
    bio: str | None
    photo_url: str | None
    is_active: bool
    link_available: bool


class SitemapEntry(BaseModel):
    username: str
    updated_at: datetime


class ProfileUpdate(BaseModel):
    username: Username
    first_name: Name = None
    last_name: Name = None
    bio: Bio = None


class StatusUpdate(BaseModel):
    is_active: bool


class OwnerProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    first_name: str | None
    last_name: str | None
    bio: str | None
    photo_url: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def public_url(self) -> str:
        return f"{settings.frontend_origin}/{self.username}"


class PhotoOut(BaseModel):
    photo_url: str
