import pytest

from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


async def _admin(client):
    auth = await authenticate(client, 1001, username="admin")
    return auth_header(auth["token"])


async def test_admin_endpoints_reject_regular_users(client):
    auth = await authenticate(client, 9101)
    headers = auth_header(auth["token"])
    for path in ("/api/admin/stats", "/api/admin/users", "/api/admin/transactions", "/api/admin/pvp"):
        assert (await client.get(path, headers=headers)).status_code == 403


async def test_admin_can_adjust_balance_through_the_ledger(client):
    admin_headers = await _admin(client)
    auth = await authenticate(client, 9102)
    user_id = auth["user"]["id"]
    headers = auth_header(auth["token"])

    granted = await client.post(
        f"/api/admin/users/{user_id}/balance",
        json={"amount": 2500, "description": "test grant"},
        headers=admin_headers,
    )
    assert granted.status_code == 200
    assert granted.json()["balance"] == 3500

    taken = await client.post(
        f"/api/admin/users/{user_id}/balance", json={"amount": -500}, headers=admin_headers
    )
    assert taken.json()["balance"] == 3000

    history = (await client.get("/api/transactions?type=admin_adjustment", headers=headers)).json()
    # welcome bonus + grant + deduction
    assert history["total"] == 3
    assert history["items"][0]["balance_after"] == 3000


async def test_admin_cannot_overdraw_a_user(client):
    admin_headers = await _admin(client)
    auth = await authenticate(client, 9103)
    user_id = auth["user"]["id"]

    response = await client.post(
        f"/api/admin/users/{user_id}/balance", json={"amount": -99999}, headers=admin_headers
    )
    assert response.status_code == 402
    assert (await client.get("/api/balance", headers=auth_header(auth["token"]))).json()["balance"] == 1000


async def test_ban_blocks_api_access(client):
    admin_headers = await _admin(client)
    auth = await authenticate(client, 9104)
    headers = auth_header(auth["token"])
    user_id = auth["user"]["id"]

    banned = await client.post(
        f"/api/admin/users/{user_id}/ban", json={"reason": "cheating"}, headers=admin_headers
    )
    assert banned.status_code == 200

    blocked = await client.get("/api/profile", headers=headers)
    assert blocked.status_code == 403
    assert blocked.json()["error"]["message"] == "cheating"

    play = await client.post("/api/solo/plinko/play", json={"bet": 10}, headers=headers)
    assert play.status_code == 403

    await client.post(f"/api/admin/users/{user_id}/unban", headers=admin_headers)
    assert (await client.get("/api/profile", headers=headers)).status_code == 200


async def test_stats_and_listings_render(client):
    admin_headers = await _admin(client)
    stats = await client.get("/api/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    body = stats.json()
    assert body["users"]["total"] >= 1
    assert "gg_circulating" in body["economy"]

    users = await client.get("/api/admin/users?q=admin", headers=admin_headers)
    assert users.status_code == 200
    assert users.json()["total"] >= 1


async def test_cron_tick_requires_the_secret(client):
    assert (await client.post("/api/internal/tick")).status_code == 401
    ok = await client.post("/api/internal/tick", headers={"X-Cron-Token": "test-cron"})
    assert ok.status_code == 200
    assert ok.json()["ok"] is True
