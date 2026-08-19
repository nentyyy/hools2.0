from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin
from gg_shared import SoloGameType, SoloStatus

_TYPES = ", ".join(f"'{t.value}'" for t in SoloGameType)
_STATUSES = ", ".join(f"'{s.value}'" for s in SoloStatus)


class SoloGame(Base, PrimaryKeyMixin, TimestampMixin):
    """One single-player round. Instant modes finish immediately; Hi-Lo and Ice
    Arena stay `active` across requests with their progress in `state`."""

    __tablename__ = "solo_games"
    __table_args__ = (
        CheckConstraint(f"game_type IN ({_TYPES})", name="game_type_valid"),
        CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
        CheckConstraint("bet >= 0", name="bet_non_negative"),
        CheckConstraint("reward >= 0", name="reward_non_negative"),
        Index("ix_solo_games_user_type", "user_id", "game_type"),
        Index("ix_solo_games_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    game_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    bet: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    reward: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    multiplier: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB)
    state: Mapped[dict | None] = mapped_column(JSONB)

    server_seed: Mapped[str | None] = mapped_column(String(128))
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)

    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    rounds: Mapped[list[SoloRound]] = relationship(
        back_populates="game", lazy="selectin", cascade="all, delete-orphan", order_by="SoloRound.round_number"
    )


class SoloRound(Base, PrimaryKeyMixin, TimestampMixin):
    """Per-round history for the multi-round modes (Ice Arena, Hi-Lo)."""

    __tablename__ = "solo_rounds"
    __table_args__ = (
        Index("ix_solo_rounds_game_number", "game_id", "round_number", unique=True),
    )

    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("solo_games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False)
    success_chance: Mapped[float] = mapped_column(Float, nullable=False)
    possible_reward: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    roll: Mapped[float] = mapped_column(Float, nullable=False)
    survived: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    payload: Mapped[dict | None] = mapped_column(JSONB)

    game: Mapped[SoloGame] = relationship(back_populates="rounds", lazy="noload")
