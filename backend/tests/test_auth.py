import pytest

from tests.conftest import auth_header, authenticate, make_init_data

pytestmark = pytest.mark.asyncio


async def test_signature_is_required(client):
    response = await client.post("/api/auth/telegram", json={"init_data": "user=%7B%22id%22%3A1%7D&hash=deadbeef"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_forged_user_is_rejected(client):
    # A valid signature for user 5001 cannot be reused with a swapped user id.
    tampered = make_init_data(5001).replace("5001", "5002")
    response = await client.post("/api/auth/telegram", json={"init_data": tampered})
    assert response.status_code == 401


async def test_login_creates_user_once(client):
    first = await authenticate(client, 4242, username="alice")
    assert first["is_new"] is True
    assert first["user"]["balance"] == 1000  # signup bonus

    second = await authenticate(client, 4242, username="alice")
    assert second["is_new"] is False
    assert second["user"]["id"] == first["user"]["id"]
    assert second["user"]["balance"] == 1000  # bonus is not paid twice


async def test_me_requires_token(client):
    assert (await client.get("/api/me")).status_code == 401

    auth = await authenticate(client, 4243)
    response = await client.get("/api/me", headers=auth_header(auth["token"]))
    assert response.status_code == 200
    assert response.json()["telegram_id"] == 4243


async def test_referral_link_binds_and_pays_once(client):
    inviter = await authenticate(client, 4300, username="inviter")
    code = inviter["user"]["referral_code"]

    invited = await authenticate(client, 4301, username="invited", start_param=f"ref_{code}")
    assert invited["user"]["referral_id"] == inviter["user"]["id"]

    stats = await client.get("/api/referrals", headers=auth_header(inviter["token"]))
    body = stats.json()
    assert body["invited_count"] == 1
    assert body["earnings"] == 50

    # Re-opening the deep link must not pay the inviter again.
    await authenticate(client, 4301, username="invited", start_param=f"ref_{code}")
    again = (await client.get("/api/referrals", headers=auth_header(inviter["token"]))).json()
    assert again["earnings"] == 50
