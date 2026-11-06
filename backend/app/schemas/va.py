from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, computed_field

from app.core.config import settings

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Age = Annotated[int, Field(ge=1, le=120)]


class PublicProfileOut(BaseModel):
    """Allow-list of what a visitor may see. Never add a link or admin data here."""

    id: UUID
    username: str
    first_name: str | None
    last_name: str | None
    age: int | None
    photo_url: str | None
    is_active: bool
    link_available: bool


class VaFields(BaseModel):
    first_name: Name
    last_name: Name
    age: Age
    instagram_url: str


class VaCreate(VaFields):
    destination_url: str


class StatusUpdate(BaseModel):
    is_active: bool


class LinkUpdate(BaseModel):
    destination_url: str


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    destination_url: str
    is_active: bool


class VaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    username: str
    first_name: str
    last_name: str
    age: int
    instagram_url: str
    photo_url: str
    is_active: bool
    link: LinkOut
    created_at: datetime
    updated_at: datetime

    @computed_field
    @property
    def public_url(self) -> str:
        return f"{settings.frontend_origin}/{self.username}"
