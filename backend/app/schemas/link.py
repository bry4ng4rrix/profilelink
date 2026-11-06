from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LinkIn(BaseModel):
    destination_url: str


class LinkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    destination_url: str
    is_active: bool
    created_at: datetime
    updated_at: datetime
