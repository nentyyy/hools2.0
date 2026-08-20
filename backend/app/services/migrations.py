"""Run Alembic migrations from inside the running application.

This exists so a deployment can be finished from a phone: there is no shell on
a serverless host, and `alembic upgrade head` is the one step that otherwise
requires one.

Two safeguards make it safe to expose:

* a PostgreSQL advisory lock, so several instances starting at once cannot
  migrate concurrently — the losers report `busy` and do nothing;
* the upgrade runs in a worker thread, because Alembic's env.py calls
  `asyncio.run()`, which cannot be nested inside the request's event loop.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from alembic.config import Config
from sqlalchemy import text

from alembic import command
from app.core.config import settings
from app.core.db import engine

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parents[2]
ADVISORY_LOCK_KEY = 8_241_464  # arbitrary but stable across instances


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url.replace("%", "%%"))
    return config


def _upgrade_sync(revision: str) -> None:
    command.upgrade(_alembic_config(), revision)


async def _current_revision(conn) -> str | None:
    try:
        return await conn.scalar(text("SELECT version_num FROM alembic_version LIMIT 1"))
    except Exception:
        return None  # the table does not exist yet — nothing has been applied


def head_revision() -> str | None:
    """The newest revision this build ships."""
    try:
        from alembic.script import ScriptDirectory

        return ScriptDirectory.from_config(_alembic_config()).get_current_head()
    except Exception:  # pragma: no cover - only if the versions folder is missing
        logger.warning("could not read the migration head", exc_info=True)
        return None


async def status() -> dict:
    """Compare what the database has applied against what this build expects."""
    head = head_revision()
    try:
        async with engine.connect() as conn:
            current = await _current_revision(conn)
    except Exception as exc:
        return {"state": "unknown", "current": None, "head": head, "error": exc.__class__.__name__}

    if current is None:
        return {"state": "not_applied", "current": None, "head": head}
    if head and current != head:
        return {"state": "outdated", "current": current, "head": head}
    return {"state": "ok", "current": current, "head": head}


async def upgrade(revision: str = "head") -> dict:
    """Apply migrations. Returns what changed, or `busy` if another run holds the lock."""
    async with engine.connect() as conn:
        acquired = await conn.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_LOCK_KEY}
        )
        if not acquired:
            logger.info("migration skipped: another instance holds the lock")
            return {"status": "busy", "message": "Another instance is migrating right now"}

        try:
            before = await _current_revision(conn)
            await conn.rollback()  # release the read transaction; alembic opens its own

            await asyncio.to_thread(_upgrade_sync, revision)

            after = await _current_revision(conn)
            logger.info("migrations applied", extra={"from": before, "to": after})
            return {
                "status": "ok",
                "from_revision": before,
                "to_revision": after,
                "changed": before != after,
            }
        finally:
            await conn.exec_driver_sql(f"SELECT pg_advisory_unlock({ADVISORY_LOCK_KEY})")
