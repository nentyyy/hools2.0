"""Giveaways: joining, drawing a winner and paying the prize.

The draw runs under a Redis lock plus a row lock and flips the status inside the
same transaction that credits the winner, so it can never pay out twice even if
the cron tick and an HTTP request race each other.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.redis import distributed_lock
from app.models import Giveaway, GiveawayParticipant, User
from app.services import inventory
from app.services.ledger import apply_change, lock_user
from gg_shared import GiveawayStatus, ItemRarity, TransactionType

logger = logging.getLogger(__name__)

PRIZE_TYPES = ("gg", "item", "external")


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


async def list_giveaways(
    session: AsyncSession,
    *,
    status: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> tuple[list[Giveaway], int]:
    stmt = select(Giveaway)
    count_stmt = select(func.count()).select_from(Giveaway)
    if status:
        stmt = stmt.where(Giveaway.status == status)
        count_stmt = count_stmt.where(Giveaway.status == status)
    else:
        stmt = stmt.where(Giveaway.status != GiveawayStatus.DRAFT.value)
        count_stmt = count_stmt.where(Giveaway.status != GiveawayStatus.DRAFT.value)

    total = int(await session.scalar(count_stmt) or 0)
    rows = list(
        (
            await session.execute(
                stmt.order_by(Giveaway.status.asc(), Giveaway.end_at.asc()).limit(limit).offset(offset)
            )
        ).scalars().all()
    )

    # Draw any giveaway whose window closed. Doing this on read means a winner
    # appears as soon as someone looks, rather than waiting for the next cron
    # tick — which matters on hosts where cron only runs once a day.
    resolved = [await finish_if_due(session, giveaway) for giveaway in rows]
    return resolved, total


async def get_giveaway(session: AsyncSession, giveaway_id: int) -> Giveaway:
    giveaway = await session.get(Giveaway, giveaway_id)
    if giveaway is None or giveaway.status == GiveawayStatus.DRAFT.value:
        raise NotFoundError("Giveaway not found")
    return await finish_if_due(session, giveaway)


def is_due(giveaway: Giveaway) -> bool:
    return giveaway.status == GiveawayStatus.ACTIVE.value and _aware(giveaway.end_at) <= _now()


async def finish_if_due(session: AsyncSession, giveaway: Giveaway) -> Giveaway:
    """Resolve an expired giveaway, or return it untouched.

    Safe to call from any read path: the draw itself is guarded by a Redis lock
    and a row lock, so a hundred simultaneous readers still produce one winner.
    """
    if not is_due(giveaway):
        return giveaway
    try:
        finished = await draw_winner(session, giveaway.id)
        await session.commit()
        return finished
    except ConflictError:
        # Another worker is drawing it right now; show the current state.
        await session.rollback()
        return giveaway
    except Exception:  # pragma: no cover - a failed draw must not break the list
        await session.rollback()
        logger.exception("could not finish giveaway %s on read", giveaway.id)
        return giveaway


async def is_participant(session: AsyncSession, giveaway_id: int, user_id: int) -> bool:
    return bool(
        await session.scalar(
            select(func.count())
            .select_from(GiveawayParticipant)
            .where(
                GiveawayParticipant.giveaway_id == giveaway_id,
                GiveawayParticipant.user_id == user_id,
            )
        )
    )


async def participants(
    session: AsyncSession, giveaway_id: int, *, limit: int = 100, offset: int = 0
) -> tuple[list[tuple[GiveawayParticipant, User]], int]:
    total = int(
        await session.scalar(
            select(func.count())
            .select_from(GiveawayParticipant)
            .where(GiveawayParticipant.giveaway_id == giveaway_id)
        )
        or 0
    )
    rows = (
        await session.execute(
            select(GiveawayParticipant, User)
            .join(User, User.id == GiveawayParticipant.user_id)
            .where(GiveawayParticipant.giveaway_id == giveaway_id)
            .order_by(GiveawayParticipant.joined_at.desc())
            .limit(limit)
            .offset(offset)
        )
    ).all()
    return [(p, u) for p, u in rows], total


async def join(
    session: AsyncSession, user: User, giveaway_id: int, *, idempotency_key: str | None = None
) -> Giveaway:
    """Enter a giveaway. The unique (giveaway, user) index makes this safe to retry."""
    async with distributed_lock(f"giveaway:{giveaway_id}", ttl=10):
        giveaway = await session.scalar(
            select(Giveaway)
            .where(Giveaway.id == giveaway_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if giveaway is None or giveaway.status == GiveawayStatus.DRAFT.value:
            raise NotFoundError("Giveaway not found")
        if giveaway.status != GiveawayStatus.ACTIVE.value:
            raise ConflictError("This giveaway is closed")

        now = _now()
        if now < _aware(giveaway.start_at):
            raise ConflictError("This giveaway has not started yet")
        if now >= _aware(giveaway.end_at):
            raise ConflictError("This giveaway has already ended")
        if giveaway.max_participants and giveaway.participants_count >= giveaway.max_participants:
            raise ConflictError("Participant limit reached")
        if user.level < giveaway.min_level:
            raise ConflictError(f"Level {giveaway.min_level} required to enter")

        entry = GiveawayParticipant(giveaway_id=giveaway.id, user_id=user.id)
        try:
            async with session.begin_nested():
                session.add(entry)
        except IntegrityError as exc:
            raise ConflictError("You have already joined this giveaway") from exc

        if giveaway.entry_cost > 0:
            locked = await lock_user(session, user.id)
            await apply_change(
                session,
                locked,
                amount=-int(giveaway.entry_cost),
                tx_type=TransactionType.ADMIN_ADJUSTMENT,
                reference_id=f"giveaway:{giveaway.id}",
                description=f"Entry fee — {giveaway.title}",
                idempotency_key=idempotency_key or f"giveaway-join:{user.id}:{giveaway.id}",
            )

        giveaway.participants_count = int(giveaway.participants_count) + 1
        await session.flush()

    logger.info("giveaway_joined", extra={"giveaway_id": giveaway.id, "user_id": user.id})
    return giveaway


async def draw_winner(session: AsyncSession, giveaway_id: int, *, force: bool = False) -> Giveaway:
    """Pick a winner and pay the prize. Idempotent: a finished giveaway is returned as is."""
    async with distributed_lock(f"giveaway:{giveaway_id}", ttl=30):
        giveaway = await session.scalar(
            select(Giveaway)
            .where(Giveaway.id == giveaway_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if giveaway is None:
            raise NotFoundError("Giveaway not found")
        if giveaway.status == GiveawayStatus.FINISHED.value:
            return giveaway
        if giveaway.status == GiveawayStatus.CANCELLED.value:
            raise ConflictError("Giveaway was cancelled")
        if not force and _now() < _aware(giveaway.end_at):
            raise ConflictError("Giveaway has not ended yet")

        rows = (
            await session.execute(
                select(GiveawayParticipant.user_id)
                .where(GiveawayParticipant.giveaway_id == giveaway.id)
                .order_by(GiveawayParticipant.id)
            )
        ).scalars().all()

        if not rows:
            giveaway.status = GiveawayStatus.CANCELLED.value
            giveaway.finished_at = _now()
            await session.flush()
            logger.info("giveaway_cancelled_empty", extra={"giveaway_id": giveaway.id})
            return giveaway

        # secrets.choice draws from the OS CSPRNG — no seed to leak or predict.
        winner_id = secrets.choice(list(rows))
        giveaway.winner_id = winner_id
        giveaway.status = GiveawayStatus.FINISHED.value
        giveaway.finished_at = _now()

        await _pay_prize(session, giveaway, winner_id)
        await session.flush()

    logger.info(
        "giveaway_finished",
        extra={"giveaway_id": giveaway.id, "winner_id": winner_id, "participants": len(rows)},
    )
    return giveaway


async def _pay_prize(session: AsyncSession, giveaway: Giveaway, winner_id: int) -> None:
    if giveaway.prize_type == "gg" and giveaway.prize_value > 0:
        winner = await lock_user(session, winner_id)
        await apply_change(
            session,
            winner,
            amount=int(giveaway.prize_value),
            tx_type=TransactionType.GIVEAWAY_REWARD,
            reference_id=f"giveaway:{giveaway.id}",
            description=f"Giveaway prize — {giveaway.title}",
            idempotency_key=f"giveaway-prize:{giveaway.id}",
        )
    elif giveaway.prize_type == "item":
        payload = giveaway.prize_payload or {}
        await inventory.add_item(
            session,
            winner_id,
            item_type="giveaway",
            item_code=payload.get("code", f"giveaway_{giveaway.id}"),
            name=payload.get("name", giveaway.title),
            rarity=payload.get("rarity", ItemRarity.EPIC.value),
            gg_value=int(giveaway.prize_value or 0),
            image=giveaway.image,
            source=f"giveaway:{giveaway.id}",
        )
    # "external" prizes are handed over manually by an admin.


async def tick(session: AsyncSession, limit: int = 25) -> int:
    """Close every giveaway whose window has elapsed."""
    rows = (
        await session.execute(
            select(Giveaway)
            .where(Giveaway.status == GiveawayStatus.ACTIVE.value, Giveaway.end_at <= _now())
            .order_by(Giveaway.end_at)
            .limit(limit)
        )
    ).scalars().all()

    finished = 0
    for giveaway in rows:
        try:
            await draw_winner(session, giveaway.id)
            await session.commit()
            finished += 1
        except ConflictError:
            await session.rollback()
        except Exception:  # pragma: no cover
            await session.rollback()
            logger.exception("giveaway tick failed for %s", giveaway.id)
    return finished


def validate_prize_type(prize_type: str) -> str:
    if prize_type not in PRIZE_TYPES:
        raise ValidationError(f"prize_type must be one of {list(PRIZE_TYPES)}")
    return prize_type
