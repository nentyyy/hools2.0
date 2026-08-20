"""Shared FastAPI dependencies: authentication, rate limiting, idempotency."""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
from typing import Annotated, Any

from fastapi import Depends, Header, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.core.errors import AuthError, ForbiddenError, RateLimitError
from app.core.logging import user_id_ctx
from app.core.redis import (
    idempotency_begin,
    idempotency_release,
    idempotency_store,
    rate_limit_hit,
)
from app.core.security import constant_time_equals, decode_access_token
from app.models import User
from app.services import users as users_service

logger = logging.getLogger(__name__)

bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    session: SessionDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> User:
    if credentials is None or not credentials.credentials:
        raise AuthError("Authorization header is missing")

    payload = decode_access_token(credentials.credentials)
    try:
        user_id = int(payload.get("sub", 0))
    except (TypeError, ValueError) as exc:
        raise AuthError("Malformed session token") from exc

    user = await users_service.get_by_id(session, user_id)
    users_service.ensure_active(user)
    user_id_ctx.set(user.id)
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


async def get_current_admin(user: CurrentUser) -> User:
    # Two independent sources of truth: the flag on the row and the allowlist in
    # the environment. Losing either one does not silently grant access.
    if not (user.is_admin or settings.is_admin(user.telegram_id)):
        logger.warning("admin access denied", extra={"user_id": user.id})
        raise ForbiddenError("Administrator access required")
    return user


AdminUser = Annotated[User, Depends(get_current_admin)]


async def require_internal_token(
    x_internal_token: Annotated[str | None, Header(alias="X-Internal-Token")] = None,
) -> bool:
    """Guards endpoints that only the bot process may call."""
    if not settings.internal_api_token or not constant_time_equals(
        x_internal_token or "", settings.internal_api_token
    ):
        raise AuthError("Invalid internal token")
    return True


async def require_cron_token(
    x_cron_token: Annotated[str | None, Header(alias="X-Cron-Token")] = None,
    authorization: Annotated[str | None, Header()] = None,
    token: Annotated[str | None, Query(description="Alternative to the X-Cron-Token header")] = None,
) -> bool:
    """Guards the scheduler and setup endpoints.

    Accepts the header, a bearer token (that is what Vercel Cron sends) or a
    `?token=` query parameter, because a phone browser cannot set headers and
    these endpoints have to be reachable from one during setup.
    """
    candidate = x_cron_token or ""
    if not candidate and authorization and authorization.lower().startswith("bearer "):
        candidate = authorization[7:]
    if not candidate and token:
        candidate = token
    if not settings.cron_secret or not constant_time_equals(candidate, settings.cron_secret):
        raise AuthError("Invalid cron token")
    return True


class RateLimiter:
    """Per-user (or per-IP for anonymous routes) fixed window limiter."""

    def __init__(self, spec: str, *, scope: str = "default") -> None:
        limit, _, window = spec.partition("/")
        self.limit = int(limit)
        self.window = int(window or 60)
        self.scope = scope

    async def __call__(
        self,
        request: Request,
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)] = None,
    ) -> None:
        identity = request.client.host if request.client else "anonymous"
        presence_id: str | None = None
        if credentials and credentials.credentials:
            # An invalid token simply falls back to per-IP limiting.
            with contextlib.suppress(AuthError):
                identity = f"u{decode_access_token(credentials.credentials).get('sub')}"
                presence_id = identity

        allowed, retry_after = await rate_limit_hit(
            f"{self.scope}:{identity}", self.limit, self.window, presence_id=presence_id
        )
        if not allowed:
            logger.info("rate_limited", extra={"scope": self.scope, "identity": identity})
            raise RateLimitError(
                "Too many requests, slow down", details={"retry_after": retry_after}
            )


default_limit = RateLimiter(settings.rate_limit_default, scope="api")
# Deliberately tight: this one is reachable with a token in the URL.
setup_limit = RateLimiter("10/60", scope="setup")
play_limit = RateLimiter(settings.rate_limit_play, scope="play")
auth_limit = RateLimiter(settings.rate_limit_auth, scope="auth")


class IdempotencyGuard:
    """Makes a mutating request safe to retry.

    The client sends `X-Idempotency-Key` and gets the *same* response back for
    the same key instead of paying twice. Where a repeat cannot possibly be
    intentional — joining a lobby, entering a giveaway, selling an item, buying
    Stars — a key derived from the request body also guards a double tap for a
    few seconds. Repeatable actions (playing a solo round with the same bet) opt
    out of that fallback, so spamming the button really does play again.
    """

    def __init__(self, key: str | None, cached: dict | None, *, ttl: int) -> None:
        self.key = key
        self.cached = cached
        self.ttl = ttl

    async def finish(self, response: Any) -> Any:
        if self.key is None:
            return response
        payload = response.model_dump(mode="json") if hasattr(response, "model_dump") else response
        await idempotency_store(self.key, payload, self.ttl)
        return response

    async def fail(self) -> None:
        if self.key is not None:
            await idempotency_release(self.key)


async def idempotency_guard(
    scope: str,
    user_id: int,
    client_key: str | None,
    body: Any = None,
    *,
    auto: bool = True,
) -> IdempotencyGuard:
    if client_key:
        key = f"{scope}:{user_id}:{client_key[:96]}"
        ttl = 86400
    elif auto:
        digest = hashlib.sha256(
            json.dumps(body, sort_keys=True, default=str).encode() if body is not None else b""
        ).hexdigest()[:32]
        key = f"{scope}:{user_id}:auto:{digest}"
        ttl = 5  # only collapses rapid duplicate submits
    else:
        return IdempotencyGuard(None, None, ttl=0)

    cached = await idempotency_begin(key, ttl)
    return IdempotencyGuard(key, cached, ttl=ttl)


IdempotencyKey = Annotated[str | None, Header(alias="X-Idempotency-Key")]
