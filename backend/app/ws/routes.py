"""Realtime PvP websocket.

    /ws/pvp/{game_id}?token=<session jwt>

The socket is read-mostly: the client may send `ping` or `state`, everything
else is ignored. All game state changes come from the backend.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.api.serializers import serialize_pvp
from app.core.db import SessionFactory
from app.core.errors import AppError
from app.core.security import decode_access_token
from app.services import pvp as pvp_service
from app.ws.events import PvPEvent, pvp_channel
from app.ws.manager import manager
from gg_shared import PvPStatus

logger = logging.getLogger(__name__)
router = APIRouter()

HEARTBEAT_SECONDS = 25


@router.websocket("/ws/pvp/{game_id}")
async def pvp_socket(websocket: WebSocket, game_id: int, token: str = Query(default="")) -> None:
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub", 0))
    except (AppError, TypeError, ValueError):
        await websocket.close(code=4401, reason="Invalid or missing token")
        return

    channel = pvp_channel(game_id)
    await manager.connect(channel, websocket)
    pump: asyncio.Task | None = None

    try:
        await _send_state(websocket, game_id)
        pump = asyncio.create_task(_state_pump(websocket, game_id))

        while True:
            message = await websocket.receive_text()
            if message == "ping":
                await manager.send(websocket, {"event": "pong"})
            elif message == "state":
                await _send_state(websocket, game_id)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - a broken socket must not leak a task
        logger.warning("ws error on game %s", game_id, exc_info=True)
    finally:
        if pump:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await pump
        await manager.disconnect(channel, websocket)
        logger.debug("ws closed", extra={"game_id": game_id, "user_id": user_id})


async def _send_state(websocket: WebSocket, game_id: int) -> None:
    async with SessionFactory() as session:
        try:
            game = await pvp_service.get_game(session, game_id)
            payload = await serialize_pvp(session, game)
            await manager.send(
                websocket, {"event": PvPEvent.STATE.value, "game_id": game_id, "data": payload}
            )
        except AppError as exc:
            await manager.send(websocket, {"event": "error", "data": {"message": exc.message}})


async def _state_pump(websocket: WebSocket, game_id: int) -> None:
    """Heartbeat that also drives the round's timers.

    `ensure_progress` is what turns the countdown into a spin and the spin into
    a result, so a connected client keeps the round moving even if no HTTP
    request or cron tick arrives.
    """
    while True:
        await asyncio.sleep(HEARTBEAT_SECONDS)
        async with SessionFactory() as session:
            try:
                game = await pvp_service.ensure_progress(session, game_id)
                await session.commit()
            except AppError:
                continue
            except Exception:  # pragma: no cover
                await session.rollback()
                logger.warning("state pump failed for %s", game_id, exc_info=True)
                continue

            if game.status in {PvPStatus.FINISHED.value, PvPStatus.CANCELLED.value}:
                await _send_state(websocket, game_id)
                return
            await manager.send(websocket, {"event": "heartbeat", "game_id": game_id})
