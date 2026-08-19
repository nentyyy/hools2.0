"""Fallbacks: unknown commands and unhandled exceptions."""

from __future__ import annotations

import contextlib
import logging

from aiogram import F, Router
from aiogram.types import ErrorEvent, Message

from gg_bot import keyboards, texts

logger = logging.getLogger(__name__)
router = Router(name="errors")


@router.message(F.text.startswith("/"))
async def unknown_command(message: Message) -> None:
    await message.answer(
        "I don't know that command.\n\n" + texts.HELP, reply_markup=keyboards.open_app()
    )


@router.message(F.text)
async def any_message(message: Message) -> None:
    await message.answer(
        "Everything happens inside the Mini App — tap below to play.",
        reply_markup=keyboards.main_menu(),
    )


@router.error()
async def on_error(event: ErrorEvent) -> bool:
    logger.exception("unhandled bot error: %s", event.exception)
    update = event.update
    message = getattr(update, "message", None) or getattr(
        getattr(update, "callback_query", None), "message", None
    )
    if message is not None:
        # The chat may be unreachable (blocked bot, deleted message).
        with contextlib.suppress(Exception):
            await message.answer("Something went wrong on our side. Please try again in a moment.")
    return True
