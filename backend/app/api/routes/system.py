"""Health checks and the scheduler tick."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import text

from app.api.deps import SessionDep, require_cron_token
from app.core.config import settings
from app.core.redis import get_redis
from app.services import giveaways as giveaways_service
from app.services import pvp as pvp_service

logger = logging.getLogger(__name__)
router = APIRouter(tags=["system"])


@router.get("/health")
async def health(session: SessionDep) -> dict:
    checks: dict[str, str] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["database"] = f"error: {exc.__class__.__name__}"
    try:
        await get_redis().ping()
        checks["redis"] = "ok"
    except Exception as exc:  # pragma: no cover
        checks["redis"] = f"error: {exc.__class__.__name__}"

    healthy = all(v == "ok" for v in checks.values())
    return {
        "status": "ok" if healthy else "degraded",
        "environment": settings.environment,
        "checks": checks,
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
