"""The bot's path to the backend.

In webhook mode the bot runs inside the backend process, so it must reach the
internal API without a network hop — there is no loopback address on a
serverless host, and the public URL would cost a second invocation per button
press. These tests pin that wiring, because when it breaks every bot command
answers "we can't reach the game server".
"""

import pytest

from gg_bot import api as bot_api

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def _fresh_client():
    await bot_api.close_client()
    yield
    await bot_api.close_client()


async def test_the_bot_uses_the_in_process_transport(client):
    import httpx

    transport = bot_api.get_client()._transport
    assert isinstance(transport, httpx.ASGITransport), "no HTTP hop when co-located"


async def test_start_registers_a_user_through_the_internal_api(client):
    data = await bot_api.ensure_user(
        770001,
        username="botuser",
        first_name="Bot",
        last_name="User",
        language_code="en",
    )
    assert data["telegram_id"] == 770001
    assert data["created"] is True
    assert data["balance"] == 1000  # welcome bonus
    assert data["referral_link"].startswith("https://t.me/")

    again = await bot_api.ensure_user(
        770001, username="botuser", first_name="Bot", last_name="User", language_code="en"
    )
    assert again["created"] is False


async def test_referral_deep_link_binds_through_the_bot(client):
    inviter = await bot_api.ensure_user(
        770002, username="inviter", first_name="Inv", last_name=None, language_code="en"
    )
    invited = await bot_api.ensure_user(
        770003,
        username="invited",
        first_name="Inv2",
        last_name=None,
        language_code="en",
        start_param=f"ref_{inviter['referral_code']}",
    )
    assert invited["created"] is True

    refreshed = await bot_api.get_user(770002)
    assert refreshed["stats"]["referral_earnings"] == 50


async def test_a_bad_internal_token_is_reported_not_swallowed(client, monkeypatch):
    monkeypatch.setattr(bot_api.settings, "internal_api_token", "wrong-token")
    with pytest.raises(bot_api.BackendError) as failure:
        await bot_api.get_user(770001)
    assert failure.value.status_code == 401
