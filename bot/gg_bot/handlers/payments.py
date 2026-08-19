"""Telegram Stars payment handlers.

The full flow lives here:

    /balance or the top-up button -> backend creates the invoice (XTR)
    -> Telegram shows the Stars payment sheet
    -> pre_checkout_query  -> backend re-validates the invoice
    -> successful_payment  -> backend credits GG and writes the ledger row
    -> /paysupport, /refund -> Telegram's official refund mechanism

Nothing is credited before `successful_payment`, and the backend is the only
component that touches balances.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, Message, PreCheckoutQuery

from gg_bot import api, keyboards, texts
from gg_bot.config import settings

logger = logging.getLogger(__name__)
router = Router(name="payments")


@router.callback_query(F.data == "topup")
async def show_packages(callback: CallbackQuery) -> None:
    try:
        config = await api.get_config()
    except api.BackendError:
        await callback.answer(texts.BACKEND_DOWN, show_alert=True)
        return
    await callback.message.edit_text(
        "⭐ <b>Top up GG</b>\n\nPick a package. Payment goes through Telegram Stars.",
        reply_markup=keyboards.packages_menu(config["packages"]),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("buy:"))
async def buy_package(callback: CallbackQuery) -> None:
    package = callback.data.split(":", 1)[1]
    user = callback.from_user

    try:
        await api.ensure_user(
            user.id,
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            language_code=user.language_code,
        )
        invoice = await api.create_invoice(user.id, package)
    except api.BackendError as exc:
        logger.warning("invoice creation failed for %s: %s", user.id, exc.message)
        await callback.answer(exc.message or texts.BACKEND_DOWN, show_alert=True)
        return

    await callback.message.edit_text(
        f"⭐ <b>{invoice['gg']} GG</b> for <b>{invoice['stars']} Stars</b>\n\n"
        "Tap below to pay. GG is credited automatically once Telegram confirms the payment.",
        reply_markup=keyboards.pay_button(invoice["invoice_link"], invoice["stars"]),
    )
    await callback.answer()
    logger.info("invoice sent", extra={"user_id": user.id, "package": package})


@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery) -> None:
    """Last checkpoint before Telegram charges the user."""
    try:
        verdict = await api.precheckout(
            telegram_id=query.from_user.id,
            payload=query.invoice_payload,
            total_amount=query.total_amount,
            currency=query.currency,
        )
    except api.BackendError:
        await query.answer(ok=False, error_message="We could not verify this invoice. Please try again.")
        return

    if verdict.get("ok"):
        await query.answer(ok=True)
        logger.info("pre_checkout approved", extra={"user_id": query.from_user.id})
    else:
        await query.answer(ok=False, error_message=verdict.get("error_message") or "Invoice is not valid.")
        logger.warning(
            "pre_checkout rejected",
            extra={"user_id": query.from_user.id, "reason": verdict.get("error_message")},
        )


@router.message(F.successful_payment)
async def successful_payment(message: Message) -> None:
    """Credit GG. The backend is idempotent, so a redelivered update is harmless."""
    payment = message.successful_payment
    try:
        result = await api.confirm_payment(
            telegram_id=message.from_user.id,
            payload=payment.invoice_payload,
            charge_id=payment.telegram_payment_charge_id,
            total_amount=payment.total_amount,
            currency=payment.currency,
            provider_charge_id=payment.provider_payment_charge_id,
            raw=payment.model_dump(mode="json"),
        )
    except api.BackendError as exc:
        logger.error(
            "payment confirmation failed",
            extra={
                "user_id": message.from_user.id,
                "charge_id": payment.telegram_payment_charge_id,
                "error": exc.message,
            },
        )
        await message.answer(
            "⚠️ Your payment went through, but we could not credit GG automatically.\n"
            f"Transaction id: <code>{payment.telegram_payment_charge_id}</code>\n\n"
            "Send this id to /paysupport and we will fix it right away."
        )
        return

    await message.answer(
        texts.payment_confirmed(result["gg"], result["balance"], payment.telegram_payment_charge_id),
        reply_markup=keyboards.open_app("🎮 Play now"),
    )
    logger.info(
        "payment credited",
        extra={"user_id": message.from_user.id, "gg": result["gg"], "credited": result["credited"]},
    )


@router.message(Command("paysupport"))
async def paysupport(message: Message) -> None:
    """Required by Telegram for bots that accept payments."""
    text = texts.PAY_SUPPORT
    try:
        history = await api.payment_history(message.from_user.id)
        paid = [p for p in history["items"] if p["status"] == "paid"]
        if paid:
            lines = "\n".join(
                f"• #{p['id']} — {p['gg']} GG for ⭐{p['stars']} · <code>{p['charge_id']}</code>"
                for p in paid[:5]
            )
            text += f"\n\n<b>Your recent payments</b>\n{lines}"
    except api.BackendError:
        pass  # support text must be available even when the backend is down
    await message.answer(text)


@router.message(Command("refund"))
async def refund(message: Message, command: CommandObject) -> None:
    """Admin-only: `/refund <payment_id> [reason]` via Telegram's refund API."""
    if not settings.is_admin(message.from_user.id):
        await message.answer("This command is for administrators.")
        return

    args = (command.args or "").split(maxsplit=1)
    if not args or not args[0].isdigit():
        await message.answer("Usage: <code>/refund &lt;payment_id&gt; [reason]</code>")
        return

    payment_id = int(args[0])
    reason = args[1] if len(args) > 1 else "Refunded by support"
    try:
        result = await api.refund(message.from_user.id, payment_id, reason=reason)
    except api.BackendError as exc:
        await message.answer(f"❌ Refund failed: {exc.message}")
        return

    await message.answer(f"✅ Payment #{result['payment_id']} is now <b>{result['status']}</b>.")
    logger.warning("refund issued", extra={"admin_id": message.from_user.id, "payment_id": payment_id})
