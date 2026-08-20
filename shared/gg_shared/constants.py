"""Enums and catalogues that both the backend and the bot must agree on.

Everything money-related lives here so a package price can never drift between
the invoice the bot creates and the credit the backend applies.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TransactionType(StrEnum):
    """Every mutation of the GG ledger carries one of these types."""

    STARS_TOPUP = "stars_topup"
    STARS_REFUND = "stars_refund"
    PVP_BET = "pvp_bet"
    PVP_WIN = "pvp_win"
    PVP_REFUND = "pvp_refund"
    SOLO_BET = "solo_bet"
    SOLO_WIN = "solo_win"
    GIVEAWAY_REWARD = "giveaway_reward"
    REFERRAL_BONUS = "referral_bonus"
    ADMIN_ADJUSTMENT = "admin_adjustment"


class PvPMode(StrEnum):
    """Wheel and ice rounds are separate games — bets never mix between them."""

    WHEEL = "wheel"
    ICE = "ice"


class PvPStatus(StrEnum):
    WAITING = "waiting"
    STARTING = "starting"
    SPINNING = "spinning"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class SoloGameType(StrEnum):
    PLINKO = "plinko"
    UPGRADE = "upgrade"
    LUCKY_BUY = "lucky_buy"
    HI_LO = "hi_lo"
    ICE_ARENA = "ice_arena"


class SoloStatus(StrEnum):
    """Instant games go straight to FINISHED; round based games sit in ACTIVE."""

    ACTIVE = "active"
    FINISHED = "finished"
    CASHED_OUT = "cashed_out"
    LOST = "lost"


class GiveawayStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    FINISHED = "finished"
    CANCELLED = "cancelled"


class ItemRarity(StrEnum):
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    EPIC = "epic"
    LEGENDARY = "legendary"


@dataclass(frozen=True, slots=True)
class GGPackage:
    """A purchasable amount of GG. `stars` is the price in XTR."""

    code: str
    title: str
    gg: int
    stars: int
    bonus_gg: int = 0

    @property
    def total_gg(self) -> int:
        return self.gg + self.bonus_gg


# Telegram requires digital goods inside Mini Apps to be sold for Stars (XTR).
GG_PACKAGES: tuple[GGPackage, ...] = (
    GGPackage(code="gg_100", title="100 GG", gg=100, stars=50),
    GGPackage(code="gg_550", title="550 GG", gg=500, stars=250, bonus_gg=50),
    GGPackage(code="gg_1200", title="1200 GG", gg=1000, stars=500, bonus_gg=200),
    GGPackage(code="gg_3250", title="3250 GG", gg=2500, stars=1250, bonus_gg=750),
    GGPackage(code="gg_7000", title="7000 GG", gg=5000, stars=2500, bonus_gg=2000),
)


def find_package(code: str) -> GGPackage | None:
    return next((p for p in GG_PACKAGES if p.code == code), None)
