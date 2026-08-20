"""Solo game endpoints.

Each mode has its own POST endpoint. The request carries the bet and the
player's choice; the response carries the outcome the backend computed and
already wrote to the database.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.api.deps import (
    CurrentUser,
    IdempotencyKey,
    SessionDep,
    default_limit,
    idempotency_guard,
    play_limit,
)
from app.core.config import settings
from app.core.errors import ValidationError
from app.models import SoloGame
from app.schemas.common import make_page
from app.schemas.game import (
    HiLoPlayRequest,
    IceArenaPlayRequest,
    LuckyBuyPlayRequest,
    PlinkoPlayRequest,
    SoloGamePublic,
    UpgradePlayRequest,
)
from app.services.solo import hilo, ice_arena, lucky_buy, plinko, upgrade

router = APIRouter(prefix="/solo", tags=["solo"])


def _response(game: SoloGame, balance: int, state: dict | None = None) -> dict:
    return {
        "game": SoloGamePublic.model_validate(game).model_dump(mode="json"),
        "balance": balance,
        "state": state,
    }


@router.get("/shop", dependencies=[Depends(default_limit)])
async def shop(chance: float = 0.05) -> dict:
    """Every gift Lucky Buy can be played for, priced at a sample chance."""
    return {
        "gifts": lucky_buy.catalogue(lucky_buy.validate_chance(chance)),
        "min_chance": lucky_buy.MIN_CHANCE,
        "max_chance": lucky_buy.MAX_CHANCE,
        "house_edge": settings.house_edge,
    }


@router.get("/config", dependencies=[Depends(default_limit)])
async def config() -> dict:
    """Everything the client needs to render odds without guessing at them."""
    return {
        "limits": {"min_bet": settings.solo_min_bet, "max_bet": settings.solo_max_bet},
        "house_edge": settings.house_edge,
        "plinko": {
            "rows": list(plinko.ROWS),
            "risks": list(plinko.RISKS),
            "tables": {
                f"{rows}:{risk}": plinko.multiplier_table(rows, risk)
                for rows in plinko.ROWS
                for risk in plinko.RISKS
            },
        },
        "upgrade": {
            "min_target": upgrade.MIN_TARGET,
            "max_target": upgrade.MAX_TARGET,
            "presets": [
                {"target": t, "chance": round(upgrade.chance_for(t), 4)}
                for t in (1.5, 2.0, 3.0, 5.0, 10.0, 20.0)
            ],
        },
        "lucky_buy": {
            "min_chance": lucky_buy.MIN_CHANCE,
            "max_chance": lucky_buy.MAX_CHANCE,
            "gifts": lucky_buy.catalogue(),
        },
        "hi_lo": {"max_rounds": hilo.MAX_ROUNDS, "choices": list(hilo.CHOICES)},
        "ice_arena": {
            "max_rounds": ice_arena.MAX_ROUNDS,
            "difficulties": [
                {"difficulty": name, "chance": chance, "step": ice_arena.step_multiplier(name)}
                for name, chance in ice_arena.DIFFICULTIES.items()
            ],
        },
    }


@router.post("/plinko/play", dependencies=[Depends(play_limit)])
async def play_plinko(
    payload: PlinkoPlayRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "plinko", user.id, idempotency_key, payload.model_dump(), auto=False
    )
    if guard.cached:
        return guard.cached
    try:
        player, game = await plinko.play(
            session,
            user.id,
            bet=payload.bet,
            rows=payload.rows,
            risk=payload.risk,
            idempotency_key=guard.key,
        )
        await session.commit()
    except Exception:
        await guard.fail()
        raise
    return await guard.finish(_response(game, int(player.balance)))


@router.post("/upgrade/play", dependencies=[Depends(play_limit)])
async def play_upgrade(
    payload: UpgradePlayRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "upgrade", user.id, idempotency_key, payload.model_dump(), auto=False
    )
    if guard.cached:
        return guard.cached
    try:
        player, game = await upgrade.play(
            session, user.id, bet=payload.bet, target=payload.target, idempotency_key=guard.key
        )
        await session.commit()
    except Exception:
        await guard.fail()
        raise
    return await guard.finish(_response(game, int(player.balance)))


@router.post("/lucky-buy/play", dependencies=[Depends(play_limit)])
async def play_lucky_buy(
    payload: LuckyBuyPlayRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "lucky-buy", user.id, idempotency_key, payload.model_dump(), auto=False
    )
    if guard.cached:
        return guard.cached
    try:
        player, game, item = await lucky_buy.play(
            session,
            user.id,
            gift_code=payload.gift,
            chance=payload.chance,
            idempotency_key=guard.key,
        )
        await session.commit()
    except Exception:
        await guard.fail()
        raise

    response = _response(game, int(player.balance))
    response["item"] = (
        {
            "id": item.id,
            "name": item.name,
            "rarity": item.rarity,
            "gg_value": int(item.gg_value),
            "code": item.item_code,
        }
        if item
        else None
    )
    return await guard.finish(response)


@router.post("/hilo/play", dependencies=[Depends(play_limit)])
async def play_hilo(
    payload: HiLoPlayRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "hilo", user.id, idempotency_key, payload.model_dump(), auto=False
    )
    if guard.cached:
        return guard.cached
    try:
        if payload.action == "start":
            if not payload.bet:
                raise ValidationError("bet is required to start a round")
            player, game = await hilo.start(
                session, user.id, bet=payload.bet, idempotency_key=guard.key
            )
        elif payload.action == "guess":
            if not payload.game_id or not payload.choice:
                raise ValidationError("game_id and choice are required")
            player, game = await hilo.guess(
                session,
                user.id,
                game_id=payload.game_id,
                choice=payload.choice,
                idempotency_key=guard.key,
            )
        else:
            if not payload.game_id:
                raise ValidationError("game_id is required")
            player, game = await hilo.cash_out(session, user.id, game_id=payload.game_id)
        await session.commit()
    except Exception:
        await guard.fail()
        raise
    return await guard.finish(_response(game, int(player.balance), hilo.public_state(game)))


@router.post("/ice-arena/play", dependencies=[Depends(play_limit)])
async def play_ice_arena(
    payload: IceArenaPlayRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> dict:
    guard = await idempotency_guard(
        "ice-arena", user.id, idempotency_key, payload.model_dump(), auto=False
    )
    if guard.cached:
        return guard.cached
    try:
        if payload.action == "start":
            if not payload.bet:
                raise ValidationError("bet is required to start a run")
            player, game = await ice_arena.start(
                session, user.id, bet=payload.bet, idempotency_key=guard.key
            )
        elif payload.action == "advance":
            if not payload.game_id or not payload.difficulty:
                raise ValidationError("game_id and difficulty are required")
            player, game = await ice_arena.advance(
                session,
                user.id,
                game_id=payload.game_id,
                difficulty=payload.difficulty,
                idempotency_key=guard.key,
            )
        else:
            if not payload.game_id:
                raise ValidationError("game_id is required")
            player, game = await ice_arena.cash_out(session, user.id, game_id=payload.game_id)
        await session.commit()
    except Exception:
        await guard.fail()
        raise
    return await guard.finish(_response(game, int(player.balance), ice_arena.public_state(game)))


@router.get("/active", dependencies=[Depends(default_limit)])
async def active_rounds(user: CurrentUser, session: SessionDep) -> dict:
    """Lets the client restore an unfinished Hi-Lo or Ice Arena run."""
    from app.services.solo.engine import find_active
    from gg_shared import SoloGameType

    hilo_game = await find_active(session, user.id, SoloGameType.HI_LO)
    ice_game = await find_active(session, user.id, SoloGameType.ICE_ARENA)
    return {
        "hi_lo": hilo.public_state(hilo_game) if hilo_game else None,
        "ice_arena": ice_arena.public_state(ice_game) if ice_game else None,
    }


@router.get("/history", dependencies=[Depends(default_limit)])
async def history(
    user: CurrentUser,
    session: SessionDep,
    game_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(SoloGame).where(SoloGame.user_id == user.id)
    count_stmt = select(func.count()).select_from(SoloGame).where(SoloGame.user_id == user.id)
    if game_type:
        stmt = stmt.where(SoloGame.game_type == game_type)
        count_stmt = count_stmt.where(SoloGame.game_type == game_type)

    total = int(await session.scalar(count_stmt) or 0)
    rows = (
        (await session.execute(stmt.order_by(SoloGame.id.desc()).limit(limit).offset(offset)))
        .scalars()
        .all()
    )
    return make_page(
        [SoloGamePublic.model_validate(g).model_dump(mode="json") for g in rows], total, limit, offset
    )
