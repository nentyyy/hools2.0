from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class AuthRequest(BaseModel):
    """The Mini App sends the raw signed string and nothing else."""

    init_data: str = Field(min_length=1, max_length=8192, alias="initData")
    start_param: str | None = Field(default=None, max_length=64)

    model_config = {"populate_by_name": True}


class UserPublic(ORMModel):
    id: int
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    avatar: str | None = None
    balance: int
    xp: int
    level: int
    is_banned: bool
    is_admin: bool
    referral_code: str
    referral_id: int | None = None
    created_at: datetime
    updated_at: datetime


class AuthResponse(BaseModel):
    token: str
    expires_in: int
    user: UserPublic
    is_new: bool


class BalanceResponse(BaseModel):
    balance: int
    currency: str = "GG"


class LevelInfo(BaseModel):
    level: int
    xp: int
    xp_into_level: int
    xp_needed: int
    xp_next_level: int
    progress: float


class ProfileStats(BaseModel):
    pvp_wins: int
    pvp_games: int
    solo_wins: int
    solo_games: int
    total_wagered: int
    total_earned: int
    stars_spent: int


class ReferralSummary(BaseModel):
    code: str
    link: str
    invited_count: int
    earnings: int


class InventoryItemPublic(ORMModel):
    id: int
    item_type: str
    item_code: str
    name: str
    image: str | None = None
    rarity: str
    quantity: int
    gg_value: int
    is_sold: bool
    source: str | None = None
    created_at: datetime


class TransactionPublic(ORMModel):
    id: int
    type: str
    amount: int
    balance_before: int
    balance_after: int
    reference_id: str | None = None
    description: str | None = None
    created_at: datetime


class ProfileResponse(BaseModel):
    user: UserPublic
    level: LevelInfo
    stats: ProfileStats
    referrals: ReferralSummary
    inventory: list[InventoryItemPublic]
    transactions: list[TransactionPublic]


class ReferralUser(BaseModel):
    id: int
    name: str
    username: str | None = None
    avatar: str | None = None
    level: int
    joined_at: datetime


class ReferralsResponse(BaseModel):
    code: str
    link: str
    invited_count: int
    earnings: int
    signup_bonus: int
    topup_percent: float
    referrals: list[ReferralUser]
