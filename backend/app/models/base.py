from datetime import datetime
from typing import Annotated
from uuid import UUID

from sqlalchemy import DateTime, func
from sqlalchemy.orm import mapped_column

from app.core.db import utcnow

UuidPk = Annotated[UUID, mapped_column(primary_key=True, server_default=func.gen_random_uuid())]
CreatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now())
]
UpdatedAt = Annotated[
    datetime, mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=utcnow)
]
