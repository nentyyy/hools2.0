"""Health and schema reporting.

A deployment whose code is ahead of its database fails on ordinary queries. The
generic "storage is unavailable" answer sends whoever is on call to look at the
database instead of at the migrations, so both the health report and the error
name that case explicitly.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.main import create_app
from app.services import migrations as migrations_service

pytestmark = pytest.mark.asyncio


async def test_health_reports_stores_and_schema(client):
    body = (await client.get("/api/health")).json()

    assert body["checks"]["database"] == "ok"
    assert body["checks"]["redis"] == "ok"
    assert body["checks"]["migrations"] == "ok"
    assert body["schema_revision"] == body["schema_head"]
    assert body["config"]["missing"] == [] or isinstance(body["config"]["missing"], list)


async def test_health_flags_a_schema_left_behind(client, session):
    head = migrations_service.head_revision()
    assert head, "the build must ship at least one migration"

    await session.execute(text("UPDATE alembic_version SET version_num = '0001_initial'"))
    await session.commit()
    try:
        body = (await client.get("/api/health")).json()
        assert body["status"] == "degraded"
        assert body["checks"]["migrations"] == f"outdated (0001_initial → {head})"
        assert "internal/setup" in body["hint"]
    finally:
        await session.execute(text("UPDATE alembic_version SET version_num = :head"), {"head": head})
        await session.commit()


async def test_a_missing_column_is_reported_as_an_outdated_schema():
    """PostgreSQL 42703 means the query named a column the database lacks."""

    class MissingColumnError(Exception):
        sqlstate = "42703"

    app = create_app()
    handler = app.exception_handlers[SQLAlchemyError]

    error = SQLAlchemyError("column pvp_games.mode does not exist")
    error.orig = MissingColumnError()
    response = handler(None, error)
    body = await response if hasattr(response, "__await__") else response

    assert body.status_code == 503
    assert b"schema_outdated" in body.body
    assert b"internal/setup" in body.body
