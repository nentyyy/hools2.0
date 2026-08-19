"""Giveaway browsing and entry."""

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
from app.api.serializers import serialize_giveaway
from app.models import User
from app.schemas.common import make_page
from app.services import giveaways as service

router = APIRouter(prefix="/giveaways", tags=["giveaways"])


@router.get("", dependencies=[Depends(default_limit)])
async def list_giveaways(
    user: CurrentUser,
    session: SessionDep,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows, total = await service.list_giveaways(session, status=status, limit=limit, offset=offset)
    items = []
    for giveaway in rows:
        joined = await service.is_participant(session, giveaway.id, user.id)
        items.append(serialize_giveaway(giveaway, joined=joined))
    return make_page(items, total, limit, offset)


@router.get("/{giveaway_id}", dependencies=[Depends(default_limit)])
async def get_giveaway(giveaway_id: int, user: CurrentUser, session: SessionDep) -> dict:
    giveaway = await service.get_giveaway(session, giveaway_id)
    joined = await service.is_participant(session, giveaway.id, user.id)
    winner = await session.get(User, giveaway.winner_id) if giveaway.winner_id else None
    return serialize_giveaway(giveaway, joined=joined, winner=winner)


@router.post("/{giveaway_id}/join", dependencies=[Depends(play_limit)])
async def join_giveaway(
    giveaway_id: int,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "giveaway-join", user.id, idempotency_key, {"giveaway_id": giveaway_id}
    )
    if guard.cached:
        return guard.cached
    try:
        giveaway = await service.join(session, user, giveaway_id, idempotency_key=guard.key)
        await session.commit()
        await session.refresh(giveaway)
    except Exception:
        await guard.fail()
        raise
    await session.refresh(user)
    return await guard.finish(
        {**serialize_giveaway(giveaway, joined=True), "balance": int(user.balance)}
    )


@router.get("/{giveaway_id}/participants", dependencies=[Depends(default_limit)])
async def giveaway_participants(
    giveaway_id: int,
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    await service.get_giveaway(session, giveaway_id)
    rows, total = await service.participants(session, giveaway_id, limit=limit, offset=offset)
    items = [
        {
            "user_id": participant.user_id,
            "name": participant_user.display_name,
            "username": participant_user.username,
            "avatar": participant_user.avatar,
            "level": participant_user.level,
            "joined_at": participant.joined_at,
        }
        for participant, participant_user in rows
    ]
    return make_page(items, total, limit, offset)
