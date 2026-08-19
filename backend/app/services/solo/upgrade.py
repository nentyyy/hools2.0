"""UPGRADE — pick a target multiplier, the backend rolls against its odds.

Win chance is `(1 - house_edge) / target`, so the expected return is the same at
every target and only the variance changes.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models import SoloGame, User
from app.services.solo import engine
from gg_shared import SoloGameType

MIN_TARGET = 1.1
MAX_TARGET = 50.0


def chance_for(target: float) -> float:
    return engine.payout_factor() / target


def validate_target(target: float) -> float:
    target = round(float(target), 2)
    if not (MIN_TARGET <= target <= MAX_TARGET):
        raise ValidationError(f"target must be between {MIN_TARGET} and {MAX_TARGET}")
    return target


async def play(
    session: AsyncSession,
    user_id: int,
    *,
    bet: int,
    target: float,
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame]:
    target = validate_target(target)
    chance = chance_for(target)

    user, game, seed = await engine.begin(
        session,
        user_id,
        SoloGameType.UPGRADE,
        bet,
        idempotency_key=idempotency_key,
        state={"target": target},
    )

    roll = engine.round_rolls(seed.server_seed, game, 0, 1)[0]
    won = roll < chance
    reward = round(int(game.bet) * target) if won else 0

    await engine.finish(
        session,
        user,
        game,
        reward=reward,
        multiplier=target if won else 0.0,
        result={
            "target": target,
            "chance": round(chance, 6),
            "roll": round(roll, 6),
            "won": won,
        },
        reveal_seed=seed.server_seed,
    )
    return user, game
