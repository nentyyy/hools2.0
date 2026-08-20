from datetime import UTC, datetime, timedelta

import pytest

from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


async def _admin(client):
    auth = await authenticate(client, 1001, username="admin")
    return auth_header(auth["token"])


async def _create(client, admin_headers, **overrides):
    payload = {
        "title": "Frost Drop",
        "description": "Win 500 GG",
        "prize_type": "gg",
        "prize_value": 500,
        "end_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
    }
    payload.update(overrides)
    response = await client.post("/api/admin/giveaways", json=payload, headers=admin_headers)
    assert response.status_code == 200, response.text
    return response.json()


async def test_join_once_and_only_once(client):
    admin_headers = await _admin(client)
    giveaway = await _create(client, admin_headers)

    auth = await authenticate(client, 9001)
    headers = auth_header(auth["token"])

    joined = await client.post(
        f"/api/giveaways/{giveaway['id']}/join", headers={**headers, "X-Idempotency-Key": "join-1"}
    )
    assert joined.status_code == 200, joined.text
    assert joined.json()["joined"] is True
    assert joined.json()["participants_count"] == 1

    duplicate = await client.post(
        f"/api/giveaways/{giveaway['id']}/join", headers={**headers, "X-Idempotency-Key": "join-2"}
    )
    assert duplicate.status_code == 409

    detail = (await client.get(f"/api/giveaways/{giveaway['id']}", headers=headers)).json()
    assert detail["participants_count"] == 1
    assert detail["joined"] is True


async def test_entry_fee_is_charged_and_level_gate_applies(client):
    admin_headers = await _admin(client)
    paid = await _create(client, admin_headers, title="Paid entry", entry_cost=100)
    gated = await _create(client, admin_headers, title="Level gate", min_level=5)

    auth = await authenticate(client, 9002)
    headers = auth_header(auth["token"])

    response = await client.post(f"/api/giveaways/{paid['id']}/join", headers=headers)
    assert response.status_code == 200
    assert response.json()["balance"] == 900

    blocked = await client.post(f"/api/giveaways/{gated['id']}/join", headers=headers)
    assert blocked.status_code == 409
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 900


async def test_finished_giveaway_pays_a_participant(client):
    admin_headers = await _admin(client)
    giveaway = await _create(client, admin_headers, title="Payout test", prize_value=750)

    players = {}
    for telegram_id in (9003, 9004, 9005):
        auth = await authenticate(client, telegram_id)
        headers = auth_header(auth["token"])
        players[auth["user"]["id"]] = headers
        assert (await client.post(f"/api/giveaways/{giveaway['id']}/join", headers=headers)).status_code == 200

    participants = (
        await client.get(f"/api/giveaways/{giveaway['id']}/participants", headers=admin_headers)
    ).json()
    assert participants["total"] == 3

    finished = await client.post(f"/api/admin/giveaways/{giveaway['id']}/finish", headers=admin_headers)
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert body["status"] == "finished"
    assert body["winner_id"] in players

    winner_balance = (await client.get("/api/balance", headers=players[body["winner_id"]])).json()["balance"]
    assert winner_balance == 1750

    # Finishing again must not pay a second prize.
    await client.post(f"/api/admin/giveaways/{giveaway['id']}/finish", headers=admin_headers)
    assert (await client.get("/api/balance", headers=players[body["winner_id"]])).json()["balance"] == 1750


async def test_cannot_join_a_closed_giveaway(client):
    admin_headers = await _admin(client)
    giveaway = await _create(client, admin_headers, title="Closed")
    await client.post(f"/api/admin/giveaways/{giveaway['id']}/finish", headers=admin_headers)

    auth = await authenticate(client, 9006)
    response = await client.post(
        f"/api/giveaways/{giveaway['id']}/join", headers=auth_header(auth["token"])
    )
    assert response.status_code == 409


async def test_creating_a_giveaway_requires_admin(client):
    auth = await authenticate(client, 9007)
    response = await client.post(
        "/api/admin/giveaways",
        json={"title": "nope", "end_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
        headers=auth_header(auth["token"]),
    )
    assert response.status_code == 403


async def test_expired_giveaway_is_drawn_on_read(client):
    """No cron needed: opening an ended giveaway resolves it."""
    admin_headers = await _admin(client)
    now = datetime.now(UTC)
    giveaway = await _create(
        client,
        admin_headers,
        title="Already over",
        prize_value=300,
        start_at=(now - timedelta(hours=2)).isoformat(),
        end_at=(now + timedelta(seconds=1)).isoformat(),
    )

    auth = await authenticate(client, 9008)
    headers = auth_header(auth["token"])
    assert (await client.post(f"/api/giveaways/{giveaway['id']}/join", headers=headers)).status_code == 200

    # Move the deadline into the past, then simply read it.
    await client.patch(
        f"/api/admin/giveaways/{giveaway['id']}",
        json={"end_at": (now - timedelta(minutes=1)).isoformat()},
        headers=admin_headers,
    )

    detail = (await client.get(f"/api/giveaways/{giveaway['id']}", headers=headers)).json()
    assert detail["status"] == "finished"
    assert detail["winner_id"] == auth["user"]["id"]
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1300

    # And reading it again does not pay a second prize.
    await client.get(f"/api/giveaways/{giveaway['id']}", headers=headers)
    assert (await client.get("/api/balance", headers=headers)).json()["balance"] == 1300
