from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


class GGPackagePublic(BaseModel):
    code: str
    title: str
    gg: int
    bonus_gg: int
    total_gg: int
    stars: int
    currency: str = "XTR"


class CreateInvoiceRequest(BaseModel):
    package: str = Field(min_length=1, max_length=32)


class InvoiceResponse(BaseModel):
    payment_id: int
    invoice_link: str
    payload: str
    stars: int
    gg: int
    currency: str = "XTR"


class StarPaymentPublic(ORMModel):
    id: int
    user_id: int
    package_code: str
    gg_amount: int
    stars_amount: int
    currency: str
    status: str
    telegram_payment_charge_id: str | None = None
    invoice_link: str | None = None
    created_at: datetime
    paid_at: datetime | None = None
    refunded_at: datetime | None = None
    refund_reason: str | None = None


class SuccessfulPaymentWebhook(BaseModel):
    """Posted by the bot process once Telegram confirms a payment."""

    telegram_id: int
    payload: str = Field(min_length=1, max_length=128)
    telegram_payment_charge_id: str = Field(min_length=1, max_length=128)
    provider_payment_charge_id: str | None = None
    total_amount: int = Field(ge=1)
    currency: str = "XTR"
    raw: dict | None = None


class PreCheckoutRequest(BaseModel):
    telegram_id: int
    payload: str
    total_amount: int
    currency: str = "XTR"


class PreCheckoutResponse(BaseModel):
    ok: bool
    error_message: str | None = None


class RefundRequest(BaseModel):
    payment_id: int
    reason: str | None = Field(default=None, max_length=256)
    force: bool = False
