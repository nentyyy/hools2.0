from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin
from gg_shared import GiveawayStatus

_STATUSES = ", ".join(f"'{s.value}'" for s in GiveawayStatus)


class Giveaway(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "giveaways"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
        CheckConstraint("end_at > start_at", name="window_valid"),
        CheckConstraint("participants_count >= 0", name="participants_non_negative"),
        Index("ix_giveaways_status_end", "status", "end_at"),
    )

    title: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    image: Mapped[str | None] = mapped_column(String(512))

    prize_type: Mapped[str] = mapped_column(String(24), default="gg", server_default="gg", nullable=False)
    prize_value: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    prize_payload: Mapped[dict | None] = mapped_column(JSONB)

    entry_cost: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    min_level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    max_participants: Mapped[int | None] = mapped_column(Integer)
    participants_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(16), default=GiveawayStatus.ACTIVE.value, server_default=GiveawayStatus.ACTIVE.value, nullable=False
    )

    winner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    participants: Mapped[list[GiveawayParticipant]] = relationship(
        back_populates="giveaway", lazy="noload", cascade="all, delete-orphan"
    )


class GiveawayParticipant(Base, PrimaryKeyMixin):
    __tablename__ = "giveaway_participants"
    __table_args__ = (
        # A user can only ever hold one ticket per giveaway; the constraint makes
        # a duplicate POST fail at the database rather than in application code.
        UniqueConstraint("giveaway_id", "user_id", name="uq_giveaway_participants_giveaway_user"),
    )

    giveaway_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("giveaways.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    giveaway: Mapped[Giveaway] = relationship(back_populates="participants", lazy="noload")
