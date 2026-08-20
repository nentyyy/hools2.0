"""The gift catalogue.

Gifts are what Lucky Buy plays for: you pick one, pick the odds you want, and
the stake follows from both. Values are in GG and are the single source of truth
for pricing, so the shop, the game and the inventory cannot disagree.
"""

from __future__ import annotations

from dataclasses import dataclass

from gg_shared.constants import ItemRarity


@dataclass(frozen=True, slots=True)
class Gift:
    code: str
    name: str
    rarity: ItemRarity
    gg_value: int
    glyph: str


GIFTS: tuple[Gift, ...] = (
    Gift("candle", "Desert Candle", ItemRarity.COMMON, 100, "🕯"),
    Gift("teddy", "Sand Teddy", ItemRarity.COMMON, 250, "🧸"),
    Gift("rose", "Pale Rose", ItemRarity.UNCOMMON, 500, "🌹"),
    Gift("champagne", "Champagne", ItemRarity.UNCOMMON, 900, "🍾"),
    Gift("perfume", "Amber Perfume", ItemRarity.RARE, 1_800, "🧴"),
    Gift("ring", "Bonded Ring", ItemRarity.RARE, 3_500, "💍"),
    Gift("hourglass", "Gold Hourglass", ItemRarity.EPIC, 7_000, "⏳"),
    Gift("goblet", "Ivory Goblet", ItemRarity.EPIC, 12_000, "🏆"),
    Gift("crown", "Sand Crown", ItemRarity.LEGENDARY, 25_000, "👑"),
    Gift("comet", "Amber Comet", ItemRarity.LEGENDARY, 50_000, "☄️"),
)


def find_gift(code: str) -> Gift | None:
    return next((gift for gift in GIFTS if gift.code == code), None)
