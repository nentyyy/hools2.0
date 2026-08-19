"""Endpoints the bot process calls with the internal service token.

The bot never touches the database directly: all balance, referral and giveaway
logic lives in one place, behind this token-protected surface.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import SessionDep, require_internal_token
from app.core.config import settings
from app.core.errors import ForbiddenError, NotFoundError
from app.core.security import TelegramUser
from app.services import giveaways as giveaways_service
from app.services import payments as payments_service
from app.services import referrals as referrals_service
from app.services import users as users_service
from app.services.leveling import level_progress
from gg_shared import GiveawayStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal", tags=["internal"], dependencies=[Depends(require_internal_token)])


class EnsureUserRequest(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    language_code: str | None = None
    start_param: str | None = Field(default=None, max_length=64)


def _summary(user, level: dict) -> dict:
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "name": user.display_name,
        "username": user.username,
        "balance": int(user.balance),
        "level": level,
        "is_banned": user.is_banned,
        "is_admin": user.is_admin,
        "referral_code": user.referral_code,
        "referral_link": referrals_service.build_link(user.referral_code),
        "stats": {
            "pvp_wins": user.pvp_wins,
            "pvp_games": user.pvp_games,
            "solo_wins": user.solo_wins,
            "solo_games": user.solo_games,
            "total_wagered": int(user.total_wagered),
            "total_earned": int(user.total_earned),
            "stars_spent": int(user.stars_spent),
            "referral_earnings": int(user.referral_earnings),
        },
    }


@router.post("/users/ensure")
async def ensure_user(payload: EnsureUserRequest, session: SessionDep) -> dict:
    """Register (or refresh) a user from a bot interaction such as /start.

    Binding the referral here means a deep link counts even if the user talks to
    the bot before ever opening the Mini App.
    """
    tg_user = TelegramUser(
        telegram_id=payload.telegram_id,
        username=payload.username,
        first_name=payload.first_name,
        last_name=payload.last_name,
        language_code=payload.language_code,
        photo_url=None,
        is_premium=False,
        start_param=payload.start_param,
        auth_date=0,
        raw={},
    )
    user, created = await users_service.get_or_create(session, tg_user, start_param=payload.start_param)
    await session.commit()
    await session.refresh(user)
    return {"created": created, **_summary(user, level_progress(int(user.xp)))}


@router.get("/users/{telegram_id}")
async def get_user(telegram_id: int, session: SessionDep) -> dict:
    user = await users_service.get_by_telegram_id(session, telegram_id)
    if user is None:
        raise NotFoundError("User not found")
    return _summary(user, level_progress(int(user.xp)))


@router.get("/giveaways")
async def active_giveaways(session: SessionDep, limit: Annotated[int, Query(ge=1, le=20)] = 5) -> dict:
    rows, total = await giveaways_service.list_giveaways(
        session, status=GiveawayStatus.ACTIVE.value, limit=limit
    )
    return {
        "total": total,
        "items": [
            {
                "id": g.id,
                "title": g.title,
                "prize_type": g.prize_type,
                "prize_value": int(g.prize_value),
                "participants_count": int(g.participants_count),
                "end_at": g.end_at,
                "entry_cost": int(g.entry_cost),
            }
            for g in rows
        ],
    }


@router.get("/config")
async def config() -> dict:
    """Lets the bot render deep links and prices without duplicating settings."""
    from app.services.payments import packages

    return {
        "webapp_url": settings.webapp_url,
        "bot_username": settings.bot_username,
        "packages": packages(),
        "pvp": {"min_bet": settings.pvp_min_bet, "max_bet": settings.pvp_max_bet},
    }


class InvoiceRequest(BaseModel):
    telegram_id: int
    package: str = Field(min_length=1, max_length=32)


class RefundRequest(BaseModel):
    admin_telegram_id: int
    payment_id: int
    reason: str | None = Field(default=None, max_length=256)
    force: bool = False


@router.post("/payments/invoice")
async def create_invoice(payload: InvoiceRequest, session: SessionDep) -> dict:
    """Create a Stars invoice for a user talking to the bot in a normal chat."""
    user = await users_service.get_by_telegram_id(session, payload.telegram_id)
    if user is None:
        raise NotFoundError("User not found")
    users_service.ensure_active(user)

    payment = await payments_service.create_invoice(session, user, payload.package)
    await session.commit()
    return {
        "payment_id": payment.id,
        "invoice_link": payment.invoice_link,
        "payload": payment.payload,
        "stars": int(payment.stars_amount),
        "gg": int(payment.gg_amount),
    }


@router.get("/payments/{telegram_id}")
async def payment_history(telegram_id: int, session: SessionDep) -> dict:
    user = await users_service.get_by_telegram_id(session, telegram_id)
    if user is None:
        raise NotFoundError("User not found")
    rows, total = await payments_service.list_payments(session, user_id=user.id, limit=20)
    return {
        "total": total,
        "items": [
            {
                "id": p.id,
                "package": p.package_code,
                "gg": int(p.gg_amount),
                "stars": int(p.stars_amount),
                "status": p.status,
                "charge_id": p.telegram_payment_charge_id,
                "created_at": p.created_at,
                "paid_at": p.paid_at,
            }
            for p in rows
        ],
    }


@router.post("/payments/refund")
async def refund(payload: RefundRequest, session: SessionDep) -> dict:
    """Refund from the bot. The caller must be an administrator."""
    admin = await users_service.get_by_telegram_id(session, payload.admin_telegram_id)
    is_admin = settings.is_admin(payload.admin_telegram_id) or bool(admin and admin.is_admin)
    if not is_admin:
        logger.warning("internal refund denied for %s", payload.admin_telegram_id)
        raise ForbiddenError("Administrator access required")

    payment = await payments_service.refund_payment(
        session, payload.payment_id, reason=payload.reason, force=payload.force
    )
    await session.commit()
    return {"ok": True, "payment_id": payment.id, "status": payment.status}
