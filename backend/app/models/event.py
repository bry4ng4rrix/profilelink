from uuid import UUID

from sqlalchemy import CHAR, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base
from app.models.base import CreatedAt, UuidPk


class ClickEvent(Base):
    __tablename__ = "click_events"
    __table_args__ = (
        Index("ix_click_events_profile_time", "profile_id", text("clicked_at DESC")),
    )

    id: Mapped[UuidPk]
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    clicked_at: Mapped[CreatedAt]
    referer_domain: Mapped[str | None] = mapped_column(String(253))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(CHAR(64))


class ProfileVisit(Base):
    __tablename__ = "profile_visits"
    __table_args__ = (
        Index("ix_profile_visits_profile_time", "profile_id", text("visited_at DESC")),
    )

    id: Mapped[UuidPk]
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("profiles.id", ondelete="CASCADE"))
    visited_at: Mapped[CreatedAt]
    referer_domain: Mapped[str | None] = mapped_column(String(253))
    user_agent: Mapped[str | None] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(CHAR(64))
