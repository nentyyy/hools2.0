"""Operator switches that can be flipped without redeploying.

Some deployments cannot easily edit environment variables (a locked dashboard,
a phone, a managed integration). These flags live in Redis and are set through
the token-protected setup endpoint, so they still require the operator secret —
they are just reachable from a browser.

An environment variable always wins: if it is on, the flag cannot turn it off.
"""

from __future__ import annotations

import logging

from redis.exceptions import RedisError

from app.core.config import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

BROWSER_LOGIN_KEY = "config:browser_login"


async def browser_login_enabled() -> bool:
    if settings.allow_browser_login:
        return True
    try:
        return await get_redis().get(BROWSER_LOGIN_KEY) == "1"
    except RedisError:
        logger.warning("could not read the browser-login flag", exc_info=True)
        return False


async def set_browser_login(enabled: bool) -> bool:
    """Turn browser play on or off. Returns the resulting state."""
    redis = get_redis()
    if enabled:
        await redis.set(BROWSER_LOGIN_KEY, "1")
    else:
        await redis.delete(BROWSER_LOGIN_KEY)
    logger.warning("browser login %s", "enabled" if enabled else "disabled")
    return await browser_login_enabled()
