from uuid import UUID

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base
from app.core.usernames import USERNAME_PATTERN
from app.models.base import CreatedAt, UpdatedAt, UuidPk


class VaProfile(Base):
    """A person shown on a public page. Data managed by the admin, never an account."""

    __tablename__ = "va_profiles"
    __table_args__ = (
        CheckConstraint(f"username ~ '{USERNAME_PATTERN}'", name="username_format"),
        CheckConstraint("age BETWEEN 1 AND 120", name="age_range"),
        CheckConstraint("char_length(instagram_url) <= 2048", name="instagram_length"),
    )

    id: Mapped[UuidPk]
    username: Mapped[str] = mapped_column(String(30), unique=True)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    age: Mapped[int] = mapped_column(SmallInteger)
    instagram_url: Mapped[str] = mapped_column(Text)  # admin only, never on the public page
    photo_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]

    # lazy="raise": public code paths cannot pull destination_url in by accident.
    link: Mapped["VaExternalLink"] = relationship(lazy="raise", uselist=False)


class VaExternalLink(Base):
    __tablename__ = "va_external_links"
    __table_args__ = (
        CheckConstraint("char_length(destination_url) <= 2048", name="destination_length"),
    )

    id: Mapped[UuidPk]
    va_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("va_profiles.id", ondelete="CASCADE"), unique=True
    )
    destination_url: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(server_default=text("true"))
    created_at: Mapped[CreatedAt]
    updated_at: Mapped[UpdatedAt]
