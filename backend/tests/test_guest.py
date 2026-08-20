"""Browser (guest) sign-in.

The Telegram path must stay exactly as strict as before; the guest path is a
separate, explicitly enabled door.
"""

import pytest

from app.core.config import settings
from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


@pytest.fixture
def browser_login_enabled():
    settings.allow_browser_login = True
    yield
    settings.allow_browser_login = False


async def test_guest_login_is_off_by_default(client):
    response = await client.post("/api/auth/guest", json={"device_id": "browser-device-1"})
    assert response.status_code == 403

    modes = (await client.get("/api/auth/modes")).json()
    assert modes["telegram"] is True and modes["guest"] is False


async def test_guest_can_play_when_enabled(client, browser_login_enabled):
    first = await client.post("/api/auth/guest", json={"device_id": "browser-device-2"})
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["is_new"] is True
    assert body["user"]["telegram_id"] < 0, "guests live in a reserved id range"
    assert body["user"]["is_admin"] is False
    assert body["user"]["balance"] == 1000

    headers = auth_header(body["token"])
    played = await client.post("/api/solo/plinko/play", json={"bet": 100}, headers=headers)
    assert played.status_code == 200
    assert played.json()["balance"] != 1000


async def test_same_device_returns_the_same_account(client, browser_login_enabled):
    payload = {"device_id": "browser-device-3"}
    first = (await client.post("/api/auth/guest", json=payload)).json()
    second = (await client.post("/api/auth/guest", json=payload)).json()

    assert second["is_new"] is False
    assert first["user"]["id"] == second["user"]["id"]

    other = (await client.post("/api/auth/guest", json={"device_id": "browser-device-4"})).json()
    assert other["user"]["id"] != first["user"]["id"]


async def test_guest_cannot_become_admin(client, browser_login_enabled):
    # The admin allowlist holds telegram id 1001; a guest id can never match it.
    guest = (await client.post("/api/auth/guest", json={"device_id": "browser-device-5"})).json()
    headers = auth_header(guest["token"])
    assert (await client.get("/api/admin/stats", headers=headers)).status_code == 403


async def test_short_device_id_is_rejected(client, browser_login_enabled):
    assert (await client.post("/api/auth/guest", json={"device_id": "short"})).status_code == 422


async def test_telegram_login_is_unaffected(client, browser_login_enabled):
    # Enabling guest play must not loosen signature checking.
    forged = await client.post("/api/auth/telegram", json={"init_data": "user=%7B%22id%22%3A9%7D&hash=bad"})
    assert forged.status_code == 401

    real = await authenticate(client, 9401)
    assert real["user"]["telegram_id"] == 9401
