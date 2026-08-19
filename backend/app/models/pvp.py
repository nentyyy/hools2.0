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
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin
from gg_shared import PvPStatus

_STATUSES = ", ".join(f"'{s.value}'" for s in PvPStatus)


class PvPGame(Base, PrimaryKeyMixin, TimestampMixin):
    """A pot-style round: every player's win chance equals their share of the pool.

    The round is driven by timestamps rather than by a live task, so any worker
    (or a cron tick) can resolve it deterministically and exactly once.
    """

    __tablename__ = "pvp_games"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUSES})", name="status_valid"),
        CheckConstraint("total_pool >= 0", name="pool_non_negative"),
        Index("ix_pvp_games_status_created", "status", "created_at"),
    )

    status: Mapped[str] = mapped_column(
        String(16), default=PvPStatus.WAITING.value, server_default=PvPStatus.WAITING.value, nullable=False
    )
    total_pool: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    rake: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    prize: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    min_bet: Mapped[int] = mapped_column(BigInteger, default=10, server_default="10", nullable=False)
    max_players: Mapped[int] = mapped_column(Integer, default=12, server_default="12", nullable=False)

    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    winner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    spin_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Provably fair proof of the winning ticket.
    server_seed: Mapped[str | None] = mapped_column(String(128))
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    winning_roll: Mapped[float | None] = mapped_column(Float)

    players: Mapped[list[PvPPlayer]] = relationship(
        back_populates="game", lazy="selectin", cascade="all, delete-orphan", order_by="PvPPlayer.id"
    )

    @property
    def is_open(self) -> bool:
        return self.status in {PvPStatus.WAITING.value, PvPStatus.STARTING.value}


class PvPPlayer(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "pvp_players"
    __table_args__ = (
        # One seat per user per round: joining twice tops up the same seat.
        UniqueConstraint("game_id", "user_id", name="uq_pvp_players_game_user"),
        CheckConstraint("amount > 0", name="amount_positive"),
    )

    game_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pvp_games.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chance: Mapped[float] = mapped_column(Float, default=0.0, server_default="0", nullable=False)
    ticket_from: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    ticket_to: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    is_winner: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)

    game: Mapped[PvPGame] = relationship(back_populates="players", lazy="noload")
