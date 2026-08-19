"""Shared plumbing for every solo mode."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rng
from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import GameSeed, SoloGame, SoloRound, User
from app.services.ledger import apply_change, lock_user
from app.services.leveling import xp_for_wager
from app.services.seeds import next_nonce
from gg_shared import SoloGameType, SoloStatus, TransactionType

logger = logging.getLogger(__name__)


def validate_bet(bet: int) -> int:
    bet = int(bet)
    if bet < settings.solo_min_bet:
        raise ValidationError(f"Minimum bet is {settings.solo_min_bet} GG")
    if bet > settings.solo_max_bet:
        raise ValidationError(f"Maximum bet is {settings.solo_max_bet} GG")
    return bet


def payout_factor() -> float:
    """Fraction of the wagered amount returned to players on average."""
    return 1.0 - settings.house_edge


async def begin(
    session: AsyncSession,
    user_id: int,
    game_type: SoloGameType,
    bet: int,
    *,
    idempotency_key: str | None = None,
    state: dict | None = None,
) -> tuple[User, SoloGame, GameSeed]:
    """Take the bet and open a game row. Caller computes the outcome next."""
    bet = validate_bet(bet)

    # Locking the seed first serialises this user's rounds; the ledger lock on
    # the user row then makes the debit itself race free.
    seed = await next_nonce(session, user_id)
    user = await lock_user(session, user_id)

    game = SoloGame(
        user_id=user_id,
        game_type=game_type.value,
        status=SoloStatus.ACTIVE.value,
        bet=bet,
        reward=0,
        multiplier=0.0,
        state=state or {},
        server_seed_hash=seed.server_seed_hash,
        client_seed=seed.client_seed,
        nonce=seed.nonce,
    )
    session.add(game)
    await session.flush()

    await apply_change(
        session,
        user,
        amount=-bet,
        tx_type=TransactionType.SOLO_BET,
        reference_id=f"solo:{game.id}",
        description=f"{game_type.value} bet",
        idempotency_key=idempotency_key or f"solo-bet:{user_id}:{game.id}",
    )
    user.solo_games += 1
    return user, game, seed


async def lock_user_for(session: AsyncSession, user_id: int) -> User:
    """Re-export of the ledger row lock so game modules keep a single import."""
    return await lock_user(session, user_id)


async def finish(
    session: AsyncSession,
    user: User,
    game: SoloGame,
    *,
    reward: int,
    multiplier: float,
    result: dict,
    status: SoloStatus = SoloStatus.FINISHED,
    credit: bool = True,
    reveal_seed: str | None = None,
) -> SoloGame:
    """Close a round, optionally paying out the reward."""
    reward = max(int(reward), 0)
    game.reward = reward
    game.multiplier = round(float(multiplier), 4)
    game.result = result
    game.status = status.value
    game.finished_at = datetime.now(UTC)
    if reveal_seed:
        game.server_seed = reveal_seed

    if reward > 0 and credit:
        await apply_change(
            session,
            user,
            amount=reward,
            tx_type=TransactionType.SOLO_WIN,
            reference_id=f"solo:{game.id}",
            description=f"{game.game_type} win x{game.multiplier:g}",
            idempotency_key=f"solo-win:{game.id}",
            extra={"multiplier": game.multiplier},
            xp=xp_for_wager(int(game.bet)),
        )
        user.solo_wins += 1
    elif reward == 0:
        # Losing still earns XP: the wager is what counts.
        from app.services.leveling import grant_xp

        grant_xp(user, xp_for_wager(int(game.bet)))

    await session.flush()
    logger.info(
        "solo_round",
        extra={
            "user_id": user.id,
            "game_id": game.id,
            "game_type": game.game_type,
            "bet": int(game.bet),
            "reward": reward,
            "multiplier": game.multiplier,
        },
    )
    return game


async def load_active(session: AsyncSession, user_id: int, game_id: int, game_type: SoloGameType) -> SoloGame:
    """Fetch a round-based game for update, verifying ownership."""
    game = await session.scalar(
        select(SoloGame)
        .where(SoloGame.id == game_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if game is None:
        raise NotFoundError("Game not found")
    if game.user_id != user_id:
        raise NotFoundError("Game not found")  # do not leak other players' games
    if game.game_type != game_type.value:
        raise ValidationError("Game type mismatch")
    if game.status != SoloStatus.ACTIVE.value:
        raise ConflictError("This round is already finished")
    return game


async def find_active(session: AsyncSession, user_id: int, game_type: SoloGameType) -> SoloGame | None:
    return await session.scalar(
        select(SoloGame)
        .where(
            SoloGame.user_id == user_id,
            SoloGame.game_type == game_type.value,
            SoloGame.status == SoloStatus.ACTIVE.value,
        )
        .order_by(SoloGame.id.desc())
    )


def round_rolls(server_seed: str, game: SoloGame, round_index: int, count: int = 1) -> list[float]:
    """Deterministic randomness for round `round_index` of a multi-round game.

    The server seed lives in `game_seeds` while the round is in progress and is
    copied onto the game row only once it ends, so a player can recompute every
    round afterwards but never predict the next one.
    """
    stream = rng.floats(server_seed, game.client_seed, int(game.nonce), (round_index + 1) * count)
    return stream[round_index * count : (round_index + 1) * count]


async def add_round(
    session: AsyncSession,
    game: SoloGame,
    *,
    round_number: int,
    difficulty: str,
    success_chance: float,
    possible_reward: int,
    roll: float,
    survived: bool,
    payload: dict | None = None,
) -> SoloRound:
    row = SoloRound(
        game_id=game.id,
        round_number=round_number,
        difficulty=difficulty,
        success_chance=round(success_chance, 6),
        possible_reward=possible_reward,
        roll=roll,
        survived=survived,
        payload=payload,
    )
    session.add(row)
    await session.flush()
    return row
