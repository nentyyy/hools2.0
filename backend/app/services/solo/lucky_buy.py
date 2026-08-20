"""LUCKY BUY — buy a chance at one specific gift.

You choose the gift and the odds; the stake follows from both:

    stake = gift value * chance / (1 - house_edge)

so the expected return is `1 - house_edge` at every setting, and the only thing
the slider changes is variance. Win and the gift lands in your inventory, where
it can be kept or sold for its value. Lose and the stake is gone.

The roll comes from the provably-fair stream, so a player can recompute any past
attempt once the seed is revealed.
"""

from __future__ import annotations

import math

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationError
from app.models import InventoryItem, SoloGame, User
from app.services import inventory
from app.services.solo import engine
from gg_shared import GIFTS, Gift, SoloGameType, SoloStatus, find_gift

MIN_CHANCE = 0.01
MAX_CHANCE = 0.90


def get_gift(code: str) -> Gift:
    gift = find_gift(code)
    if gift is None:
        raise ValidationError(f"Unknown gift: {code}")
    return gift


def validate_chance(chance: float) -> float:
    chance = round(float(chance), 4)
    if not (MIN_CHANCE <= chance <= MAX_CHANCE):
        raise ValidationError(f"chance must be between {MIN_CHANCE} and {MAX_CHANCE}")
    return chance


def stake_for(gift: Gift, chance: float) -> int:
    """What a given chance at this gift costs, rounded up in the house's favour."""
    return max(1, math.ceil(gift.gg_value * chance / engine.payout_factor()))


def catalogue(chance: float = 0.05) -> list[dict]:
    """Shop listing, priced at a sample chance so cards can show a starting price."""
    return [
        {
            "code": gift.code,
            "name": gift.name,
            "rarity": gift.rarity.value,
            "glyph": gift.glyph,
            "gg_value": gift.gg_value,
            "min_chance": MIN_CHANCE,
            "max_chance": MAX_CHANCE,
            "sample_chance": chance,
            "sample_stake": stake_for(gift, chance),
        }
        for gift in GIFTS
    ]


async def play(
    session: AsyncSession,
    user_id: int,
    *,
    gift_code: str,
    chance: float,
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame, InventoryItem | None]:
    gift = get_gift(gift_code)
    chance = validate_chance(chance)
    stake = stake_for(gift, chance)

    user, game, seed = await engine.begin(
        session,
        user_id,
        SoloGameType.LUCKY_BUY,
        stake,
        idempotency_key=idempotency_key,
        state={"gift": gift.code, "chance": chance},
    )

    roll = engine.round_rolls(seed.server_seed, game, 0, 1)[0]
    won = roll < chance

    item: InventoryItem | None = None
    if won:
        item = await inventory.add_item(
            session,
            user_id,
            item_type="gift",
            item_code=gift.code,
            name=gift.name,
            rarity=gift.rarity,
            gg_value=gift.gg_value,
            source=f"lucky_buy:{game.id}",
            extra={"glyph": gift.glyph, "chance": chance},
        )

    # The prize is the gift itself; selling it is what turns it into GG.
    await engine.finish(
        session,
        user,
        game,
        reward=gift.gg_value if won else 0,
        multiplier=gift.gg_value / stake if won and stake else 0.0,
        result={
            "gift": {
                "code": gift.code,
                "name": gift.name,
                "rarity": gift.rarity.value,
                "glyph": gift.glyph,
                "gg_value": gift.gg_value,
            },
            "chance": chance,
            "stake": stake,
            "roll": round(roll, 6),
            "won": won,
            "item_id": item.id if item else None,
        },
        status=SoloStatus.FINISHED,
        credit=False,
        reveal_seed=seed.server_seed,
    )
    if won:
        user.solo_wins += 1
    return user, game, item
