"""PLINKO — a ball falls through `rows` pegs and lands in one of rows+1 slots.

The landing slot is binomially distributed. Multipliers are derived from that
distribution rather than hand-tuned: a shape function sets how aggressive the
edges are (that is what "risk" means), then the whole table is normalised so the
return to player is exactly `1 - house_edge` for every risk/row combination.
"""

from __future__ import annotations

from math import comb

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models import SoloGame, User
from app.services.solo import engine
from gg_shared import SoloGameType

ROWS = (8, 12, 16)
RISKS = {"low": 1.6, "medium": 2.6, "high": 3.8}
CENTER_FLOOR = {"low": 0.55, "medium": 0.25, "high": 0.1}


def _probabilities(rows: int) -> list[float]:
    total = 2**rows
    return [comb(rows, i) / total for i in range(rows + 1)]


def multiplier_table(rows: int, risk: str) -> list[float]:
    """Payout for each slot, left to right."""
    if rows not in ROWS:
        raise ValidationError(f"rows must be one of {list(ROWS)}")
    if risk not in RISKS:
        raise ValidationError(f"risk must be one of {list(RISKS)}")

    probs = _probabilities(rows)
    exponent = RISKS[risk]
    floor = CENTER_FLOOR[risk]
    center = rows / 2

    shape = [floor + (abs(i - center) / center) ** exponent * (1 - floor) for i in range(rows + 1)]
    # Normalise so that sum(p_i * m_i) == payout_factor().
    expected = sum(p * s for p, s in zip(probs, shape, strict=True))
    scale = engine.payout_factor() / expected
    return [round(s * scale, 4) for s in shape]


def drop(rolls: list[float]) -> tuple[list[str], int]:
    """Turn one roll per row into a path and the resulting slot index."""
    path = ["R" if roll >= 0.5 else "L" for roll in rolls]
    return path, sum(1 for step in path if step == "R")


async def play(
    session: AsyncSession,
    user_id: int,
    *,
    bet: int,
    rows: int = 12,
    risk: str = "medium",
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame]:
    table = multiplier_table(rows, risk)

    user, game, seed = await engine.begin(
        session,
        user_id,
        SoloGameType.PLINKO,
        bet,
        idempotency_key=idempotency_key,
        state={"rows": rows, "risk": risk},
    )

    rolls = engine.round_rolls(seed.server_seed, game, 0, rows)
    path, slot = drop(rolls)
    multiplier = table[slot]
    reward = round(int(game.bet) * multiplier)

    await engine.finish(
        session,
        user,
        game,
        reward=reward,
        multiplier=multiplier,
        result={
            "rows": rows,
            "risk": risk,
            "path": path,
            "slot": slot,
            "multiplier": multiplier,
            "multipliers": table,
            "rolls": [round(r, 6) for r in rolls],
        },
        reveal_seed=seed.server_seed,
    )
    return user, game
