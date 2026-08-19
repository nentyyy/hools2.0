"""Realtime event names and the fan-out entry point.

Events are published to Redis so that every uvicorn worker (and every serverless
instance) delivers them to its own websocket clients. When Redis is unreachable
we still deliver to locally connected clients so a single-process deployment
keeps working.
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from app.core.redis import publish as redis_publish

logger = logging.getLogger(__name__)


class PvPEvent(StrEnum):
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    BALANCE_UPDATED = "balance_updated"
    GAME_STARTED = "game_started"
    COUNTDOWN = "countdown"
    WHEEL_STARTED = "wheel_started"
    WINNER_SELECTED = "winner_selected"
    GAME_FINISHED = "game_finished"
    STATE = "state"


def pvp_channel(game_id: int) -> str:
    return f"ws:pvp:{game_id}"


async def publish_pvp_event(game_id: int, event: PvPEvent | str, payload: dict[str, Any]) -> None:
    from app.ws.manager import manager  # imported late to avoid a circular import

    message = {"event": str(event), "game_id": game_id, "data": payload}
    try:
        await redis_publish(pvp_channel(game_id), message)
    except Exception:  # pragma: no cover - fall back to this process only
        logger.warning("redis fan-out failed, delivering locally", exc_info=True)
        await manager.broadcast_local(pvp_channel(game_id), message)
    # Keep a short replay buffer so HTTP pollers (serverless, no websockets)
    # can catch up on what they missed.
    await manager.remember(pvp_channel(game_id), message)
