from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.core.usernames import USERNAME_PATTERN
from app.models.base import CreatedAt, UpdatedAt, UuidPk


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (
        CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="username_format"),
        CheckConstraint("char_length(bio) <= 500", name="bio_length"),
        Index("ix_profiles_active_updated", "updated_at", postgresql_where=text("is_active")),
    )

    id: Mapped[UuidPk]
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    username: Mapped[str] = mapped_column(String(30), unique=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
    bio: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]


class ExternalLink(Base):
    __tablename__ = "external_links"
    __table_args__ = (
        CheckConstraint("char_length(destination_url) <= 2048", name="destination_length"),
    )

    id: Mapped[UuidPk]
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), unique=True
    )
    destination_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
