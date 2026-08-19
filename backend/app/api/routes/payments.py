"""Telegram Stars payment endpoints.

`/payments/stars/webhook` and `/payments/stars/precheckout` are called by the
bot process with the internal service token — never by the Mini App.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    AdminUser,
    CurrentUser,
    IdempotencyKey,
    SessionDep,
    default_limit,
    idempotency_guard,
    play_limit,
    require_internal_token,
)
from app.schemas.common import make_page
from app.schemas.payment import (
    CreateInvoiceRequest,
    GGPackagePublic,
    InvoiceResponse,
    PreCheckoutRequest,
    PreCheckoutResponse,
    RefundRequest,
    StarPaymentPublic,
    SuccessfulPaymentWebhook,
)
from app.services import payments as service
from app.services import telegram

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])


@router.get("/packages", response_model=list[GGPackagePublic], dependencies=[Depends(default_limit)])
async def packages() -> list[GGPackagePublic]:
    return [GGPackagePublic(**p) for p in service.packages()]


@router.post("/stars/create", response_model=InvoiceResponse, dependencies=[Depends(play_limit)])
async def create_invoice(
    payload: CreateInvoiceRequest,
    user: CurrentUser,
    session: SessionDep,
    idempotency_key: IdempotencyKey = None,
) -> InvoiceResponse:
    """Create a Stars invoice link for a GG package. No GG is credited here."""
    guard = await idempotency_guard("stars-create", user.id, idempotency_key, payload.model_dump())
    if guard.cached:
        return InvoiceResponse(**guard.cached)
    try:
        payment = await service.create_invoice(session, user, payload.package)
        await session.commit()
    except Exception:
        await guard.fail()
        raise

    response = InvoiceResponse(
        payment_id=payment.id,
        invoice_link=payment.invoice_link or "",
        payload=payment.payload,
        stars=int(payment.stars_amount),
        gg=int(payment.gg_amount),
    )
    await guard.finish(response)
    return response


@router.post(
    "/stars/precheckout",
    response_model=PreCheckoutResponse,
    dependencies=[Depends(require_internal_token)],
)
async def precheckout(payload: PreCheckoutRequest, session: SessionDep) -> PreCheckoutResponse:
    ok, error = await service.validate_pre_checkout(
        session,
        payload=payload.payload,
        telegram_id=payload.telegram_id,
        total_amount=payload.total_amount,
        currency=payload.currency,
    )
    return PreCheckoutResponse(ok=ok, error_message=error)


@router.post("/stars/webhook", dependencies=[Depends(require_internal_token)])
async def stars_webhook(payload: SuccessfulPaymentWebhook, session: SessionDep) -> dict:
    """Credit GG for a confirmed Stars payment. Safe to deliver more than once."""
    payment, user, credited = await service.confirm_payment(
        session,
        telegram_id=payload.telegram_id,
        payload=payload.payload,
        charge_id=payload.telegram_payment_charge_id,
        total_amount=payload.total_amount,
        currency=payload.currency,
        provider_charge_id=payload.provider_payment_charge_id,
        raw=payload.raw,
    )
    await session.commit()

    if credited:
        try:
            await telegram.send_message(
                user.telegram_id,
                f"✅ Payment confirmed.\n<b>+{int(payment.gg_amount)} GG</b> has been added to your balance.\n"
                f"Transaction id: <code>{payload.telegram_payment_charge_id}</code>",
            )
        except Exception:  # pragma: no cover - the credit itself already happened
            logger.warning("could not send payment confirmation", exc_info=True)

    return {
        "ok": True,
        "credited": credited,
        "gg": int(payment.gg_amount),
        "balance": int(user.balance),
        "payment_id": payment.id,
    }


@router.post("/stars/refund", dependencies=[Depends(default_limit)])
async def refund(payload: RefundRequest, admin: AdminUser, session: SessionDep) -> dict:
    """Refund Stars through Telegram and take the GG back. Admin only."""
    payment = await service.refund_payment(
        session, payload.payment_id, reason=payload.reason, force=payload.force
    )
    await session.commit()
    logger.info("refund_issued", extra={"admin_id": admin.id, "payment_id": payment.id})
    return StarPaymentPublic.model_validate(payment).model_dump(mode="json")


@router.get("/history", dependencies=[Depends(default_limit)])
async def history(
    user: CurrentUser,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    rows, total = await service.list_payments(session, user_id=user.id, limit=limit, offset=offset)
    return make_page(
        [StarPaymentPublic.model_validate(p).model_dump(mode="json") for p in rows],
        total,
        limit,
        offset,
    )


@router.get("/support", dependencies=[Depends(default_limit)])
async def support() -> dict:
    return {"text": service.support_text()}
