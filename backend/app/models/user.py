from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.ton import TonWallet


class User(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"
    __table_args__ = (
        # The database is the last line of defence for the ledger: no code path,
        # however racy, can drive a balance below zero.
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("xp >= 0", name="xp_non_negative"),
        CheckConstraint("level >= 1", name="level_positive"),
    )

    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[str | None] = mapped_column(String(64))
    first_name: Mapped[str | None] = mapped_column(String(128))
    last_name: Mapped[str | None] = mapped_column(String(128))
    avatar: Mapped[str | None] = mapped_column(String(512))
    language_code: Mapped[str | None] = mapped_column(String(8))

    balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    xp: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)

    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)
    ban_reason: Mapped[str | None] = mapped_column(String(256))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false", nullable=False)

    referral_code: Mapped[str] = mapped_column(String(16), unique=True, index=True, nullable=False)
    referral_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    # Denormalised counters kept in step with the ledger inside the same
    # transaction, so the profile screen never fans out into aggregate queries.
    pvp_wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    pvp_games: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    solo_wins: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    solo_games: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    total_wagered: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    total_earned: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    stars_spent: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    referral_earnings: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)

    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    referrer: Mapped[User | None] = relationship(remote_side="User.id", lazy="noload")
    ton_wallet: Mapped[TonWallet | None] = relationship(
        back_populates="user", uselist=False, lazy="noload", cascade="all, delete-orphan"
    )

    @property
    def display_name(self) -> str:
        name = " ".join(p for p in (self.first_name, self.last_name) if p).strip()
        return name or self.username or f"Player #{self.id}"

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<User id={self.id} tg={self.telegram_id} balance={self.balance}>"
