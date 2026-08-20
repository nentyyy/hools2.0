from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# --------------------------------------------------------------------------- #
# PvP
# --------------------------------------------------------------------------- #
class PvPPlayerPublic(BaseModel):
    user_id: int
    name: str
    username: str | None = None
    avatar: str | None = None
    amount: int
    chance: float
    ticket_from: int
    ticket_to: int
    is_winner: bool


class PvPGamePublic(BaseModel):
    id: int
    status: str
    mode: str
    total_pool: int
    prize: int
    rake: int
    min_bet: int
    max_players: int
    creator_id: int
    winner_id: int | None = None
    players: list[PvPPlayerPublic]
    created_at: datetime
    started_at: datetime | None = None
    spin_at: datetime | None = None
    finished_at: datetime | None = None
    server_seed_hash: str
    server_seed: str | None = None
    client_seed: str
    nonce: int
    winning_roll: float | None = None
    countdown_seconds: int
    spin_seconds: int
    server_time: datetime


class PvPCreateRequest(BaseModel):
    amount: int = Field(ge=1, le=10_000_000)
    mode: Literal["wheel", "ice"] = "wheel"


class PvPJoinRequest(BaseModel):
    amount: int = Field(ge=1, le=10_000_000)
    # Only quick-join uses this; joining a specific round takes its mode.
    mode: Literal["wheel", "ice"] = "wheel"


class PvPStateResponse(BaseModel):
    game: PvPGamePublic
    events: list[dict[str, Any]] = []
    cursor: int = 0


# --------------------------------------------------------------------------- #
# Solo
# --------------------------------------------------------------------------- #
class SoloGamePublic(ORMModel):
    id: int
    game_type: str
    status: str
    bet: int
    reward: int
    multiplier: float
    result: dict[str, Any] | None = None
    state: dict[str, Any] | None = None
    server_seed_hash: str
    server_seed: str | None = None
    client_seed: str
    nonce: int
    created_at: datetime
    finished_at: datetime | None = None


class SoloPlayResponse(BaseModel):
    game: SoloGamePublic
    balance: int
    state: dict[str, Any] | None = None


class PlinkoPlayRequest(BaseModel):
    bet: int = Field(ge=1, le=10_000_000)
    rows: int = Field(default=12)
    risk: Literal["low", "medium", "high"] = "medium"


class UpgradePlayRequest(BaseModel):
    bet: int = Field(ge=1, le=10_000_000)
    target: float = Field(ge=1.1, le=50.0)


class LuckyBuyPlayRequest(BaseModel):
    """Play for one specific gift at the odds the player picked."""

    gift: str = Field(min_length=1, max_length=32)
    chance: float = Field(ge=0.01, le=0.9)


class HiLoPlayRequest(BaseModel):
    action: Literal["start", "guess", "cash_out"]
    bet: int | None = Field(default=None, ge=1, le=10_000_000)
    game_id: int | None = None
    choice: Literal["higher", "lower", "same"] | None = None


class IceArenaPlayRequest(BaseModel):
    action: Literal["start", "advance", "cash_out"]
    bet: int | None = Field(default=None, ge=1, le=10_000_000)
    game_id: int | None = None
    difficulty: Literal["easy", "normal", "hard", "extreme"] | None = None


# --------------------------------------------------------------------------- #
# Giveaways
# --------------------------------------------------------------------------- #
class GiveawayPublic(ORMModel):
    id: int
    title: str
    description: str | None = None
    image: str | None = None
    prize_type: str
    prize_value: int
    prize_payload: dict[str, Any] | None = None
    entry_cost: int
    min_level: int
    max_participants: int | None = None
    participants_count: int
    start_at: datetime
    end_at: datetime
    status: str
    winner_id: int | None = None
    finished_at: datetime | None = None
    created_at: datetime


class GiveawayDetail(GiveawayPublic):
    joined: bool = False
    winner: dict[str, Any] | None = None


class GiveawayParticipantPublic(BaseModel):
    user_id: int
    name: str
    username: str | None = None
    avatar: str | None = None
    level: int
    joined_at: datetime
