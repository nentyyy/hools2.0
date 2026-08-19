"""PvP lobbies. Every outcome is computed by the backend."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    CurrentUser,
    IdempotencyKey,
    SessionDep,
    default_limit,
    idempotency_guard,
    play_limit,
)
from app.api.serializers import serialize_pvp
from app.core.config import settings
from app.schemas.game import PvPCreateRequest, PvPJoinRequest
from app.services import pvp as pvp_service
from app.ws.events import pvp_channel
from app.ws.manager import manager
from gg_shared import PvPStatus

router = APIRouter(prefix="/pvp", tags=["pvp"])


@router.get("", dependencies=[Depends(default_limit)])
async def list_games(
    session: SessionDep,
    user: CurrentUser,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    statuses = (
        [status]
        if status
        else [PvPStatus.WAITING.value, PvPStatus.STARTING.value, PvPStatus.SPINNING.value]
    )
    games = await pvp_service.list_games(session, statuses=statuses, limit=limit, offset=offset)
    return {
        "items": [await serialize_pvp(session, g) for g in games],
        "config": {
            "min_bet": settings.pvp_min_bet,
            "max_bet": settings.pvp_max_bet,
            "rake_percent": settings.pvp_rake_percent,
            "countdown_seconds": settings.pvp_countdown_seconds,
            "spin_seconds": settings.pvp_spin_seconds,
            "max_players": settings.pvp_max_players,
        },
    }


@router.post("/create", dependencies=[Depends(play_limit)])
async def create_game(
    payload: PvPCreateRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard("pvp-create", user.id, idempotency_key, payload.model_dump())
    if guard.cached:
        return guard.cached
    try:
        game = await pvp_service.create_game(
            session, user, payload.amount, idempotency_key=guard.key
        )
        await session.commit()
        await session.refresh(game)
    except Exception:
        await guard.fail()
        raise

    await session.refresh(user)
    return await guard.finish(
        {"game": await serialize_pvp(session, game), "balance": int(user.balance)}
    )


@router.post("/{game_id}/join", dependencies=[Depends(play_limit)])
async def join_game(
    game_id: int,
    payload: PvPJoinRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "pvp-join", user.id, idempotency_key, {"game_id": game_id, **payload.model_dump()}
    )
    if guard.cached:
        return guard.cached
    try:
        game = await pvp_service.join_game(
            session, user, game_id, payload.amount, idempotency_key=guard.key
        )
        await session.commit()
        await session.refresh(game)
    except Exception:
        await guard.fail()
        raise

    await session.refresh(user)
    return await guard.finish(
        {"game": await serialize_pvp(session, game), "balance": int(user.balance)}
    )


@router.get("/{game_id}", dependencies=[Depends(default_limit)])
async def get_game(game_id: int, user: CurrentUser, session: SessionDep) -> dict:
    game = await pvp_service.get_game(session, game_id)
    return {"game": await serialize_pvp(session, game)}


@router.get("/{game_id}/state", dependencies=[Depends(default_limit)])
async def game_state(
    game_id: int,
    user: CurrentUser,
    session: SessionDep,
    cursor: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    """Polling fallback for environments without websockets (e.g. serverless).

    Returns the authoritative state plus any realtime events after `cursor`.
    """
    game = await pvp_service.get_game(session, game_id)
    events = await manager.replay(pvp_channel(game_id), since=cursor)
    return {
        "game": await serialize_pvp(session, game),
        "events": events,
        "cursor": cursor + len(events),
    }
