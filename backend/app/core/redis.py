"""Redis client plus the two primitives we rely on for correctness:

* `distributed_lock` – guards state machines (PvP rounds, giveaway payouts)
  against two workers resolving the same thing twice.
* `idempotency` helpers – make a retried POST return the first response instead
  of charging the user again.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from redis.asyncio import Redis, from_url
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.errors import ConflictError

logger = logging.getLogger(__name__)

_redis: Redis | None = None

# Release the lock only if we still own it, so a lock that expired mid-work is
# never yanked out from under its new owner.
_UNLOCK_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
            health_check_interval=30,
        )
    return _redis


async def close_redis() -> None:
    global _redis
    if _redis is not None:
        await _redis.aclose()
        _redis = None


@asynccontextmanager
async def distributed_lock(
    name: str,
    *,
    ttl: int = 15,
    wait: float = 5.0,
    poll: float = 0.05,
) -> AsyncIterator[bool]:
    """Acquire `lock:{name}`; raises ConflictError if it cannot be taken in time."""
    redis = get_redis()
    key = f"lock:{name}"
    token = secrets.token_hex(16)
    deadline = asyncio.get_running_loop().time() + wait

    acquired = False
    while True:
        acquired = bool(await redis.set(key, token, nx=True, ex=ttl))
        if acquired or asyncio.get_running_loop().time() >= deadline:
            break
        await asyncio.sleep(poll)

    if not acquired:
        raise ConflictError("Resource is busy, try again in a moment")

    try:
        yield True
    finally:
        try:
            await redis.eval(_UNLOCK_SCRIPT, 1, key, token)
        except Exception:  # pragma: no cover - lock will expire on its own
            logger.warning("failed to release lock %s", key)


async def idempotency_begin(key: str, ttl: int = 86400) -> dict[str, Any] | None:
    """Claim an idempotency key.

    Returns None when the caller owns the key and should run the operation,
    or the stored response when the request was already processed. Raises
    ConflictError while an identical request is still in flight.

    If Redis is unavailable the caller proceeds without the replay cache: the
    unique constraints on `transactions.idempotency_key`, the PvP seat and the
    giveaway entry are what actually prevent a double spend, so degrading here
    costs a convenience, not a guarantee.
    """
    redis = get_redis()
    try:
        claimed = await redis.set(f"idem:{key}", json.dumps({"status": "in_progress"}), nx=True, ex=ttl)
        if claimed:
            return None

        raw = await redis.get(f"idem:{key}")
    except RedisError:
        logger.warning("idempotency store unavailable, relying on database constraints", exc_info=True)
        return None

    if not raw:
        return None
    stored = json.loads(raw)
    if stored.get("status") == "in_progress":
        raise ConflictError("An identical request is still being processed")
    return stored.get("response")


async def idempotency_store(key: str, response: Any, ttl: int = 86400) -> None:
    try:
        await get_redis().set(
            f"idem:{key}", json.dumps({"status": "done", "response": response}, default=str), ex=ttl
        )
    except RedisError:
        logger.warning("could not cache idempotent response for %s", key)


async def idempotency_release(key: str) -> None:
    """Drop the claim when the operation failed, so the client may retry."""
    try:
        await get_redis().delete(f"idem:{key}")
    except RedisError:
        logger.warning("could not release idempotency key %s", key)


async def rate_limit_hit(bucket: str, limit: int, window: int) -> tuple[bool, int]:
    """Fixed-window counter. Returns (allowed, retry_after_seconds).

    Fails open: a rate limiter that cannot reach Redis must not take the whole
    API down with it, and every endpoint behind it has its own authorisation.
    """
    redis = get_redis()
    key = f"rl:{bucket}"
    try:
        pipe = redis.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()
        if count == 1 or ttl < 0:
            await redis.expire(key, window)
            ttl = window
    except RedisError:
        logger.warning("rate limiter unavailable, allowing the request", exc_info=True)
        return True, 1
    return count <= limit, max(int(ttl), 1)


async def publish(channel: str, message: dict) -> None:
    try:
        await get_redis().publish(channel, json.dumps(message, default=str))
    except Exception:  # pragma: no cover - realtime fan-out is best effort
        logger.warning("redis publish failed on %s", channel, exc_info=True)
