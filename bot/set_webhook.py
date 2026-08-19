"""One-shot helper: point Telegram at the deployed webhook.

    python set_webhook.py                 # uses WEBAPP_URL/api/telegram/webhook
    python set_webhook.py https://api.example.com/api/telegram/webhook
    python set_webhook.py --delete        # switch back to polling
"""

from __future__ import annotations

import asyncio
import sys

from gg_bot.config import settings
from gg_bot.runtime import get_bot, setup_commands


async def main() -> None:
    bot = get_bot()
    try:
        if "--delete" in sys.argv:
            await bot.delete_webhook(drop_pending_updates=False)
            print("Webhook deleted — the bot can now run in polling mode.")
            return

        target = next((a for a in sys.argv[1:] if a.startswith("http")), None)
        url = target or f"{settings.backend_url.rstrip('/')}{settings.api_prefix}/telegram/webhook"
        await bot.set_webhook(
            url,
            secret_token=settings.telegram_webhook_secret or None,
            allowed_updates=["message", "callback_query", "pre_checkout_query"],
        )
        await setup_commands()
        info = await bot.get_webhook_info()
        print(f"Webhook set to {info.url}")
        if info.last_error_message:
            print(f"Last error reported by Telegram: {info.last_error_message}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
