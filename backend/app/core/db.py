"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

import logging
import ssl
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings

logger = logging.getLogger(__name__)


def _connect_args() -> dict:
    options = settings.database_options
    args: dict = {"server_settings": {"application_name": "gg.gram"}}

    # A transaction-mode pooler (Neon, Supabase, pgbouncer) hands each query to
    # a different backend, so prepared statements must be switched off.
    if options.statement_cache_size == 0:
        args["statement_cache_size"] = 0
        args["prepared_statement_cache_size"] = 0

    # `?sslmode=require` is libpq syntax; asyncpg wants an SSL context instead.
    if options.ssl_required:
        context = ssl.create_default_context()
        args["ssl"] = context

    return args


engine: AsyncEngine = create_async_engine(
    settings.sqlalchemy_url,
    echo=False,
    pool_pre_ping=True,
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_recycle=1800,
    connect_args=_connect_args(),
)

SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    expire_on_commit=False,
    autoflush=False,
)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency: one session (and one transaction) per request."""
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    """Transactional scope for background jobs and the bot's internal calls."""
    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    await engine.dispose()
