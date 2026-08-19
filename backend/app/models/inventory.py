from __future__ import annotations

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin
from gg_shared import ItemRarity

_RARITIES = ", ".join(f"'{r.value}'" for r in ItemRarity)


class InventoryItem(Base, PrimaryKeyMixin, TimestampMixin):
    __tablename__ = "inventory_items"
    __table_args__ = (
        CheckConstraint(f"rarity IN ({_RARITIES})", name="rarity_valid"),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        Index("ix_inventory_items_user_type", "user_id", "item_type"),
    )

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    item_type: Mapped[str] = mapped_column(String(32), nullable=False)
    item_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    image: Mapped[str | None] = mapped_column(String(512))
    rarity: Mapped[str] = mapped_column(String(16), default=ItemRarity.COMMON.value, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, server_default="1", nullable=False)
    gg_value: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0", nullable=False)
    is_sold: Mapped[bool] = mapped_column(default=False, server_default="false", nullable=False)
    source: Mapped[str | None] = mapped_column(String(32))
    extra: Mapped[dict | None] = mapped_column("metadata", JSONB)
