from aiogram import Router

from gg_bot.handlers import commands, errors, payments


def build_router() -> Router:
    """Order matters: payment updates are matched before the generic handlers."""
    router = Router(name="gg.gram")
    router.include_router(payments.router)
    router.include_router(commands.router)
    router.include_router(errors.router)
    return router


__all__ = ["build_router"]
