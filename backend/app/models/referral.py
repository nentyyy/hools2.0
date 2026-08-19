from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin


class ReferralBonus(Base, PrimaryKeyMixin, TimestampMixin):
    """Guard table: a signup bonus can be paid at most once per referred user."""

    __tablename__ = "referral_bonuses"
    __table_args__ = (
        UniqueConstraint("referrer_id", "referred_id", "kind", name="uq_referral_bonuses_pair_kind"),
    )

    referrer_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    referred_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), default="signup", nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    reference_id: Mapped[str | None] = mapped_column(String(128))
