"""Thin async client for the Telegram Bot API.

Only the backend and the bot process ever hold the token; it is never exposed to
the Mini App.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

API_BASE = "https://api.telegram.org"


class TelegramError(AppError):
    """The Bot API rejected the call."""

    status_code = 502
    code = "telegram_error"


async def call(method: str, payload: dict[str, Any] | None = None, *, timeout: float = 15.0) -> Any:
    if not settings.bot_token:
        raise TelegramError("Bot token is not configured")

    url = f"{API_BASE}/bot{settings.bot_token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(url, json=payload or {})
            data = response.json()
    except httpx.HTTPError as exc:
        logger.error("telegram request failed: %s", exc)
        raise TelegramError(f"Telegram API is unreachable: {exc}") from exc
    except ValueError as exc:
        raise TelegramError("Telegram API returned a malformed response") from exc

    if not data.get("ok"):
        description = data.get("description", "unknown error")
        logger.error("telegram api error", extra={"method": method, "description": description})
        raise TelegramError(f"Telegram API error: {description}")
    return data.get("result")


async def create_invoice_link(
    *,
    title: str,
    description: str,
    payload: str,
    stars: int,
    photo_url: str | None = None,
) -> str:
    """Create a Stars (XTR) invoice link.

    Digital goods sold inside Telegram must be paid for with Stars, so there is
    no provider token and the price is a single XTR labeled price.
    """
    body: dict[str, Any] = {
        "title": title[:32],
        "description": description[:255],
        "payload": payload,
        "currency": "XTR",
        "prices": [{"label": title[:32], "amount": stars}],
    }
    if photo_url:
        body["photo_url"] = photo_url
    return await call("createInvoiceLink", body)


async def refund_star_payment(*, user_id: int, charge_id: str) -> bool:
    """Return Stars to the buyer through Telegram's official refund method."""
    return bool(
        await call(
            "refundStarPayment",
            {"user_id": user_id, "telegram_payment_charge_id": charge_id},
        )
    )


async def send_message(
    chat_id: int, text: str, *, reply_markup: dict | None = None, parse_mode: str = "HTML"
) -> Any:
    body: dict[str, Any] = {"chat_id": chat_id, "text": text, "parse_mode": parse_mode}
    if reply_markup:
        body["reply_markup"] = reply_markup
    return await call("sendMessage", body)


async def answer_pre_checkout_query(query_id: str, ok: bool, error_message: str | None = None) -> Any:
    body: dict[str, Any] = {"pre_checkout_query_id": query_id, "ok": ok}
    if error_message:
        body["error_message"] = error_message
    return await call("answerPreCheckoutQuery", body)


async def set_webhook(url: str, secret_token: str | None = None, drop_pending: bool = False) -> Any:
    body: dict[str, Any] = {
        "url": url,
        "allowed_updates": ["message", "callback_query", "pre_checkout_query", "inline_query"],
        "drop_pending_updates": drop_pending,
    }
    if secret_token:
        body["secret_token"] = secret_token
    return await call("setWebhook", body)


async def delete_webhook(drop_pending: bool = False) -> Any:
    return await call("deleteWebhook", {"drop_pending_updates": drop_pending})


async def get_me() -> Any:
    return await call("getMe")
