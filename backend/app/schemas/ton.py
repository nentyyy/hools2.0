from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class TonProofDomain(BaseModel):
    lengthBytes: int | None = None  # noqa: N815 - TON Connect wire format
    value: str


class TonProof(BaseModel):
    timestamp: int
    domain: TonProofDomain
    signature: str
    payload: str


class TonConnectRequest(BaseModel):
    address: str = Field(min_length=1, max_length=128)
    public_key: str | None = Field(default=None, max_length=128)
    friendly_address: str | None = Field(default=None, max_length=128)
    chain: str | None = Field(default=None, max_length=16)
    wallet_name: str | None = Field(default=None, max_length=64)
    proof: TonProof | None = None


class TonWalletPublic(ORMModel):
    address: str
    friendly_address: str | None = None
    chain: str | None = None
    wallet_name: str | None = None
    proof_verified_at: datetime | None = None
    connected_at: datetime | None = None


class TonWalletResponse(BaseModel):
    connected: bool
    wallet: TonWalletPublic | None = None
    proof_payload: str | None = None
    receiver_address: str | None = None
    manifest_url: str | None = None


class TonVerifyRequest(BaseModel):
    boc_hash: str = Field(min_length=4, max_length=128)
    tx_hash: str | None = Field(default=None, max_length=128)
    expected_amount_nano: int | None = Field(default=None, ge=0)
    comment: str | None = Field(default=None, max_length=256)
    purpose: str | None = Field(default=None, max_length=32)


class TonTransactionPublic(ORMModel):
    id: int
    boc_hash: str
    tx_hash: str | None = None
    from_address: str | None = None
    to_address: str | None = None
    amount_nano: int
    amount_ton: float
    comment: str | None = None
    purpose: str | None = None
    status: str
    created_at: datetime
    confirmed_at: datetime | None = None
