"""LUCKY BUY — open a case and receive an item.

Item values are expressed as multiples of the case price and normalised so that
the expected value of a case is exactly `price * (1 - house_edge)`. The item
lands in the inventory; selling it is what turns it into GG.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rng
from app.core.errors import ValidationError
from app.models import InventoryItem, SoloGame, User
from app.services import inventory
from app.services.solo import engine
from gg_shared import ItemRarity, SoloGameType, SoloStatus


@dataclass(frozen=True, slots=True)
class CaseItem:
    code: str
    name: str
    rarity: ItemRarity
    value: float  # multiple of the case price, before normalisation
    weight: float


@dataclass(frozen=True, slots=True)
class Case:
    code: str
    title: str
    price: int
    items: tuple[CaseItem, ...]


CASES: tuple[Case, ...] = (
    Case(
        code="frost",
        title="Frost Case",
        price=100,
        items=(
            CaseItem("ice_shard", "Ice Shard", ItemRarity.COMMON, 0.2, 46),
            CaseItem("frost_charm", "Frost Charm", ItemRarity.UNCOMMON, 0.8, 30),
            CaseItem("glacier_core", "Glacier Core", ItemRarity.RARE, 2.0, 16),
            CaseItem("winter_crown", "Winter Crown", ItemRarity.EPIC, 6.0, 6.5),
            CaseItem("absolute_zero", "Absolute Zero", ItemRarity.LEGENDARY, 25.0, 1.5),
        ),
    ),
    Case(
        code="neon",
        title="Neon Case",
        price=500,
        items=(
            CaseItem("neon_chip", "Neon Chip", ItemRarity.COMMON, 0.25, 44),
            CaseItem("pulse_blade", "Pulse Blade", ItemRarity.UNCOMMON, 0.9, 31),
            CaseItem("grid_runner", "Grid Runner", ItemRarity.RARE, 2.4, 17),
            CaseItem("hyper_visor", "Hyper Visor", ItemRarity.EPIC, 7.0, 6),
            CaseItem("singularity", "Singularity", ItemRarity.LEGENDARY, 40.0, 2),
        ),
    ),
    Case(
        code="vault",
        title="Vault Case",
        price=2000,
        items=(
            CaseItem("token_stack", "Token Stack", ItemRarity.COMMON, 0.3, 42),
            CaseItem("gold_ingot", "Gold Ingot", ItemRarity.UNCOMMON, 1.0, 32),
            CaseItem("black_card", "Black Card", ItemRarity.RARE, 2.6, 18),
            CaseItem("vault_key", "Vault Key", ItemRarity.EPIC, 8.0, 6),
            CaseItem("jackpot_core", "Jackpot Core", ItemRarity.LEGENDARY, 60.0, 2),
        ),
    ),
)


def get_case(code: str) -> Case:
    case = next((c for c in CASES if c.code == code), None)
    if case is None:
        raise ValidationError(f"Unknown case: {code}")
    return case


def normalised_values(case: Case) -> list[float]:
    """Scale the raw item values so the case returns `payout_factor()` on average."""
    weights = [item.weight for item in case.items]
    total_weight = sum(weights)
    expected = sum(item.value * item.weight for item in case.items) / total_weight
    scale = engine.payout_factor() / expected
    return [round(item.value * scale, 4) for item in case.items]


def case_odds(case: Case) -> list[dict]:
    total_weight = sum(item.weight for item in case.items)
    values = normalised_values(case)
    return [
        {
            "code": item.code,
            "name": item.name,
            "rarity": item.rarity.value,
            "chance": round(item.weight / total_weight, 6),
            "gg_value": round(case.price * value),
        }
        for item, value in zip(case.items, values, strict=True)
    ]


async def play(
    session: AsyncSession,
    user_id: int,
    *,
    case_code: str,
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame, InventoryItem]:
    case = get_case(case_code)

    user, game, seed = await engine.begin(
        session,
        user_id,
        SoloGameType.LUCKY_BUY,
        case.price,
        idempotency_key=idempotency_key,
        state={"case": case.code},
    )

    roll = engine.round_rolls(seed.server_seed, game, 0, 1)[0]
    index = rng.weighted_pick(
        [i.value for i in case.items], [i.weight for i in case.items], roll
    )
    won = case.items[index]
    value = round(case.price * normalised_values(case)[index])

    item = await inventory.add_item(
        session,
        user_id,
        item_type="case_drop",
        item_code=won.code,
        name=won.name,
        rarity=won.rarity,
        gg_value=value,
        source=f"lucky_buy:{game.id}",
        extra={"case": case.code},
    )

    # The prize is the item, not GG: it is credited when the player sells it.
    await engine.finish(
        session,
        user,
        game,
        reward=value,
        multiplier=value / case.price if case.price else 0.0,
        result={
            "case": case.code,
            "item": {
                "id": item.id,
                "code": won.code,
                "name": won.name,
                "rarity": won.rarity.value,
                "gg_value": value,
            },
            "roll": round(roll, 6),
            "odds": case_odds(case),
        },
        status=SoloStatus.FINISHED,
        credit=False,
        reveal_seed=seed.server_seed,
    )
    if value > case.price:
        user.solo_wins += 1
    return user, game, item
