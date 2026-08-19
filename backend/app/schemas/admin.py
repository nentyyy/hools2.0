from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class BanRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=256)


class AdjustBalanceRequest(BaseModel):
    amount: int = Field(description="Signed amount of GG to add (negative removes)")
    description: str | None = Field(default=None, max_length=256)


class GiveawayCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=128)
    description: str | None = None
    image: str | None = Field(default=None, max_length=512)
    prize_type: str = "gg"
    prize_value: int = Field(default=0, ge=0)
    prize_payload: dict | None = None
    entry_cost: int = Field(default=0, ge=0)
    min_level: int = Field(default=1, ge=1)
    max_participants: int | None = Field(default=None, ge=1)
    start_at: datetime | None = None
    end_at: datetime
    status: str = "active"


class GiveawayUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=128)
    description: str | None = None
    image: str | None = Field(default=None, max_length=512)
    prize_type: str | None = None
    prize_value: int | None = Field(default=None, ge=0)
    prize_payload: dict | None = None
    entry_cost: int | None = Field(default=None, ge=0)
    min_level: int | None = Field(default=None, ge=1)
    max_participants: int | None = Field(default=None, ge=1)
    start_at: datetime | None = None
    end_at: datetime | None = None
    status: str | None = None
