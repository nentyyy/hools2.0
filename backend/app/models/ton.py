from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin


class TonWallet(Base, PrimaryKeyMixin, TimestampMixin):
    """A wallet the user connected over TON Connect.

    Only the public address and the proof we verified are stored — never a seed
    phrase, private key or any custodial material.
    """

    __tablename__ = "ton_wallets"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    address: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    friendly_address: Mapped[str | None] = mapped_column(String(128))
    public_key: Mapped[str | None] = mapped_column(String(128))
    chain: Mapped[str | None] = mapped_column(String(16))
    wallet_name: Mapped[str | None] = mapped_column(String(64))
    proof_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    disconnected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[object] = relationship("User", back_populates="ton_wallet", lazy="noload")


class TonTransaction(Base, PrimaryKeyMixin, TimestampMixin):
    """An on-chain transfer we verified against a public TON indexer."""

    __tablename__ = "ton_transactions"
    __table_args__ = (
        CheckConstraint("status IN ('pending', 'confirmed', 'failed')", name="status_valid"),
        Index("ix_ton_transactions_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    boc_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    tx_hash: Mapped[str | None] = mapped_column(String(128), index=True)
    from_address: Mapped[str | None] = mapped_column(String(128))
    to_address: Mapped[str | None] = mapped_column(String(128))
    amount_nano: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    amount_ton: Mapped[float] = mapped_column(Numeric(20, 9), default=0, server_default="0", nullable=False)
    comment: Mapped[str | None] = mapped_column(String(256))
    purpose: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", nullable=False)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    raw: Mapped[dict | None] = mapped_column(JSONB)
