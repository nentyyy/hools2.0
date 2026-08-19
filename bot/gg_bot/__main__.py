"""Polling entrypoint: `python -m gg_bot`.

Used for local development and for the docker/VPS deployment. In webhook mode
(serverless) the backend feeds updates to the same dispatcher instead.
"""

from __future__ import annotations

import asyncio
import logging
import sys

from gg_bot.config import settings
from gg_bot.runtime import get_bot, get_dispatcher, setup_commands

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


async def main() -> None:
    _setup_logging()
    if not settings.bot_token:
        logger.error("BOT_TOKEN is not set — nothing to run")
        raise SystemExit(1)

    bot = get_bot()
    dispatcher = get_dispatcher()

    me = await bot.get_me()
    logger.info("starting @%s in polling mode (backend: %s)", me.username, settings.backend_url)

    # Polling and a webhook cannot be active at the same time.
    await bot.delete_webhook(drop_pending_updates=False)
    await setup_commands()

    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
        logger.info("bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("interrupted")
