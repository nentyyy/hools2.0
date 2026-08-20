"""Health checks and the scheduler tick."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.api.deps import SessionDep, require_cron_token, setup_limit
from app.core.config import settings
from app.core.redis import get_redis
from app.services import giveaways as giveaways_service
from app.services import migrations as migrations_service
from app.services import pvp as pvp_service
from app.services import telegram as telegram_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: SessionDep) -> dict:
    """Readiness report.

    Deliberately detailed: this is the first URL to open when a deployment
    misbehaves, and it answers the three questions that actually matter — can
    the API reach its stores, has the schema been applied, and is anything
    required left unconfigured. It reports names and booleans only, never
    values.
    """
    checks: dict[str, str] = {}
    revision: str | None = None

    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
        try:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
            checks["migrations"] = "ok" if revision else "not applied"
        except Exception:
            await session.rollback()
            checks["migrations"] = "not applied"
    except Exception as exc:
        checks["database"] = f"error: {exc.__class__.__name__}"
        checks["migrations"] = "unknown"

    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {exc.__class__.__name__}"

    def configured(value: str, placeholder: str) -> str:
        """A value left at its .env.example default counts as unconfigured."""
        return "" if value == placeholder else value

    missing = [
        name
        for name, value in (
            ("BOT_TOKEN", settings.bot_token),
            ("BOT_USERNAME", settings.bot_username),
            ("JWT_SECRET", configured(settings.jwt_secret, "change-me")),
            ("INTERNAL_API_TOKEN", configured(settings.internal_api_token, "change-me-internal")),
            ("CRON_SECRET", configured(settings.cron_secret, "change-me-cron")),
        )
        if not value
    ]

    healthy = checks.get("database") == "ok" and checks.get("redis") == "ok"
    ready = healthy and checks.get("migrations") == "ok"

    return {
        "status": "ok" if ready else "degraded" if healthy else "error",
        "environment": settings.environment,
        "checks": checks,
        "schema_revision": revision,
        "config": {
            "missing": missing,
            "admin_ids": len(settings.admin_telegram_ids),
            "browser_login": settings.allow_browser_login,
            "webapp_url": settings.webapp_url,
        },
        "hint": (
            None
            if ready
            else "Run /api/internal/setup?token=<CRON_SECRET> to apply migrations and register the bot webhook"
            if checks.get("migrations") != "ok"
            else "Check the failing store above"
        ),
    }


@router.api_route(
    "/internal/tick", methods=["GET", "POST"], dependencies=[Depends(require_cron_token)]
)
async def tick(session: SessionDep) -> dict:
    """Advance every time-driven state machine.

    Called by the in-process scheduler when running under uvicorn, and by an
    external cron in serverless deployments. GET is accepted because Vercel Cron
    only issues GET requests (with the cron secret as a bearer token).
    """
    pvp_done = await pvp_service.tick(session)
    giveaways_done = await giveaways_service.tick(session)
    logger.info("tick", extra={"pvp": pvp_done, "giveaways": giveaways_done})
    return {"ok": True, "pvp_resolved": pvp_done, "giveaways_finished": giveaways_done}


@router.api_route(
    "/internal/migrate",
    methods=["GET", "POST"],
    dependencies=[Depends(require_cron_token), Depends(setup_limit)],
)
async def migrate(revision: str = "head") -> dict:
    """Apply database migrations without a shell.

    Safe to call repeatedly: an already-migrated database reports
    `changed: false`, and concurrent callers get `busy` instead of racing.
    """
    return await migrations_service.upgrade(revision)


@router.api_route(
    "/internal/setup",
    methods=["GET", "POST"],
    dependencies=[Depends(require_cron_token), Depends(setup_limit)],
)
async def setup(request: Request, webhook_url: str | None = None) -> dict:
    """One-shot deployment finisher: migrate, then wire the bot up.

    Open it once in a browser after the first deploy:
    `https://<domain>/api/internal/setup?token=<CRON_SECRET>`

    It applies migrations, points Telegram's webhook at this deployment and
    registers the bot's command list. Every step is idempotent, and each is
    reported separately so a partial failure is visible rather than silent.
    """
    steps: dict[str, object] = {}

    try:
        steps["migrations"] = await migrations_service.upgrade()
    except Exception as exc:
        logger.exception("setup: migrations failed")
        steps["migrations"] = {"status": "error", "message": str(exc)}

    base = str(request.base_url).rstrip("/")
    target = webhook_url or f"{base}{settings.api_prefix}/telegram/webhook"

    if not settings.bot_token:
        steps["webhook"] = {"status": "skipped", "message": "BOT_TOKEN is not configured"}
    else:
        try:
            await telegram_service.set_webhook(target, settings.telegram_webhook_secret or None)
            steps["webhook"] = {"status": "ok", "url": target}
        except Exception as exc:
            logger.exception("setup: webhook failed")
            steps["webhook"] = {"status": "error", "message": str(exc)}

        try:
            from gg_bot.runtime import COMMANDS

            await telegram_service.call(
                "setMyCommands",
                {"commands": [{"command": c.command, "description": c.description} for c in COMMANDS]},
            )
            steps["commands"] = {"status": "ok", "count": len(COMMANDS)}
        except Exception as exc:
            logger.warning("setup: could not register bot commands: %s", exc)
            steps["commands"] = {"status": "error", "message": str(exc)}

        try:
            me = await telegram_service.get_me()
            steps["bot"] = {"status": "ok", "username": me.get("username"), "id": me.get("id")}
        except Exception as exc:
            steps["bot"] = {"status": "error", "message": str(exc)}

    ok = all(
        not isinstance(value, dict) or value.get("status") in {"ok", "skipped", "busy"}
        for value in steps.values()
    )
    return {
        "ok": ok,
        "webapp_url": settings.webapp_url,
        "deployment": base,
        "steps": steps,
        "next": (
            "Open BotFather, run /newapp for this bot and set the Web App URL to "
            f"{base} — then send /start to the bot."
        ),
    }
