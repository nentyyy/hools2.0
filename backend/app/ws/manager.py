"""Websocket connection manager with a Redis pub/sub bridge."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

from app.core.redis import get_redis

logger = logging.getLogger(__name__)

REPLAY_LIMIT = 50
REPLAY_TTL = 600


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._tasks: dict[str, asyncio.Task] = {}
        self._lock = asyncio.Lock()

    async def connect(self, channel: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel].add(websocket)
            if channel not in self._tasks:
                self._tasks[channel] = asyncio.create_task(self._subscribe(channel))
        logger.info("ws_connected", extra={"channel": channel, "clients": len(self._connections[channel])})

    async def disconnect(self, channel: str, websocket: WebSocket) -> None:
        async with self._lock:
            self._connections[channel].discard(websocket)
            if not self._connections[channel]:
                self._connections.pop(channel, None)
                task = self._tasks.pop(channel, None)
                if task:
                    task.cancel()
        logger.info("ws_disconnected", extra={"channel": channel})

    async def broadcast_local(self, channel: str, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for websocket in list(self._connections.get(channel, ())):
            try:
                await websocket.send_json(message)
            except Exception:
                dead.append(websocket)
        for websocket in dead:
            await self.disconnect(channel, websocket)

    async def send(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        with contextlib.suppress(Exception):
            await websocket.send_json(message)

    async def remember(self, channel: str, message: dict[str, Any]) -> None:
        """Append to the replay buffer used by the HTTP polling fallback."""
        try:
            redis = get_redis()
            key = f"replay:{channel}"
            pipe = redis.pipeline()
            pipe.rpush(key, json.dumps(message, default=str))
            pipe.ltrim(key, -REPLAY_LIMIT, -1)
            pipe.expire(key, REPLAY_TTL)
            await pipe.execute()
        except Exception:  # pragma: no cover - replay is a convenience only
            logger.debug("replay buffer write failed for %s", channel)

    async def replay(self, channel: str, since: int = 0) -> list[dict[str, Any]]:
        try:
            raw = await get_redis().lrange(f"replay:{channel}", since, -1)
        except Exception:  # pragma: no cover
            return []
        out = []
        for item in raw:
            with contextlib.suppress(json.JSONDecodeError):
                out.append(json.loads(item))
        return out

    async def _subscribe(self, channel: str) -> None:
        """Relay everything published on `channel` to this process's clients."""
        pubsub = None
        try:
            pubsub = get_redis().pubsub()
            await pubsub.subscribe(channel)
            async for raw in pubsub.listen():
                if raw.get("type") != "message":
                    continue
                try:
                    message = json.loads(raw["data"])
                except (json.JSONDecodeError, TypeError):
                    continue
                await self.broadcast_local(channel, message)
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - reconnects on the next client
            logger.warning("pubsub bridge stopped for %s", channel, exc_info=True)
        finally:
            if pubsub is not None:
                with contextlib.suppress(Exception):
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()

    async def shutdown(self) -> None:
        for task in list(self._tasks.values()):
            task.cancel()
        self._tasks.clear()
        self._connections.clear()


manager = ConnectionManager()
