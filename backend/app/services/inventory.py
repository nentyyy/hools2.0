"""Inventory: items dropped by Lucky Buy or awarded by giveaways.

Items carry a GG value. Selling one credits that value through the ledger, so an
item is just deferred GG that the player can keep as a trophy instead.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError
from app.models import InventoryItem, User
from app.services.ledger import apply_change, lock_user
from gg_shared import ItemRarity, TransactionType

logger = logging.getLogger(__name__)


async def add_item(
    session: AsyncSession,
    user_id: int,
    *,
    item_type: str,
    item_code: str,
    name: str,
    rarity: ItemRarity | str = ItemRarity.COMMON,
    gg_value: int = 0,
    quantity: int = 1,
    image: str | None = None,
    source: str | None = None,
    extra: dict | None = None,
) -> InventoryItem:
    item = InventoryItem(
        user_id=user_id,
        item_type=item_type,
        item_code=item_code,
        name=name,
        rarity=ItemRarity(rarity).value if not isinstance(rarity, str) else str(rarity),
        gg_value=int(gg_value),
        quantity=max(int(quantity), 1),
        image=image,
        source=source,
        extra=extra,
    )
    session.add(item)
    await session.flush()
    return item


async def list_items(
    session: AsyncSession,
    user_id: int,
    *,
    include_sold: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[InventoryItem], int]:
    stmt = select(InventoryItem).where(InventoryItem.user_id == user_id)
    count_stmt = select(func.count()).select_from(InventoryItem).where(InventoryItem.user_id == user_id)
    if not include_sold:
        stmt = stmt.where(InventoryItem.is_sold.is_(False))
        count_stmt = count_stmt.where(InventoryItem.is_sold.is_(False))

    total = int(await session.scalar(count_stmt) or 0)
    items = list(
        (
            await session.execute(stmt.order_by(InventoryItem.created_at.desc()).limit(limit).offset(offset))
        ).scalars().all()
    )
    return items, total


async def get_item(session: AsyncSession, user_id: int, item_id: int) -> InventoryItem:
    item = await session.get(InventoryItem, item_id)
    # Ownership check, and a missing item is indistinguishable from someone
    # else's item so ids cannot be probed.
    if item is None or item.user_id != user_id:
        raise NotFoundError("Item not found")
    return item


async def sell_item(session: AsyncSession, user_id: int, item_id: int) -> tuple[User, InventoryItem, int]:
    """Convert an item into GG. Locks the row so it can only be sold once."""
    item = await session.scalar(
        select(InventoryItem)
        .where(InventoryItem.id == item_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if item is None or item.user_id != user_id:
        raise NotFoundError("Item not found")
    if item.is_sold:
        raise ConflictError("Item already sold")
    if item.gg_value <= 0:
        raise ConflictError("This item cannot be sold")

    payout = int(item.gg_value) * int(item.quantity)
    item.is_sold = True

    user = await lock_user(session, user_id)
    await apply_change(
        session,
        user,
        amount=payout,
        tx_type=TransactionType.SOLO_WIN,
        reference_id=f"inventory:{item.id}",
        description=f"Sold {item.name}",
        idempotency_key=f"inventory-sell:{item.id}",
    )
    logger.info("item_sold", extra={"user_id": user_id, "item_id": item.id, "payout": payout})
    return user, item, payout
