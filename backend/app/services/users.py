"""User lookup, creation and Telegram-driven profile refresh."""

from __future__ import annotations

import hashlib
import logging
import secrets
import string
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import BannedError, ForbiddenError, NotFoundError, ValidationError
from app.core.security import TelegramUser
from app.models import User
from app.services import referrals
from app.services.ledger import apply_change
from gg_shared import TransactionType

logger = logging.getLogger(__name__)

_ALPHABET = string.ascii_uppercase + string.digits

# Guest accounts live in a reserved negative id range so they can never collide
# with a real Telegram id — and so a guest can never be matched to a real user.
GUEST_ID_FLOOR = -10**15


def guest_telegram_id(device_id: str) -> int:
    digest = hashlib.sha256(f"guest:{device_id}".encode()).hexdigest()[:14]
    return -(int(digest, 16) % 10**14) - 1


def generate_referral_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def _unique_referral_code(session: AsyncSession) -> str:
    for _ in range(10):
        code = generate_referral_code()
        exists = await session.scalar(select(func.count()).select_from(User).where(User.referral_code == code))
        if not exists:
            return code
    return secrets.token_hex(8).upper()  # pragma: no cover - astronomically unlikely


async def get_by_id(session: AsyncSession, user_id: int) -> User:
    user = await session.get(User, user_id)
    if user is None:
        raise NotFoundError("User not found")
    return user


async def get_by_telegram_id(session: AsyncSession, telegram_id: int) -> User | None:
    return await session.scalar(select(User).where(User.telegram_id == telegram_id))


async def get_or_create(
    session: AsyncSession,
    tg: TelegramUser,
    *,
    start_param: str | None = None,
) -> tuple[User, bool]:
    """Find the Telegram user or register them. Returns (user, created)."""
    user = await get_by_telegram_id(session, tg.telegram_id)
    created = False

    if user is None:
        user = User(
            telegram_id=tg.telegram_id,
            username=tg.username,
            first_name=tg.first_name,
            last_name=tg.last_name,
            avatar=tg.photo_url,
            language_code=tg.language_code,
            referral_code=await _unique_referral_code(session),
            balance=0,
        )
        try:
            async with session.begin_nested():
                session.add(user)
            created = True
        except IntegrityError:
            # Two Mini App tabs opened at once: the loser re-reads the winner's row.
            user = await get_by_telegram_id(session, tg.telegram_id)
            if user is None:  # pragma: no cover - only if the row vanished
                raise
            created = False

    if created:
        await referrals.attach_referrer(session, user, start_param or tg.start_param)
        if settings.signup_bonus > 0:
            await apply_change(
                session,
                user,
                amount=settings.signup_bonus,
                tx_type=TransactionType.ADMIN_ADJUSTMENT,
                reference_id=f"signup:{user.id}",
                description="Welcome bonus",
                idempotency_key=f"signup:{user.id}",
            )
        logger.info("user_registered", extra={"user_id": user.id, "telegram_id": user.telegram_id})
    else:
        _refresh_profile(user, tg)

    if settings.is_admin(user.telegram_id) and not user.is_admin:
        user.is_admin = True

    user.last_seen_at = datetime.now(UTC)
    await session.flush()
    return user, created


def _refresh_profile(user: User, tg: TelegramUser) -> None:
    """Telegram is the source of truth for name/username/photo."""
    user.username = tg.username
    user.first_name = tg.first_name
    user.last_name = tg.last_name
    if tg.photo_url:
        user.avatar = tg.photo_url
    if tg.language_code:
        user.language_code = tg.language_code


def ensure_active(user: User) -> None:
    if user.is_banned:
        raise BannedError(user.ban_reason or "Your account is banned")


async def get_or_create_guest(
    session: AsyncSession, device_id: str, *, start_param: str | None = None
) -> tuple[User, bool]:
    """Sign in a browser-only player.

    The account is derived from a device id the client keeps in local storage,
    so reopening the page returns to the same balance. A guest is never an
    administrator and never shares an id space with a Telegram user.
    """
    from app.services.runtime_flags import browser_login_enabled

    if not await browser_login_enabled():
        raise ForbiddenError("Browser play is disabled — open the app from Telegram")

    device_id = (device_id or "").strip()[:64]
    if len(device_id) < 8:
        raise ValidationError("device_id must be at least 8 characters")

    telegram_id = guest_telegram_id(device_id)
    suffix = f"{abs(telegram_id) % 10000:04d}"
    tg_user = TelegramUser(
        telegram_id=telegram_id,
        username=None,
        first_name=f"Guest {suffix}",
        last_name=None,
        language_code=None,
        photo_url=None,
        is_premium=False,
        start_param=start_param,
        auth_date=0,
        raw={"guest": True},
    )

    user, created = await get_or_create(session, tg_user, start_param=start_param)
    if user.is_admin:  # defensive: a guest must never inherit admin rights
        user.is_admin = False
    if created:
        logger.info("guest_registered", extra={"user_id": user.id})
    return user, created
