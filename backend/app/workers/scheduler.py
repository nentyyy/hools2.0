"""In-process scheduler.

Runs inside uvicorn (docker / VPS deployments). On serverless the same work is
driven by `POST /api/internal/tick` from an external cron.
"""

from __future__ import annotations

import asyncio
import logging

from app.core.db import SessionFactory
from app.services import giveaways as giveaways_service
from app.services import pvp as pvp_service

logger = logging.getLogger(__name__)

INTERVAL_SECONDS = 2.0
GIVEAWAY_EVERY = 15  # ticks between giveaway sweeps


async def run_scheduler(stop: asyncio.Event) -> None:
    logger.info("scheduler started")
    counter = 0
    while not stop.is_set():
        counter += 1
        try:
            async with SessionFactory() as session:
                await pvp_service.tick(session)
                if counter % GIVEAWAY_EVERY == 0:
                    await giveaways_service.tick(session)
        except Exception:  # pragma: no cover - never let the loop die
            logger.exception("scheduler iteration failed")

        try:
            await asyncio.wait_for(stop.wait(), timeout=INTERVAL_SECONDS)
        except TimeoutError:
            continue
    logger.info("scheduler stopped")
