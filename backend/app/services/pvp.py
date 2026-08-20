"""Server-authoritative PvP.

A PvP round is a pot: every GG you put in buys one ticket, and the winner is the
holder of a single ticket drawn from the whole pot. Your chance is therefore
exactly your share of the pool.

The round is driven entirely by timestamps stored on the row (`spin_at`), not by
a live background task. Any request — a join, a poll, a websocket frame, a cron
tick — calls `ensure_progress()`, which advances the state machine under a
Redis lock plus a `SELECT ... FOR UPDATE`. That makes the outcome identical no
matter which worker gets there first, and impossible to compute twice.

The frontend never decides anything: it renders what the backend already wrote.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rng
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.redis import distributed_lock
from app.models import PvPGame, PvPPlayer, User
from app.services.ledger import apply_change, lock_user
from app.services.leveling import xp_for_wager
from app.ws.events import PvPEvent, publish_pvp_event
from gg_shared import PvPStatus, TransactionType

logger = logging.getLogger(__name__)

# A lobby nobody joined is refunded automatically after this long.
WAITING_TTL = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    """Postgres gives us tz-aware values; be defensive for SQLite/tests."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


async def _load_for_update(session: AsyncSession, game_id: int) -> PvPGame:
    game = await session.scalar(select(PvPGame)
        .where(PvPGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True))
    if game is None:
        raise NotFoundError("PvP game not found")
    return game


