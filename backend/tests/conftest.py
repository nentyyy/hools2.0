"""Integration test fixtures.

These tests run against a real PostgreSQL and Redis — the code they cover is all
about transactions, locks and constraints, which an in-memory stub would not
exercise. Point TEST_DATABASE_URL / TEST_REDIS_URL at a scratch database.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlencode

os.environ.setdefault("BOT_TOKEN", "123456:TEST-BOT-TOKEN")
os.environ.setdefault("JWT_SECRET", "test-secret-0123456789abcdef0123456789")
os.environ.setdefault("INTERNAL_API_TOKEN", "test-internal")
os.environ.setdefault("CRON_SECRET", "test-cron")
os.environ.setdefault("ADMIN_TELEGRAM_IDS", "1001")
os.environ.setdefault("PVP_COUNTDOWN_SECONDS", "1")
os.environ.setdefault("PVP_SPIN_SECONDS", "1")
os.environ.setdefault("SIGNUP_BONUS", "1000")
os.environ.setdefault(
    "DATABASE_URL", os.getenv("TEST_DATABASE_URL", "postgresql+asyncpg://gg:gg@127.0.0.1:5432/gg")
)
os.environ.setdefault("REDIS_URL", os.getenv("TEST_REDIS_URL", "redis://127.0.0.1:6379/1"))
os.environ.setdefault("ENABLE_SCHEDULER", "0")

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.db import SessionFactory, engine
from app.core.redis import close_redis, get_redis
from app.main import create_app
from app.models import Base


def make_init_data(telegram_id: int, *, username: str = "player", start_param: str | None = None) -> str:
    """Produce initData signed exactly the way Telegram signs it."""
    user = {
        "id": telegram_id,
        "first_name": username.title(),
        "last_name": "Test",
        "username": username,
        "language_code": "en",
    }
    fields = {"auth_date": str(int(time.time())), "query_id": "AAA", "user": json.dumps(user)}
    if start_param:
        fields["start_param"] = start_param

    check = "\n".join(f"{k}={fields[k]}" for k in sorted(fields))
    secret = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _schema():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    await close_redis()
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def _clean_redis():
    await get_redis().flushdb()
    yield


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest_asyncio.fixture
async def session():
    async with SessionFactory() as session:
        yield session


@pytest.fixture
def anyio_backend():
    return "asyncio"


async def authenticate(client: AsyncClient, telegram_id: int, **kwargs) -> dict:
    response = await client.post(
        "/api/auth/telegram", json={"init_data": make_init_data(telegram_id, **kwargs)}
    )
    assert response.status_code == 200, response.text
    return response.json()


def auth_header(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
