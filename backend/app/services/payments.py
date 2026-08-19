"""Telegram Stars payments.

Digital goods inside a Telegram Mini App must be sold for Stars (currency
`XTR`), so the whole top-up flow runs through the official Payments API:

    createInvoiceLink -> openInvoice in the Mini App -> pre_checkout_query
    -> successful_payment -> credit GG -> refundStarPayment when needed

GG is credited only after `successful_payment` arrives, inside one database
transaction keyed on `telegram_payment_charge_id`, so a replayed update — or two
workers handling the same update — cannot credit twice.
"""

from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.models import StarPayment, User
from app.services import referrals, telegram
from app.services.ledger import apply_change, lock_user
from gg_shared import GG_PACKAGES, TransactionType, find_package

logger = logging.getLogger(__name__)


def packages() -> list[dict]:
    return [
        {
            "code": p.code,
            "title": p.title,
            "gg": p.gg,
            "bonus_gg": p.bonus_gg,
            "total_gg": p.total_gg,
            "stars": p.stars,
            "currency": "XTR",
        }
        for p in GG_PACKAGES
    ]


def _new_payload(user_id: int) -> str:
    return f"gg:{user_id}:{secrets.token_urlsafe(12)}"


async def create_invoice(session: AsyncSession, user: User, package_code: str) -> StarPayment:
    package = find_package(package_code)
    if package is None:
        raise ValidationError(f"Unknown package: {package_code}")

    payment = StarPayment(
        user_id=user.id,
        package_code=package.code,
        gg_amount=package.total_gg,
        stars_amount=package.stars,
        currency="XTR",
        payload=_new_payload(user.id),
        status="pending",
    )
    session.add(payment)
    await session.flush()

    link = await telegram.create_invoice_link(
        title=package.title,
        description=f"{package.total_gg} GG for gg.gram",
        payload=payment.payload,
        stars=package.stars,
    )
    payment.invoice_link = link
    await session.flush()

    logger.info(
        "invoice_created",
        extra={"user_id": user.id, "payment_id": payment.id, "stars": package.stars},
    )
    return payment


async def validate_pre_checkout(
    session: AsyncSession, *, payload: str, telegram_id: int, total_amount: int, currency: str
) -> tuple[bool, str | None]:
    """Answer `pre_checkout_query`: last chance to reject before Telegram charges."""
    payment = await session.scalar(select(StarPayment).where(StarPayment.payload == payload))
    if payment is None:
        return False, "This invoice is no longer valid. Please start over."
    if payment.status != "pending":
        return False, "This invoice has already been paid."
    if currency != "XTR":
        return False, "Unsupported currency."
    if int(total_amount) != int(payment.stars_amount):
        logger.warning(
            "pre_checkout amount mismatch",
            extra={"payment_id": payment.id, "expected": payment.stars_amount, "got": total_amount},
        )
        return False, "Invoice amount mismatch."

    user = await session.get(User, payment.user_id)
    if user is None or user.telegram_id != telegram_id:
        return False, "This invoice belongs to another account."
    if user.is_banned:
        return False, "Your account is restricted."
    return True, None


