"""Bot and dispatcher wiring, shared by polling and webhook modes."""

from __future__ import annotations

import logging
from functools import lru_cache

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, Update

from gg_bot.config import settings
from gg_bot.handlers import build_router
from gg_bot.middlewares import LoggingMiddleware, ThrottleMiddleware

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Open gg.gram"),
    BotCommand(command="profile", description="Your profile and stats"),
    BotCommand(command="games", description="All game modes"),
    BotCommand(command="giveaways", description="Live giveaways"),
    BotCommand(command="balance", description="Balance and top-up"),
    BotCommand(command="paysupport", description="Payment support"),
    BotCommand(command="help", description="How it works"),
]


@lru_cache
def get_bot() -> Bot:
    if not settings.bot_token:
        raise RuntimeError("BOT_TOKEN is not set")
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )


@lru_cache
def get_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.outer_middleware(LoggingMiddleware())
    dispatcher.update.outer_middleware(ThrottleMiddleware())
    dispatcher.include_router(build_router())
    return dispatcher


async def setup_commands() -> None:
    await get_bot().set_my_commands(COMMANDS)
    logger.info("bot commands registered")


async def feed_webhook_update(payload: dict) -> None:
    """Entry point used by the backend's `/api/telegram/webhook` route."""
    bot = get_bot()
    update = Update.model_validate(payload, context={"bot": bot})
    await get_dispatcher().feed_update(bot, update)
