"""Administrative API.

Every route here depends on `AdminUser`, which requires both a valid session
token and either the `is_admin` flag on the row or membership of
ADMIN_TELEGRAM_IDS.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import AdminUser, SessionDep, default_limit
from app.api.serializers import serialize_giveaway, serialize_pvp
from app.core.errors import NotFoundError, ValidationError
from app.models import Giveaway, PvPGame, SoloGame, StarPayment, Transaction, User
from app.schemas.admin import (
    AdjustBalanceRequest,
    BanRequest,
    GiveawayCreateRequest,
    GiveawayUpdateRequest,
)
from app.schemas.common import OkResponse, make_page
from app.schemas.game import SoloGamePublic
from app.schemas.payment import StarPaymentPublic
from app.schemas.user import TransactionPublic, UserPublic
from app.services import giveaways as giveaways_service
from app.services import payments as payments_service
from app.services.ledger import apply_change, lock_user
from gg_shared import GiveawayStatus, PvPStatus, TransactionType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(default_limit)])


@router.get("/stats")
async def stats(admin: AdminUser, session: SessionDep) -> dict:
    day_ago = datetime.now(UTC) - timedelta(days=1)

    async def count(model, *where) -> int:
        stmt = select(func.count()).select_from(model)
        for clause in where:
            stmt = stmt.where(clause)
        return int(await session.scalar(stmt) or 0)

    paid_stars = await session.scalar(
        select(func.coalesce(func.sum(StarPayment.stars_amount), 0)).where(StarPayment.status == "paid")
    )
    circulating = await session.scalar(select(func.coalesce(func.sum(User.balance), 0)))

    return {
        "users": {
            "total": await count(User),
            "new_24h": await count(User, User.created_at >= day_ago),
            "banned": await count(User, User.is_banned.is_(True)),
            "active_24h": await count(User, User.last_seen_at >= day_ago),
        },
        "economy": {
            "gg_circulating": int(circulating or 0),
            "stars_collected": int(paid_stars or 0),
            "payments_paid": await count(StarPayment, StarPayment.status == "paid"),
            "payments_refunded": await count(StarPayment, StarPayment.status == "refunded"),
        },
        "games": {
            "pvp_total": await count(PvPGame),
            "pvp_live": await count(
                PvPGame,
                PvPGame.status.in_(
                    [PvPStatus.WAITING.value, PvPStatus.STARTING.value, PvPStatus.SPINNING.value]
                ),
            ),
            "solo_24h": await count(SoloGame, SoloGame.created_at >= day_ago),
        },
        "giveaways": {
            "active": await count(Giveaway, Giveaway.status == GiveawayStatus.ACTIVE.value),
            "finished": await count(Giveaway, Giveaway.status == GiveawayStatus.FINISHED.value),
        },
    }


# --------------------------------------------------------------------------- #
# users
# --------------------------------------------------------------------------- #
@router.get("/users")
async def list_users(
    admin: AdminUser,
    session: SessionDep,
    q: Annotated[str | None, Query(description="username, name or telegram id")] = None,
    banned: bool | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(User)
    count_stmt = select(func.count()).select_from(User)
    if q:
        pattern = f"%{q}%"
        clause = or_(User.username.ilike(pattern), User.first_name.ilike(pattern))
        if q.isdigit():
            clause = or_(clause, User.telegram_id == int(q))
        stmt = stmt.where(clause)
        count_stmt = count_stmt.where(clause)
    if banned is not None:
        stmt = stmt.where(User.is_banned.is_(banned))
        count_stmt = count_stmt.where(User.is_banned.is_(banned))

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (await session.execute(stmt.order_by(User.created_at.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return make_page(
        [UserPublic.model_validate(u).model_dump(mode="json") for u in rows], total, limit, offset
    )


@router.get("/users/{user_id}")
async def get_user(user_id: int, admin: AdminUser, session: SessionDep) -> dict:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")

    transactions = (
        (
            await session.execute(
                select(Transaction)
                .where(Transaction.user_id == user_id)
                .order_by(Transaction.id.desc())
                .limit(25)
            )
        )
        .scalars()
        .all()
    )
    payments, _ = await payments_service.list_payments(session, user_id=user_id, limit=25)
    return {
        "user": UserPublic.model_validate(target).model_dump(mode="json"),
        "transactions": [TransactionPublic.model_validate(t).model_dump(mode="json") for t in transactions],
        "payments": [StarPaymentPublic.model_validate(p).model_dump(mode="json") for p in payments],
    }


@router.post("/users/{user_id}/ban", response_model=OkResponse)
async def ban_user(user_id: int, payload: BanRequest, admin: AdminUser, session: SessionDep) -> OkResponse:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    if target.is_admin:
        raise ValidationError("Administrators cannot be banned")

    target.is_banned = True
    target.ban_reason = payload.reason
    await session.commit()
    logger.warning("user_banned", extra={"admin_id": admin.id, "user_id": user_id})
    return OkResponse(message="User banned")


@router.post("/users/{user_id}/unban", response_model=OkResponse)
async def unban_user(user_id: int, admin: AdminUser, session: SessionDep) -> OkResponse:
    target = await session.get(User, user_id)
    if target is None:
        raise NotFoundError("User not found")
    target.is_banned = False
    target.ban_reason = None
    await session.commit()
    logger.warning("user_unbanned", extra={"admin_id": admin.id, "user_id": user_id})
    return OkResponse(message="User unbanned")


@router.post("/users/{user_id}/balance")
async def adjust_balance(
    user_id: int, payload: AdjustBalanceRequest, admin: AdminUser, session: SessionDep
) -> dict:
    """Grant or remove GG. Recorded in the ledger like any other movement."""
    if payload.amount == 0:
        raise ValidationError("amount must not be zero")

    target = await lock_user(session, user_id)
    await apply_change(
        session,
        target,
        amount=payload.amount,
        tx_type=TransactionType.ADMIN_ADJUSTMENT,
        reference_id=f"admin:{admin.id}",
        description=payload.description or f"Adjustment by admin #{admin.id}",
        extra={"admin_id": admin.id},
    )
    await session.commit()
    logger.warning(
        "balance_adjusted",
        extra={"admin_id": admin.id, "user_id": user_id, "amount": payload.amount},
    )
    return {"ok": True, "user_id": user_id, "balance": int(target.balance)}


# --------------------------------------------------------------------------- #
# money
# --------------------------------------------------------------------------- #
@router.get("/transactions")
async def list_transactions(
    admin: AdminUser,
    session: SessionDep,
    user_id: int | None = None,
    type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(Transaction)
    count_stmt = select(func.count()).select_from(Transaction)
    if user_id:
        stmt = stmt.where(Transaction.user_id == user_id)
        count_stmt = count_stmt.where(Transaction.user_id == user_id)
    if type:
        stmt = stmt.where(Transaction.type == type)
        count_stmt = count_stmt.where(Transaction.type == type)

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (await session.execute(stmt.order_by(Transaction.id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    items = []
    for tx in rows:
        item = TransactionPublic.model_validate(tx).model_dump(mode="json")
        item["user_id"] = tx.user_id
        items.append(item)
    return make_page(items, total, limit, offset)


@router.get("/payments")
async def list_payments(
    admin: AdminUser,
    session: SessionDep,
    user_id: int | None = None,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows, total = await payments_service.list_payments(
        session, user_id=user_id, status=status, limit=limit, offset=offset
    )
    return make_page(
        [StarPaymentPublic.model_validate(p).model_dump(mode="json") for p in rows], total, limit, offset
    )


# --------------------------------------------------------------------------- #
# giveaways
# --------------------------------------------------------------------------- #
@router.post("/giveaways")
async def create_giveaway(
    payload: GiveawayCreateRequest, admin: AdminUser, session: SessionDep
) -> dict:
    giveaways_service.validate_prize_type(payload.prize_type)
    start_at = payload.start_at or datetime.now(UTC)
    if payload.end_at <= start_at:
        raise ValidationError("end_at must be after start_at")

    giveaway = Giveaway(
        title=payload.title,
        description=payload.description,
        image=payload.image,
        prize_type=payload.prize_type,
        prize_value=payload.prize_value,
        prize_payload=payload.prize_payload,
        entry_cost=payload.entry_cost,
        min_level=payload.min_level,
        max_participants=payload.max_participants,
        start_at=start_at,
        end_at=payload.end_at,
        status=payload.status,
        created_by=admin.id,
    )
    session.add(giveaway)
    await session.commit()
    await session.refresh(giveaway)
    logger.info("giveaway_created", extra={"admin_id": admin.id, "giveaway_id": giveaway.id})
    return serialize_giveaway(giveaway)


@router.patch("/giveaways/{giveaway_id}")
async def update_giveaway(
    giveaway_id: int, payload: GiveawayUpdateRequest, admin: AdminUser, session: SessionDep
) -> dict:
    giveaway = await session.get(Giveaway, giveaway_id)
    if giveaway is None:
        raise NotFoundError("Giveaway not found")
    if giveaway.status == GiveawayStatus.FINISHED.value:
        raise ValidationError("A finished giveaway cannot be edited")

    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(giveaway, field, value)
    if giveaway.end_at <= giveaway.start_at:
        raise ValidationError("end_at must be after start_at")

    await session.commit()
    await session.refresh(giveaway)
    return serialize_giveaway(giveaway)


@router.post("/giveaways/{giveaway_id}/finish")
async def finish_giveaway(giveaway_id: int, admin: AdminUser, session: SessionDep) -> dict:
    """Draw the winner immediately, before `end_at` if necessary."""
    giveaway = await giveaways_service.draw_winner(session, giveaway_id, force=True)
    await session.commit()
    await session.refresh(giveaway)
    winner = await session.get(User, giveaway.winner_id) if giveaway.winner_id else None
    logger.warning("giveaway_finished_manually", extra={"admin_id": admin.id, "giveaway_id": giveaway_id})
    return serialize_giveaway(giveaway, winner=winner)


# --------------------------------------------------------------------------- #
# games
# --------------------------------------------------------------------------- #
@router.get("/pvp")
async def list_pvp(
    admin: AdminUser,
    session: SessionDep,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(PvPGame)
    count_stmt = select(func.count()).select_from(PvPGame)
    if status:
        stmt = stmt.where(PvPGame.status == status)
        count_stmt = count_stmt.where(PvPGame.status == status)

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (await session.execute(stmt.order_by(PvPGame.id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return make_page([await serialize_pvp(session, g) for g in rows], total, limit, offset)


@router.get("/solo")
async def list_solo(
    admin: AdminUser,
    session: SessionDep,
    user_id: int | None = None,
    game_type: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(SoloGame)
    count_stmt = select(func.count()).select_from(SoloGame)
    if user_id:
        stmt = stmt.where(SoloGame.user_id == user_id)
        count_stmt = count_stmt.where(SoloGame.user_id == user_id)
    if game_type:
        stmt = stmt.where(SoloGame.game_type == game_type)
        count_stmt = count_stmt.where(SoloGame.game_type == game_type)

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (await session.execute(stmt.order_by(SoloGame.id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    items = []
    for game in rows:
        item = SoloGamePublic.model_validate(game).model_dump(mode="json")
        item["user_id"] = game.user_id
        items.append(item)
    return make_page(items, total, limit, offset)
