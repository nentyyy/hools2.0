from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin


class StarPayment(Base, PrimaryKeyMixin, TimestampMixin):
    """A Telegram Stars (XTR) purchase of GG.

    `payload` is the opaque string we put on the invoice and get back on
    successful_payment; it is unique so a replayed update cannot credit twice.
    """

    __tablename__ = "star_payments"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'paid', 'refunded', 'failed')", name="status_valid"
        ),
        CheckConstraint("stars_amount > 0", name="stars_positive"),
        Index("ix_star_payments_user_status", "user_id", "status"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    package_code: Mapped[str] = mapped_column(String(32), nullable=False)
    gg_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    stars_amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", server_default="XTR", nullable=False)

    payload: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    invoice_link: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(16), default="pending", server_default="pending", nullable=False)

    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True)
    provider_payment_charge_id: Mapped[str | None] = mapped_column(String(128))
    transaction_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("transactions.id", ondelete="SET NULL")
    )

    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_reason: Mapped[str | None] = mapped_column(String(256))
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
