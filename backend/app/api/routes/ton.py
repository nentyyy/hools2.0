"""TON Connect endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentUser, SessionDep, default_limit, play_limit
from app.core.config import settings
from app.schemas.common import OkResponse
from app.schemas.ton import (
    TonConnectRequest,
    TonTransactionPublic,
    TonVerifyRequest,
    TonWalletPublic,
    TonWalletResponse,
)
from app.services import ton as service

router = APIRouter(prefix="/ton", tags=["ton"])


@router.get("/wallet", response_model=TonWalletResponse, dependencies=[Depends(default_limit)])
async def wallet(user: CurrentUser, session: SessionDep) -> TonWalletResponse:
    """Current wallet plus a fresh ton_proof challenge for connecting one."""
    record = await service.get_wallet(session, user.id)
    payload = await service.issue_proof_payload(user.id)
    return TonWalletResponse(
        connected=record is not None,
        wallet=TonWalletPublic.model_validate(record) if record else None,
        proof_payload=payload,
        receiver_address=settings.ton_receiver_address or None,
        manifest_url=settings.ton_manifest_url or None,
    )


@router.post("/connect", response_model=TonWalletPublic, dependencies=[Depends(play_limit)])
async def connect(payload: TonConnectRequest, user: CurrentUser, session: SessionDep) -> TonWalletPublic:
    record = await service.connect_wallet(
        session,
        user,
        address=payload.address,
        proof=payload.proof.model_dump() if payload.proof else None,
        public_key=payload.public_key,
        friendly_address=payload.friendly_address,
        chain=payload.chain,
        wallet_name=payload.wallet_name,
    )
    await session.commit()
    return TonWalletPublic.model_validate(record)


@router.post("/disconnect", response_model=OkResponse, dependencies=[Depends(play_limit)])
async def disconnect(user: CurrentUser, session: SessionDep) -> OkResponse:
    await service.disconnect_wallet(session, user.id)
    await session.commit()
    return OkResponse(message="Wallet disconnected")


@router.post("/verify", response_model=TonTransactionPublic, dependencies=[Depends(play_limit)])
async def verify(payload: TonVerifyRequest, user: CurrentUser, session: SessionDep) -> TonTransactionPublic:
    """Check a transfer on chain and store the result."""
    record = await service.verify_transaction(
        session,
        user,
        boc_hash=payload.boc_hash,
        tx_hash=payload.tx_hash,
        expected_amount_nano=payload.expected_amount_nano,
        comment=payload.comment,
        purpose=payload.purpose,
    )
    await session.commit()
    return TonTransactionPublic.model_validate(record)


@router.get("/transactions", dependencies=[Depends(default_limit)])
async def transactions(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows = await service.list_transactions(session, user.id, limit=limit, offset=offset)
    return {
        "items": [TonTransactionPublic.model_validate(r).model_dump(mode="json") for r in rows],
        "receiver_address": settings.ton_receiver_address or None,
    }