async def _players(session: AsyncSession, game_id: int, *, lock: bool = False) -> list[PvPPlayer]:
    stmt = select(PvPPlayer).where(PvPPlayer.game_id == game_id).order_by(PvPPlayer.id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return list((await session.execute(stmt)).scalars().all())


def _recalculate(game: PvPGame, players: list[PvPPlayer]) -> None:
    """Rebuild pool, ticket ranges and win chances from the players' bets."""
    total = sum(int(p.amount) for p in players)
    game.total_pool = total
    cursor = 0
    for player in players:
        player.ticket_from = cursor
        cursor += int(player.amount)
        player.ticket_to = cursor
        player.chance = round(int(player.amount) / total, 6) if total else 0.0


def validate_bet(amount: int) -> int:
    amount = int(amount)
    if amount < settings.pvp_min_bet:
        raise ValidationError(f"Minimum bet is {settings.pvp_min_bet} GG")
    if amount > settings.pvp_max_bet:
        raise ValidationError(f"Maximum bet is {settings.pvp_max_bet} GG")
    return amount


async def create_game(
    session: AsyncSession, user: User, amount: int, *, idempotency_key: str | None = None
) -> PvPGame:
    """Open a lobby and seat the creator with the first bet."""
    amount = validate_bet(amount)
    server_seed, server_hash = rng.new_server_seed()

    game = PvPGame(
        status=PvPStatus.WAITING.value,
        creator_id=user.id,
        min_bet=settings.pvp_min_bet,
        max_players=settings.pvp_max_players,
        server_seed=server_seed,
        server_seed_hash=server_hash,
        client_seed=rng.new_client_seed(),
        total_pool=0,
    )
    session.add(game)
    await session.flush()

    locked = await lock_user(session, user.id)
    await apply_change(
        session,
        locked,
        amount=-amount,
        tx_type=TransactionType.PVP_BET,
        reference_id=f"pvp:{game.id}",
        description=f"PvP #{game.id} entry",
        idempotency_key=idempotency_key or f"pvp-join:{user.id}:{game.id}",
    )
    locked.pvp_games += 1

    player = PvPPlayer(game_id=game.id, user_id=user.id, amount=amount)
    session.add(player)
    await session.flush()

    _recalculate(game, [player])
    game.nonce = game.id
    await session.flush()

    logger.info("pvp_created", extra={"game_id": game.id, "user_id": user.id, "amount": amount})
    return game


async def join_game(
    session: AsyncSession,
    user: User,
    game_id: int,
    amount: int,
    *,
    idempotency_key: str | None = None,
) -> PvPGame:
    """Take (or top up) a seat in an open lobby."""
    amount = validate_bet(amount)

    async with distributed_lock(f"pvp:{game_id}", ttl=15):
        game = await _load_for_update(session, game_id)
        await _advance(session, game, notify=True)

        if game.status not in {PvPStatus.WAITING.value, PvPStatus.STARTING.value}:
            raise ConflictError("This round is no longer accepting players")

        players = await _players(session, game.id, lock=True)
        existing = next((p for p in players if p.user_id == user.id), None)
        if existing is None and len(players) >= game.max_players:
            raise ConflictError("This round is full")

        locked = await lock_user(session, user.id)
        await apply_change(
            session,
            locked,
            amount=-amount,
            tx_type=TransactionType.PVP_BET,
            reference_id=f"pvp:{game.id}",
            description=f"PvP #{game.id} entry",
            idempotency_key=idempotency_key or f"pvp-join:{user.id}:{game.id}:{len(players)}",
        )

        if existing is None:
            locked.pvp_games += 1
            existing = PvPPlayer(game_id=game.id, user_id=user.id, amount=amount)
            session.add(existing)
            await session.flush()
            players.append(existing)
        else:
            existing.amount = int(existing.amount) + amount

        _recalculate(game, players)

        # Two or more players present: lock in the countdown exactly once.
        if len({p.user_id for p in players}) >= 2 and game.status == PvPStatus.WAITING.value:
            game.status = PvPStatus.STARTING.value
            game.started_at = _now()
            game.spin_at = game.started_at + timedelta(seconds=settings.pvp_countdown_seconds)

        await session.flush()

    await publish_pvp_event(
        game.id,
        PvPEvent.PLAYER_JOINED,
        {
            "user": {
                "id": user.id,
                "name": user.display_name,
                "avatar": user.avatar,
            },
            "amount": amount,
            "total_pool": game.total_pool,
            "players": [
                {"user_id": p.user_id, "amount": int(p.amount), "chance": p.chance} for p in players
            ],
        },
    )
    if game.status == PvPStatus.STARTING.value:
        await publish_pvp_event(
            game.id,
            PvPEvent.COUNTDOWN,
            {"spin_at": game.spin_at, "seconds": settings.pvp_countdown_seconds},
        )
    logger.info("pvp_joined", extra={"game_id": game.id, "user_id": user.id, "amount": amount})
    return game


def _join_grace() -> timedelta:
    """How close to the draw a round stops accepting new players.

    Scaled to the countdown so it behaves the same whether a round takes twenty
    seconds or one: joining as the wheel starts is what we want to avoid, not
    joining early.
    """
    seconds = min(max(settings.pvp_countdown_seconds * 0.25, 0.25), 3.0)
    return timedelta(seconds=seconds)


async def quick_join(
    session: AsyncSession, user: User, amount: int, *, idempotency_key: str | None = None
) -> tuple[PvPGame, bool]:
    """Seat the player in the current round, opening one if there is none.

    Matchmaking is serialised so two players pressing the button at the same
    moment end up in the same round rather than in two half-empty ones.
    Returns (game, created).
    """
    amount = validate_bet(amount)

    async with distributed_lock("pvp:matchmaking", ttl=10):
        now = _now()
        candidates = (
            await session.execute(
                select(PvPGame)
                .where(PvPGame.status.in_([PvPStatus.WAITING.value, PvPStatus.STARTING.value]))
                .order_by(PvPGame.created_at.desc())
                .limit(10)
            )
        ).scalars().all()

        for game in candidates:
            spin_at = _aware(game.spin_at)
            if spin_at and spin_at <= now + _join_grace():
                continue
            if len(game.players) >= game.max_players and not any(
                p.user_id == user.id for p in game.players
            ):
                continue
            return await join_game(session, user, game.id, amount, idempotency_key=idempotency_key), False

        return await create_game(session, user, amount, idempotency_key=idempotency_key), True


# How long a settled round keeps the arena before it clears for the next one.
RESULT_LINGER = timedelta(seconds=20)


async def current_game(session: AsyncSession) -> PvPGame | None:
    """The round the arena should show.

    A live round wins. Otherwise the last result lingers briefly so everyone can
    read it, and then the arena goes empty again — leaving a finished round on
    screen indefinitely makes a quiet lobby look like a frozen one.
    """
    live = await session.scalar(
        select(PvPGame)
        .where(
            PvPGame.status.in_(
                [PvPStatus.WAITING.value, PvPStatus.STARTING.value, PvPStatus.SPINNING.value]
            )
        )
        .order_by(PvPGame.created_at.desc())
        .limit(1)
    )
    if live is not None:
        return await ensure_progress(session, live.id)

    recent = await session.scalar(
        select(PvPGame)
        .where(PvPGame.status == PvPStatus.FINISHED.value)
        .order_by(PvPGame.finished_at.desc())
        .limit(1)
    )
    if recent is None:
        return None
    finished_at = _aware(recent.finished_at)
    return recent if finished_at and _now() - finished_at <= RESULT_LINGER else None


async def ensure_progress(session: AsyncSession, game_id: int) -> PvPGame:
    """Advance a round to whatever state its timestamps imply, then return it."""
    game = await session.get(PvPGame, game_id)
    if game is None:
        raise NotFoundError("PvP game not found")
    if not _needs_progress(game):
        return game

    async with distributed_lock(f"pvp:{game_id}", ttl=20, wait=3.0):
        game = await _load_for_update(session, game_id)
        await _advance(session, game, notify=True)
        await session.flush()
    return game


def _needs_progress(game: PvPGame) -> bool:
    now = _now()
    if game.status in {PvPStatus.FINISHED.value, PvPStatus.CANCELLED.value}:
        return False
    if game.status == PvPStatus.WAITING.value:
        return (_aware(game.created_at) or now) + WAITING_TTL <= now
    spin_at = _aware(game.spin_at)
    return spin_at is not None and now >= spin_at


async def _advance(session: AsyncSession, game: PvPGame, *, notify: bool) -> None:
    """State transitions. Safe to call repeatedly; only moves forward."""
    now = _now()

    if game.status == PvPStatus.WAITING.value:
        if (_aware(game.created_at) or now) + WAITING_TTL <= now:
            await _cancel(session, game, "No opponents joined in time", notify=notify)
        return

    spin_at = _aware(game.spin_at)
    if game.status == PvPStatus.STARTING.value and spin_at and now >= spin_at:
        game.status = PvPStatus.SPINNING.value
        # Publish the drawn ticket as the spin starts. The outcome is already
        # fixed by the seed at this point — joins are closed — and settlement
        # recomputes the very same number. Revealing it here is what lets every
        # client animate the same landing and finish together, instead of
        # learning the answer only once the animation window has passed.
        game.winning_roll = rng.single_float(
            game.server_seed or "", game.client_seed, game.nonce or game.id
        )
        if notify:
            await publish_pvp_event(
                game.id,
                PvPEvent.WHEEL_STARTED,
                {"duration": settings.pvp_spin_seconds, "total_pool": int(game.total_pool)},
            )

    if (
        game.status == PvPStatus.SPINNING.value
        and spin_at
        and now >= spin_at + timedelta(seconds=settings.pvp_spin_seconds)
    ):
        await _settle(session, game, notify=notify)


async def _cancel(session: AsyncSession, game: PvPGame, reason: str, *, notify: bool) -> None:
    """Refund every seat and close the lobby."""
    players = await _players(session, game.id, lock=True)
    for player in players:
        user = await lock_user(session, player.user_id)
        await apply_change(
            session,
            user,
            amount=int(player.amount),
            tx_type=TransactionType.PVP_REFUND,
            reference_id=f"pvp:{game.id}",
            description=f"PvP #{game.id} cancelled — bet refunded",
            idempotency_key=f"pvp-refund:{game.id}:{player.user_id}",
        )
        user.pvp_games = max(user.pvp_games - 1, 0)

    game.status = PvPStatus.CANCELLED.value
    game.finished_at = _now()
    await session.flush()
    logger.info("pvp_cancelled", extra={"game_id": game.id, "reason": reason})
    if notify:
        await publish_pvp_event(game.id, PvPEvent.GAME_FINISHED, {"status": game.status, "reason": reason})


async def _settle(session: AsyncSession, game: PvPGame, *, notify: bool) -> None:
    """Draw the winning ticket, pay out and write the result down. Runs once."""
    if game.status == PvPStatus.FINISHED.value:
        return

    players = await _players(session, game.id, lock=True)
    if len({p.user_id for p in players}) < 2:
        await _cancel(session, game, "Not enough players", notify=notify)
        return

    _recalculate(game, players)
    roll = rng.single_float(game.server_seed or "", game.client_seed, game.nonce or game.id)
    ticket = int(roll * int(game.total_pool))

    winner_player = next(
        (p for p in players if p.ticket_from <= ticket < p.ticket_to), players[-1]
    )

    rake = int(int(game.total_pool) * settings.pvp_rake_percent / 100)
    prize = int(game.total_pool) - rake

    game.rake = rake
    game.prize = prize
    game.winning_roll = roll
    game.winner_id = winner_player.user_id
    game.status = PvPStatus.FINISHED.value
    game.finished_at = _now()
    winner_player.is_winner = True

    winner = await lock_user(session, winner_player.user_id)
    await apply_change(
        session,
        winner,
        amount=prize,
        tx_type=TransactionType.PVP_WIN,
        reference_id=f"pvp:{game.id}",
        description=f"PvP #{game.id} win",
        idempotency_key=f"pvp-win:{game.id}",
        extra={"roll": roll, "pool": int(game.total_pool), "rake": rake},
        xp=xp_for_wager(int(game.total_pool)),
    )
    winner.pvp_wins += 1
    await session.flush()

    logger.info(
        "pvp_settled",
        extra={
            "game_id": game.id,
            "winner_id": winner.id,
            "pool": int(game.total_pool),
            "prize": prize,
            "roll": roll,
        },
    )

    if notify:
        payload = {
            "winner": {
                "user_id": winner.id,
                "name": winner.display_name,
                "avatar": winner.avatar,
                "chance": winner_player.chance,
            },
            "prize": prize,
            "rake": rake,
            "total_pool": int(game.total_pool),
            "roll": roll,
            "ticket": ticket,
            "server_seed": game.server_seed,
            "server_seed_hash": game.server_seed_hash,
            "client_seed": game.client_seed,
            "nonce": game.nonce,
        }
        await publish_pvp_event(game.id, PvPEvent.WINNER_SELECTED, payload)
        await publish_pvp_event(game.id, PvPEvent.GAME_FINISHED, {"status": game.status, **payload})


async def list_games(
    session: AsyncSession, *, statuses: list[str] | None = None, limit: int = 30, offset: int = 0
) -> list[PvPGame]:
    stmt = select(PvPGame).order_by(PvPGame.created_at.desc()).limit(limit).offset(offset)
    if statuses:
        stmt = stmt.where(PvPGame.status.in_(statuses))
    games = list((await session.execute(stmt)).scalars().all())

    # Lobbies shown in the list must not look alive when their timer has run out.
    for game in games:
        if _needs_progress(game):
            try:
                await ensure_progress(session, game.id)
                await session.commit()
            except ConflictError:  # another worker is already resolving it
                continue
    return games


async def get_game(session: AsyncSession, game_id: int) -> PvPGame:
    game = await session.get(PvPGame, game_id)
    if game is None:
        raise NotFoundError("PvP game not found")
    if _needs_progress(game):
        game = await ensure_progress(session, game_id)
        await session.commit()
        await session.refresh(game)
    return game


async def tick(session: AsyncSession, limit: int = 50) -> int:
    """Resolve every round whose timer has expired. Called by the cron worker."""
    stmt = (
        select(PvPGame)
        .where(PvPGame.status.in_([s.value for s in (PvPStatus.WAITING, PvPStatus.STARTING, PvPStatus.SPINNING)]))
        .order_by(PvPGame.created_at)
        .limit(limit)
    )
    processed = 0
    for game in (await session.execute(stmt)).scalars().all():
        if not _needs_progress(game):
            continue
        try:
            await ensure_progress(session, game.id)
            await session.commit()
            processed += 1
        except ConflictError:
            await session.rollback()
        except Exception:  # pragma: no cover - one bad round must not stop the rest
            await session.rollback()
            logger.exception("pvp tick failed for game %s", game.id)
    return processed
