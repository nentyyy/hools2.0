"""Race conditions are the failure mode that actually loses money, so they get
their own suite: concurrent bets, concurrent joins and a ledger consistency
check that walks every row for the user.
"""

import asyncio

import pytest
from sqlalchemy import select

from app.models import Transaction, User
from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


async def _assert_ledger_is_consistent(session, user_id: int) -> int:
    rows = (
        (
            await session.execute(
                select(Transaction).where(Transaction.user_id == user_id).order_by(Transaction.id)
            )
        )
        .scalars()
        .all()
    )
    running = 0
    for row in rows:
        assert row.balance_before == running, f"gap before transaction {row.id}"
        assert row.balance_after == row.balance_before + row.amount
        assert row.balance_after >= 0
        running = row.balance_after

    user = await session.get(User, user_id)
    await session.refresh(user)
    assert int(user.balance) == running, "user row and ledger disagree"
    return running


async def test_parallel_bets_cannot_overdraw(client, session):
    auth = await authenticate(client, 9201)
    headers = auth_header(auth["token"])
    user_id = auth["user"]["id"]

    # Balance is 1000; twenty simultaneous 200 GG bets means at most five can win
    # the race, and only if none of them pays out in between.
    responses = await asyncio.gather(
        *[
            client.post("/api/solo/plinko/play", json={"bet": 200, "rows": 8, "risk": "low"}, headers=headers)
            for _ in range(20)
        ]
    )
    codes = [r.status_code for r in responses]
    assert set(codes) <= {200, 402, 409}
    assert 200 in codes

    balance = (await client.get("/api/balance", headers=headers)).json()["balance"]
    assert balance >= 0
    assert await _assert_ledger_is_consistent(session, user_id) == balance


async def test_parallel_joins_charge_once_per_request(client, session):
    host, _ = auth_header((await authenticate(client, 9202))["token"]), None
    guest_auth = await authenticate(client, 9203)
    guest = auth_header(guest_auth["token"])

    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]

    # The same idempotency key sent five times at once: one seat, one debit.
    headers = {**guest, "X-Idempotency-Key": "parallel-join"}
    responses = await asyncio.gather(
        *[client.post(f"/api/pvp/{game_id}/join", json={"amount": 300}, headers=headers) for _ in range(5)],
        return_exceptions=True,
    )
    statuses = [r.status_code for r in responses if not isinstance(r, Exception)]
    assert 200 in statuses
    assert all(code in {200, 409} for code in statuses)

    balance = (await client.get("/api/balance", headers=guest)).json()["balance"]
    assert balance == 700
    assert await _assert_ledger_is_consistent(session, guest_auth["user"]["id"]) == 700

    game = (await client.get(f"/api/pvp/{game_id}", headers=guest)).json()["game"]
    seats = [p for p in game["players"] if p["user_id"] == guest_auth["user"]["id"]]
    assert len(seats) == 1
    assert seats[0]["amount"] == 300


async def test_parallel_giveaway_joins_create_one_entry(client, session):
    from datetime import UTC, datetime, timedelta

    admin = auth_header((await authenticate(client, 1001, username="admin"))["token"])
    giveaway = (
        await client.post(
            "/api/admin/giveaways",
            json={
                "title": "Race",
                "prize_type": "gg",
                "prize_value": 100,
                "end_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            },
            headers=admin,
        )
    ).json()

    auth = await authenticate(client, 9204)
    headers = auth_header(auth["token"])
    responses = await asyncio.gather(
        *[
            client.post(
                f"/api/giveaways/{giveaway['id']}/join",
                headers={**headers, "X-Idempotency-Key": f"g-{i}"},
            )
            for i in range(6)
        ]
    )
    assert sum(1 for r in responses if r.status_code == 200) == 1
    assert all(r.status_code in {200, 409} for r in responses)

    detail = (await client.get(f"/api/giveaways/{giveaway['id']}", headers=headers)).json()
    assert detail["participants_count"] == 1


async def test_parallel_settlement_pays_the_winner_once(client, session):
    host_auth = await authenticate(client, 9205)
    guest_auth = await authenticate(client, 9206)
    host = auth_header(host_auth["token"])
    guest = auth_header(guest_auth["token"])

    game_id = (await client.post("/api/pvp/create", json={"amount": 200}, headers=host)).json()["game"]["id"]
    await client.post(f"/api/pvp/{game_id}/join", json={"amount": 200}, headers=guest)
    await asyncio.sleep(2.4)

    # Ten readers hit the round the moment its timer expires; exactly one of them
    # gets to settle it.
    await asyncio.gather(*[client.get(f"/api/pvp/{game_id}", headers=host) for _ in range(10)])

    game = (await client.get(f"/api/pvp/{game_id}", headers=host)).json()["game"]
    assert game["status"] == "finished"

    winner_id = game["winner_id"]
    total = await _assert_ledger_is_consistent(session, winner_id)
    assert total == 1000 - 200 + 380  # one bet, one prize (400 pool minus 5% rake)
