"""Profile, transaction history, inventory, referrals and fairness."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import CurrentUser, IdempotencyKey, SessionDep, default_limit, idempotency_guard
from app.core.errors import ConflictError, ValidationError
from app.models import SoloGame, Transaction
from app.schemas.common import make_page
from app.schemas.user import (
    InventoryItemPublic,
    LevelInfo,
    ProfileResponse,
    ProfileStats,
    ReferralsResponse,
    ReferralSummary,
    TransactionPublic,
    UserPublic,
)
from app.services import inventory as inventory_service
from app.services import referrals as referrals_service
from app.services import seeds as seeds_service
from app.services.leveling import level_progress
from gg_shared import SoloStatus, TransactionType

router = APIRouter(tags=["profile"], dependencies=[Depends(default_limit)])


@router.get("/profile", response_model=ProfileResponse)
async def profile(user: CurrentUser, session: SessionDep) -> ProfileResponse:
    await session.refresh(user)

    items, _ = await inventory_service.list_items(session, user.id, limit=50)
    transactions = (
        (
            await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user.id)
                .order_by(Transaction.created_at.desc())
                .limit(20)
            )
        )
        .scalars()
        .all()
    )
    stats = await referrals_service.stats(session, user, limit=0)

    return ProfileResponse(
        user=UserPublic.model_validate(user),
        level=LevelInfo(**level_progress(int(user.xp))),
        stats=ProfileStats(
            pvp_wins=user.pvp_wins,
            pvp_games=user.pvp_games,
            solo_wins=user.solo_wins,
            solo_games=user.solo_games,
            total_wagered=int(user.total_wagered),
            total_earned=int(user.total_earned),
            stars_spent=int(user.stars_spent),
        ),
        referrals=ReferralSummary(
            code=stats["code"],
            link=stats["link"],
            invited_count=stats["invited_count"],
            earnings=stats["earnings"],
        ),
        inventory=[InventoryItemPublic.model_validate(i) for i in items],
        transactions=[TransactionPublic.model_validate(t) for t in transactions],
    )


@router.get("/transactions")
async def transactions(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    type: Annotated[str | None, Query(description="Filter by transaction type")] = None,
) -> dict:
    stmt = select(Transaction).where(Transaction.user_id == user.id)
    count_stmt = select(func.count()).select_from(Transaction).where(Transaction.user_id == user.id)

    if type:
        try:
            tx_type = TransactionType(type)
        except ValueError as exc:
            raise ValidationError(f"Unknown transaction type: {type}") from exc
        stmt = stmt.where(Transaction.type == tx_type.value)
        count_stmt = count_stmt.where(Transaction.type == tx_type.value)

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (
            await session.execute(
                stmt.order_by(Transaction.created_at.desc(), Transaction.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return make_page(
        [TransactionPublic.model_validate(t).model_dump(mode="json") for t in rows],
        total,
        limit,
        offset,
    )


@router.get("/inventory")
async def get_inventory(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
    include_sold: bool = False,
) -> dict:
    items, total = await inventory_service.list_items(
        session, user.id, include_sold=include_sold, limit=limit, offset=offset
    )
    return make_page(
        [InventoryItemPublic.model_validate(i).model_dump(mode="json") for i in items],
        total,
        limit,
        offset,
    )


@router.get("/inventory/{item_id}", response_model=InventoryItemPublic)
async def get_inventory_item(item_id: int, user: CurrentUser, session: SessionDep) -> InventoryItemPublic:
    item = await inventory_service.get_item(session, user.id, item_id)
    return InventoryItemPublic.model_validate(item)


@router.post("/inventory/{item_id}/sell")
async def sell_inventory_item(
    item_id: int,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard("inventory-sell", user.id, idempotency_key, {"item_id": item_id})
    if guard.cached:
        return guard.cached
    try:
        _, item, payout = await inventory_service.sell_item(session, user.id, item_id)
        await session.commit()
    except Exception:
        await guard.fail()
        raise
    await session.refresh(user)
    return await guard.finish(
        {"ok": True, "payout": payout, "balance": int(user.balance), "item_id": item.id}
    )


@router.get("/referrals", response_model=ReferralsResponse)
async def referrals(user: CurrentUser, session: SessionDep) -> ReferralsResponse:
    return ReferralsResponse(**await referrals_service.stats(session, user))


@router.get("/fair")
async def fairness(user: CurrentUser, session: SessionDep) -> dict:
    """Current provably-fair seed pair; the server seed stays hidden until rotation."""
    seed = await seeds_service.get_or_create_seed(session, user.id)
    await session.commit()
    return {
        "server_seed_hash": seed.server_seed_hash,
        "client_seed": seed.client_seed,
        "nonce": seed.nonce,
        "previous_server_seed": seed.previous_server_seed,
        "previous_server_seed_hash": seed.previous_server_seed_hash,
    }


@router.post("/fair/rotate")
async def rotate_seed(user: CurrentUser, session: SessionDep, client_seed: str | None = None) -> dict:
    active = await session.scalar(
        select(func.count())
        .select_from(SoloGame)
        .where(SoloGame.user_id == user.id, SoloGame.status == SoloStatus.ACTIVE.value)
    )
    if active:
        raise ConflictError("Finish your active rounds before rotating the seed")

    seed = await seeds_service.rotate_seed(session, user.id, client_seed)
    await session.commit()
    return {
        "server_seed_hash": seed.server_seed_hash,
        "client_seed": seed.client_seed,
        "nonce": seed.nonce,
        "revealed_server_seed": seed.previous_server_seed,
        "revealed_server_seed_hash": seed.previous_server_seed_hash,
    }
