from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin
from gg_shared import TransactionType

_TYPES = ", ".join(f"'{t.value}'" for t in TransactionType)


class Transaction(Base, PrimaryKeyMixin, TimestampMixin):
    """Append-only ledger. Exactly one row per change of `users.balance`."""

    __tablename__ = "transactions"
    __table_args__ = (
        CheckConstraint(f"type IN ({_TYPES})", name="type_valid"),
        CheckConstraint("balance_after >= 0", name="balance_after_non_negative"),
        CheckConstraint(
            "balance_after = balance_before + amount", name="balance_delta_consistent"
        ),
        Index("ix_transactions_user_created", "user_id", "created_at"),
        Index("ix_transactions_user_type", "user_id", "type"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)  # signed: +credit / -debit
    balance_before: Mapped[int] = mapped_column(BigInteger, nullable=False)
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(String(256))
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)

    # Set for every operation that a client may retry; the unique index turns a
    # duplicate submit into a conflict instead of a double spend.
    idempotency_key: Mapped[str | None] = mapped_column(String(128), unique=True)
