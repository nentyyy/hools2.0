"""Telegram initData validation and JWT session tokens.

The frontend is never trusted: it may only hand us the raw `initData` string
that Telegram signed. Everything about the user (id, username, photo) is taken
from the *verified* payload, never from a request body.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl

import jwt

from app.core.config import settings
from app.core.errors import AuthError

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class TelegramUser:
    telegram_id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    language_code: str | None
    photo_url: str | None
    is_premium: bool
    start_param: str | None
    auth_date: int
    raw: dict[str, Any]


def _secret_key(bot_token: str) -> bytes:
    return hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()


def validate_init_data(init_data: str, *, bot_token: str | None = None, ttl: int | None = None) -> TelegramUser:
    """Verify the HMAC signature Telegram puts on WebApp initData.

    Raises AuthError when the payload is malformed, unsigned, forged or stale.
    """
    token = bot_token or settings.bot_token
    if not token:
        raise AuthError("Bot token is not configured on the server")
    if not init_data:
        raise AuthError("initData is empty")

    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True, keep_blank_values=True))
    except ValueError as exc:
        raise AuthError("initData is malformed") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise AuthError("initData has no hash")

    data_check_string = "\n".join(f"{k}={pairs[k]}" for k in sorted(pairs))
    expected = hmac.new(_secret_key(token), data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received_hash):
        raise AuthError("initData signature is invalid")

    try:
        auth_date = int(pairs.get("auth_date", "0"))
    except ValueError as exc:
        raise AuthError("initData auth_date is invalid") from exc

    max_age = settings.init_data_ttl if ttl is None else ttl
    if max_age > 0 and (time.time() - auth_date) > max_age:
        raise AuthError("initData has expired, reopen the app")

    try:
        user = json.loads(pairs.get("user", "{}"))
    except json.JSONDecodeError as exc:
        raise AuthError("initData user payload is invalid") from exc

    if not user.get("id"):
        raise AuthError("initData does not contain a user")

    return TelegramUser(
        telegram_id=int(user["id"]),
        username=user.get("username"),
        first_name=user.get("first_name"),
        last_name=user.get("last_name"),
        language_code=user.get("language_code"),
        photo_url=user.get("photo_url"),
        is_premium=bool(user.get("is_premium", False)),
        start_param=pairs.get("start_param"),
        auth_date=auth_date,
        raw=user,
    )


def create_access_token(user_id: int, telegram_id: int, *, is_admin: bool = False) -> tuple[str, int]:
    """Issue a session JWT. Returns (token, expires_in_seconds)."""
    now = int(time.time())
    payload = {
        "sub": str(user_id),
        "tg": telegram_id,
        "adm": is_admin,
        "iat": now,
        "exp": now + settings.jwt_ttl,
        "iss": "gg.gram",
    }
    token = jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)
    return token, settings.jwt_ttl


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
            issuer="gg.gram",
        )
    except jwt.ExpiredSignatureError as exc:
        raise AuthError("Session expired") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthError("Invalid session token") from exc


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")
