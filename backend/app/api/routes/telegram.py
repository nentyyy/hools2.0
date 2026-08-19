"""Telegram webhook entry point.

Used when the bot runs in webhook mode (serverless / single deployment). In
polling mode this router is simply never hit — the bot process owns the updates
instead. The secret token header is checked before the payload is looked at.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Header, Request

from app.api.deps import AdminUser
from app.core.config import settings
from app.core.errors import AuthError
from app.core.security import constant_time_equals
from app.schemas.common import OkResponse
from app.services import telegram as telegram_api

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/telegram", tags=["telegram"])


@router.post("/webhook")
async def webhook(
    request: Request,
    x_telegram_bot_api_secret_token: Annotated[str | None, Header()] = None,
) -> dict:
    if settings.telegram_webhook_secret and not constant_time_equals(
        x_telegram_bot_api_secret_token or "", settings.telegram_webhook_secret
    ):
        logger.warning("rejected telegram webhook with a bad secret token")
        raise AuthError("Invalid webhook secret")

    update = await request.json()

    # Imported lazily so the API can start even where the bot package is absent.
    from gg_bot.runtime import feed_webhook_update

    await feed_webhook_update(update)
    return {"ok": True}


@router.post("/set-webhook", response_model=OkResponse)
async def set_webhook(admin: AdminUser, url: str | None = None, drop_pending: bool = False) -> OkResponse:
    target = url or f"{settings.webapp_url.rstrip('/')}{settings.api_prefix}/telegram/webhook"
    await telegram_api.set_webhook(target, settings.telegram_webhook_secret, drop_pending)
    logger.info("webhook_set", extra={"admin_id": admin.id, "url": target})
    return OkResponse(message=f"Webhook set to {target}")


@router.post("/delete-webhook", response_model=OkResponse)
async def delete_webhook(admin: AdminUser, drop_pending: bool = False) -> OkResponse:
    await telegram_api.delete_webhook(drop_pending)
    logger.info("webhook_deleted", extra={"admin_id": admin.id})
    return OkResponse(message="Webhook deleted")