async def confirm_payment(
    session: AsyncSession,
    *,
    telegram_id: int,
    payload: str,
    charge_id: str,
    total_amount: int,
    currency: str = "XTR",
    provider_charge_id: str | None = None,
    raw: dict | None = None,
) -> tuple[StarPayment, User, bool]:
    """Credit GG for a completed Stars purchase.

    Returns (payment, user, credited). `credited` is False when the update was a
    duplicate that had already been processed.
    """
    payment = await session.scalar(
        select(StarPayment)
        .where(StarPayment.payload == payload)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payment is None:
        logger.error("successful_payment for unknown payload", extra={"payload": payload})
        raise NotFoundError("Unknown invoice payload")

    user = await lock_user(session, payment.user_id)
    if user.telegram_id != telegram_id:
        logger.error(
            "successful_payment user mismatch",
            extra={"payment_id": payment.id, "expected": user.telegram_id, "got": telegram_id},
        )
        raise ConflictError("Payment does not belong to this account")

    if payment.status == "paid":
        # Telegram retries updates; this is the normal duplicate path.
        logger.info("duplicate successful_payment ignored", extra={"payment_id": payment.id})
        return payment, user, False
    if payment.status == "refunded":
        raise ConflictError("This payment was refunded")

    if currency != "XTR" or int(total_amount) != int(payment.stars_amount):
        payment.status = "failed"
        payment.raw_payload = raw
        await session.flush()
        raise ValidationError("Payment amount does not match the invoice")

    transaction = await apply_change(
        session,
        user,
        amount=int(payment.gg_amount),
        tx_type=TransactionType.STARS_TOPUP,
        reference_id=f"stars:{charge_id}",
        description=f"Top-up {payment.gg_amount} GG for {payment.stars_amount} XTR",
        idempotency_key=f"stars:{charge_id}",
        extra={"stars": int(payment.stars_amount), "package": payment.package_code},
    )

    payment.status = "paid"
    payment.telegram_payment_charge_id = charge_id
    payment.provider_payment_charge_id = provider_charge_id
    payment.transaction_id = transaction.id
    payment.paid_at = datetime.now(UTC)
    payment.raw_payload = raw
    user.stars_spent = int(user.stars_spent) + int(payment.stars_amount)

    await referrals.pay_topup_share(
        session, referred=user, gg_amount=int(payment.gg_amount), reference_id=f"stars:{charge_id}"
    )
    await session.flush()

    logger.info(
        "payment_confirmed",
        extra={
            "payment_id": payment.id,
            "user_id": user.id,
            "gg": int(payment.gg_amount),
            "stars": int(payment.stars_amount),
            "charge_id": charge_id,
        },
    )
    return payment, user, True


async def refund_payment(
    session: AsyncSession, payment_id: int, *, reason: str | None = None, force: bool = False
) -> StarPayment:
    """Refund Stars through Telegram and claw the GG back."""
    payment = await session.scalar(
        select(StarPayment)
        .where(StarPayment.id == payment_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if payment is None:
        raise NotFoundError("Payment not found")
    if payment.status == "refunded":
        return payment
    if payment.status != "paid" or not payment.telegram_payment_charge_id:
        raise ConflictError("Only a completed payment can be refunded")

    user = await lock_user(session, payment.user_id)
    owed = int(payment.gg_amount)
    if int(user.balance) < owed and not force:
        raise ConflictError(
            "User has already spent the topped-up GG; refund with force=true to claw back what is left"
        )

    # Ask Telegram first: if the Stars refund fails there is nothing to claw back.
    await telegram.refund_star_payment(user_id=user.telegram_id, charge_id=payment.telegram_payment_charge_id)

    clawed = min(int(user.balance), owed)
    if clawed > 0:
        await apply_change(
            session,
            user,
            amount=-clawed,
            tx_type=TransactionType.STARS_REFUND,
            reference_id=f"stars-refund:{payment.telegram_payment_charge_id}",
            description=f"Stars refund — {payment.stars_amount} XTR returned",
            idempotency_key=f"stars-refund:{payment.telegram_payment_charge_id}",
            extra={"requested": owed, "clawed_back": clawed, "reason": reason},
        )
    user.stars_spent = max(int(user.stars_spent) - int(payment.stars_amount), 0)

    payment.status = "refunded"
    payment.refunded_at = datetime.now(UTC)
    payment.refund_reason = reason
    await session.flush()

    logger.info(
        "payment_refunded",
        extra={"payment_id": payment.id, "user_id": user.id, "clawed_back": clawed, "shortfall": owed - clawed},
    )
    return payment


async def list_payments(
    session: AsyncSession,
    *,
    user_id: int | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[StarPayment], int]:
    stmt = select(StarPayment)
    count_stmt = select(func.count()).select_from(StarPayment)
    if user_id is not None:
        stmt = stmt.where(StarPayment.user_id == user_id)
        count_stmt = count_stmt.where(StarPayment.user_id == user_id)
    if status:
        stmt = stmt.where(StarPayment.status == status)
        count_stmt = count_stmt.where(StarPayment.status == status)

    total = int(await session.scalar(count_stmt) or 0)
    rows = list(
        (
            await session.execute(stmt.order_by(StarPayment.created_at.desc()).limit(limit).offset(offset))
        ).scalars().all()
    )
    return rows, total


def support_text() -> str:
    return (
        "<b>gg.gram — payment support</b>\n\n"
        f"GG is an in-app currency for games inside the Mini App. Top-ups are made with "
        f"Telegram Stars (XTR) and are credited automatically after payment.\n\n"
        "If GG did not arrive, send us the transaction id from Telegram "
        "(Settings → My Stars) and we will check it.\n\n"
        "Refunds: Stars purchases can be refunded within Telegram's refund window as long as "
        "the GG has not been spent. Reply here with your transaction id to request one.\n\n"
        f"Support: @{settings.bot_username}"
    )
