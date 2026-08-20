"""PvP lobbies. Every outcome is computed by the backend."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select

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
from app.core.redis import online_count
from app.models import PvPGame, User
from app.schemas.game import PvPCreateRequest, PvPJoinRequest
from app.services import pvp as pvp_service
from app.ws.events import pvp_channel
from app.ws.manager import manager
from gg_shared import PvPStatus

router = APIRouter(prefix="/pvp", tags=["pvp"])


def _config() -> dict:
    return {
        "min_bet": settings.pvp_min_bet,
        "max_bet": settings.pvp_max_bet,
        "rake_percent": settings.pvp_rake_percent,
        "countdown_seconds": settings.pvp_countdown_seconds,
        "spin_seconds": settings.pvp_spin_seconds,
        "max_players": settings.pvp_max_players,
    }


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
    return {"items": [await serialize_pvp(session, g) for g in games], "config": _config()}


@router.get("/current", dependencies=[Depends(default_limit)])
async def current(session: SessionDep, user: CurrentUser) -> dict:
    """The round the arena shows: the live one, or the last finished result."""
    game = await pvp_service.current_game(session)
    await session.commit()
    return {
        "game": await serialize_pvp(session, game) if game else None,
        "config": _config(),
    }


@router.post("/quick-join", dependencies=[Depends(play_limit)])
async def quick_join(
    payload: PvPJoinRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    """Join the current round, or open one when none is running."""
    guard = await idempotency_guard("pvp-quick", user.id, idempotency_key, payload.model_dump())
    if guard.cached:
        return guard.cached
    try:
        game, created = await pvp_service.quick_join(
            session, user, payload.amount, idempotency_key=guard.key
        )
        await session.commit()
        await session.refresh(game)
    except Exception:
        await guard.fail()
        raise

    await session.refresh(user)
    return await guard.finish(
        {
            "game": await serialize_pvp(session, game),
            "balance": int(user.balance),
            "created": created,
        }
    )


@router.get("/highlights", dependencies=[Depends(default_limit)])
async def highlights(session: SessionDep, user: CurrentUser) -> dict:
    """Ticker data for the arena header: the last round, the biggest one, online."""
    finished = [PvPStatus.FINISHED.value]

    last = await session.scalar(
        select(PvPGame)
        .where(PvPGame.status.in_(finished), PvPGame.winner_id.isnot(None))
        .order_by(PvPGame.finished_at.desc())
        .limit(1)
    )
    top = await session.scalar(
        select(PvPGame)
        .where(PvPGame.status.in_(finished), PvPGame.winner_id.isnot(None))
        .order_by(PvPGame.total_pool.desc())
        .limit(1)
    )

    async def summarise(game: PvPGame | None) -> dict | None:
        if game is None:
            return None
        winner = await session.get(User, game.winner_id)
        seat = next((p for p in game.players if p.user_id == game.winner_id), None)
        return {
            "game_id": game.id,
            "prize": int(game.prize),
            "pool": int(game.total_pool),
            "chance": round(seat.chance, 4) if seat else None,
            "winner": {
                "id": winner.id,
                "name": winner.display_name,
                "username": winner.username,
                "avatar": winner.avatar,
            }
            if winner
            else None,
        }

    return {
        "last": await summarise(last),
        "top": await summarise(top),
        "online": await online_count(),
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
