"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app import __version__
from app.api.routes import (
    admin,
    auth,
    giveaways,
    internal,
    payments,
    profile,
    pvp,
    solo,
    system,
    telegram,
    ton,
)
from app.core.config import settings
from app.core.db import dispose_engine
from app.core.errors import register_exception_handlers
from app.core.logging import request_id_ctx, setup_logging
from app.core.redis import close_redis, get_redis
from app.workers.scheduler import run_scheduler
from app.ws import routes as ws_routes
from app.ws.manager import manager

setup_logging(settings.log_level, json_logs=settings.is_production)
logger = logging.getLogger(__name__)

# Serverless platforms freeze the process between requests, so the in-process
# scheduler is only started for long-running deployments.
SCHEDULER_ENABLED = os.getenv("ENABLE_SCHEDULER", "1") not in {"0", "false", "False"} and not os.getenv(
    "VERCEL"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "starting gg.gram backend",
        extra={"version": __version__, "environment": settings.environment},
    )
    stop = asyncio.Event()
    scheduler_task: asyncio.Task | None = None

    try:
        await get_redis().ping()
        logger.info("redis connection ok")
    except Exception:
        logger.error("redis is unreachable at startup", exc_info=True)

    if SCHEDULER_ENABLED:
        scheduler_task = asyncio.create_task(run_scheduler(stop))

    try:
        yield
    finally:
        stop.set()
        if scheduler_task:
            scheduler_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await scheduler_task
        await manager.shutdown()
        await close_redis()
        await dispose_engine()
        logger.info("backend stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="gg.gram API",
        version=__version__,
        description="Backend for the gg.gram Telegram Mini App",
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request_id_ctx.set(request_id)
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time"] = f"{duration_ms}ms"
        if request.url.path not in {"/api/health", "/health"}:
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": duration_ms,
                },
            )
        return response

    register_exception_handlers(app)

    prefix = settings.api_prefix
    app.include_router(system.router, prefix=prefix)
    app.include_router(auth.router, prefix=prefix)
    app.include_router(profile.router, prefix=prefix)
    app.include_router(pvp.router, prefix=prefix)
    app.include_router(solo.router, prefix=prefix)
    app.include_router(giveaways.router, prefix=prefix)
    app.include_router(payments.router, prefix=prefix)
    app.include_router(ton.router, prefix=prefix)
    app.include_router(telegram.router, prefix=prefix)
    app.include_router(internal.router, prefix=prefix)
    app.include_router(admin.router, prefix=prefix)
    app.include_router(ws_routes.router)

    @app.get("/", include_in_schema=False)
    async def root() -> dict:
        return {"name": "gg.gram API", "version": __version__, "docs": "/docs"}

    return app


app = create_app()
