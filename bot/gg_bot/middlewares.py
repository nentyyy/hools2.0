"""Update logging and a small per-user throttle."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

logger = logging.getLogger(__name__)


class LoggingMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        started = time.perf_counter()
        try:
            return await handler(event, data)
        except Exception:
            logger.exception(
                "handler failed",
                extra={"user_id": getattr(user, "id", None), "update": type(event).__name__},
            )
            raise
        finally:
            logger.info(
                "update handled",
                extra={
                    "user_id": getattr(user, "id", None),
                    "update": type(event).__name__,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )


class ThrottleMiddleware(BaseMiddleware):
    """Drops bursts from a single user so a held-down button cannot flood the API."""

    def __init__(self, rate: float = 0.4) -> None:
        self.rate = rate
        self._last: dict[int, float] = defaultdict(float)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        if user is not None:
            now = time.monotonic()
            if now - self._last[user.id] < self.rate:
                if isinstance(event, Update) and event.callback_query:
                    await event.callback_query.answer("Slow down a little")
                logger.debug("throttled user %s", user.id)
                return None
            self._last[user.id] = now
        return await handler(event, data)


def describe(event: Message | CallbackQuery) -> str:  # pragma: no cover - debug helper
    if isinstance(event, Message):
        return f"message:{event.text!r}"
    return f"callback:{event.data!r}"
