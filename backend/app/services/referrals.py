"""Referral links, bonuses and statistics.

A bonus is guarded by a unique (referrer, referred, kind) row, so a retry or a
second deep-link visit can never pay twice.
"""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import ReferralBonus, User
from app.services.ledger import apply_change, lock_user
from gg_shared import TransactionType

logger = logging.getLogger(__name__)

REF_PREFIX = "ref_"


def parse_start_param(start_param: str | None) -> str | None:
    """`ref_AB12CD34` -> `AB12CD34`."""
    if not start_param:
        return None
    value = start_param.strip()
    if value.startswith(REF_PREFIX):
        value = value[len(REF_PREFIX) :]
    value = value.upper()
    return value if value.isalnum() and 4 <= len(value) <= 16 else None


def build_link(referral_code: str) -> str:
    return f"https://t.me/{settings.bot_username}?start={REF_PREFIX}{referral_code}"


async def attach_referrer(session: AsyncSession, user: User, start_param: str | None) -> User | None:
    """Bind a freshly created user to their referrer and pay the signup bonus."""
    code = parse_start_param(start_param)
    if not code or user.referral_id is not None:
        return None

    referrer = await session.scalar(select(User).where(User.referral_code == code))
    if referrer is None or referrer.id == user.id or referrer.is_banned:
        return None

    user.referral_id = referrer.id
    await session.flush()

    if settings.referral_signup_bonus > 0:
        await pay_bonus(
            session,
            referrer_id=referrer.id,
            referred_id=user.id,
            kind="signup",
            amount=settings.referral_signup_bonus,
            description=f"Referral bonus for {user.display_name}",
        )
    logger.info("referral_attached", extra={"user_id": user.id, "referrer_id": referrer.id})
    return referrer


async def pay_bonus(
    session: AsyncSession,
    *,
    referrer_id: int,
    referred_id: int,
    kind: str,
    amount: int,
    description: str,
    reference_id: str | None = None,
) -> bool:
    """Credit a referral bonus exactly once. Returns False if already paid."""
    if amount <= 0:
        return False

    guard = ReferralBonus(
        referrer_id=referrer_id,
        referred_id=referred_id,
        kind=kind,
        amount=amount,
        reference_id=reference_id,
    )
    try:
        async with session.begin_nested():
            session.add(guard)
    except IntegrityError:
        logger.info("referral bonus already paid: %s -> %s (%s)", referrer_id, referred_id, kind)
        return False

    referrer = await lock_user(session, referrer_id)
    await apply_change(
        session,
        referrer,
        amount=amount,
        tx_type=TransactionType.REFERRAL_BONUS,
        reference_id=reference_id or f"ref:{kind}:{referred_id}",
        description=description,
        idempotency_key=f"ref:{kind}:{referrer_id}:{referred_id}",
    )
    referrer.referral_earnings += amount
    return True


async def pay_topup_share(
    session: AsyncSession, *, referred: User, gg_amount: int, reference_id: str
) -> None:
    """Give the referrer a cut of a Stars top-up made by their referral."""
    if not referred.referral_id or settings.referral_topup_percent <= 0:
        return
    share = int(gg_amount * settings.referral_topup_percent / 100)
    if share <= 0:
        return
    await pay_bonus(
        session,
        referrer_id=referred.referral_id,
        referred_id=referred.id,
        kind=f"topup:{reference_id}",
        amount=share,
        description=f"{settings.referral_topup_percent:g}% of a referral top-up",
        reference_id=reference_id,
    )


async def stats(session: AsyncSession, user: User, limit: int = 50) -> dict:
    total = await session.scalar(
        select(func.count()).select_from(User).where(User.referral_id == user.id)
    )
    rows = (
        await session.execute(
            select(User).where(User.referral_id == user.id).order_by(User.created_at.desc()).limit(limit)
        )
    ).scalars().all()

    return {
        "code": user.referral_code,
        "link": build_link(user.referral_code),
        "invited_count": int(total or 0),
        "earnings": int(user.referral_earnings),
        "signup_bonus": settings.referral_signup_bonus,
        "topup_percent": settings.referral_topup_percent,
        "referrals": [
            {
                "id": r.id,
                "name": r.display_name,
                "username": r.username,
                "avatar": r.avatar,
                "level": r.level,
                "joined_at": r.created_at,
            }
            for r in rows
        ],
    }
