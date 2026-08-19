import pytest

from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


async def _login(client, telegram_id):
    auth = await authenticate(client, telegram_id)
    return auth_header(auth["token"]), auth["user"]


async def test_plinko_pays_from_the_server_table(client):
    headers, _ = await _login(client, 6001)
    before = (await client.get("/api/balance", headers=headers)).json()["balance"]

    response = await client.post(
        "/api/solo/plinko/play", json={"bet": 100, "rows": 12, "risk": "medium"}, headers=headers
    )
    assert response.status_code == 200, response.text
    body = response.json()

    result = body["game"]["result"]
    assert len(result["path"]) == 12
    assert result["slot"] == sum(1 for step in result["path"] if step == "R")
    assert result["multiplier"] == result["multipliers"][result["slot"]]
    assert body["game"]["reward"] == round(100 * result["multiplier"])
    assert body["balance"] == before - 100 + body["game"]["reward"]
    # The seed is revealed once the round is over, so the roll can be recomputed.
    assert body["game"]["server_seed"]


async def test_solo_rejects_bet_above_balance(client):
    headers, _ = await _login(client, 6002)
    response = await client.post(
        "/api/solo/plinko/play", json={"bet": 50_000, "rows": 8, "risk": "low"}, headers=headers
    )
    assert response.status_code == 402
    assert response.json()["error"]["code"] == "insufficient_funds"


async def test_idempotency_key_collapses_a_retry(client):
    headers, _ = await _login(client, 6003)
    headers = {**headers, "X-Idempotency-Key": "retry-me-once"}
    payload = {"bet": 100, "target": 2.0}

    first = await client.post("/api/solo/upgrade/play", json=payload, headers=headers)
    second = await client.post("/api/solo/upgrade/play", json=payload, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["game"]["id"] == second.json()["game"]["id"]
    assert first.json()["balance"] == second.json()["balance"]

    history = (await client.get("/api/solo/history", headers=headers)).json()
    assert history["total"] == 1  # the retry did not start a second round


async def test_upgrade_odds_match_the_declared_chance(client):
    headers, _ = await _login(client, 6004)
    response = await client.post(
        "/api/solo/upgrade/play", json={"bet": 50, "target": 5.0}, headers=headers
    )
    result = response.json()["game"]["result"]
    assert result["chance"] == pytest.approx(0.96 / 5.0, rel=1e-6)
    assert result["won"] == (result["roll"] < result["chance"])
    assert response.json()["game"]["reward"] == (250 if result["won"] else 0)


async def test_lucky_buy_drops_an_item_that_can_be_sold(client):
    headers, _ = await _login(client, 6005)
    response = await client.post("/api/solo/lucky-buy/play", json={"case": "frost"}, headers=headers)
    assert response.status_code == 200, response.text
    item = response.json()["item"]

    inventory = (await client.get("/api/inventory", headers=headers)).json()
    assert any(i["id"] == item["id"] for i in inventory["items"])

    sold = await client.post(
        f"/api/inventory/{item['id']}/sell", headers={**headers, "X-Idempotency-Key": "sell-1"}
    )
    assert sold.status_code == 200
    assert sold.json()["payout"] == item["gg_value"]

    # Replaying the same key returns the first response instead of paying again.
    replay = await client.post(
        f"/api/inventory/{item['id']}/sell", headers={**headers, "X-Idempotency-Key": "sell-1"}
    )
    assert replay.status_code == 200
    assert replay.json() == sold.json()

    # A genuinely new request cannot sell the item a second time.
    again = await client.post(
        f"/api/inventory/{item['id']}/sell", headers={**headers, "X-Idempotency-Key": "sell-2"}
    )
    assert again.status_code == 409


async def test_hilo_round_trip(client):
    headers, _ = await _login(client, 6006)
    started = await client.post("/api/solo/hilo/play", json={"action": "start", "bet": 100}, headers=headers)
    assert started.status_code == 200, started.text
    state = started.json()["state"]
    game_id = state["game_id"]
    assert 1 <= state["card"] <= 13

    # Always guess the side with the better odds so the run usually survives.
    choice = "higher" if state["card"] <= 7 else "lower"
    guessed = await client.post(
        "/api/solo/hilo/play",
        json={"action": "guess", "game_id": game_id, "choice": choice},
        headers=headers,
    )
    assert guessed.status_code == 200
    body = guessed.json()

    if body["game"]["status"] == "active":
        cashed = await client.post(
            "/api/solo/hilo/play", json={"action": "cash_out", "game_id": game_id}, headers=headers
        )
        assert cashed.status_code == 200
        assert cashed.json()["game"]["status"] == "cashed_out"
        assert cashed.json()["game"]["reward"] > 0
    else:
        assert body["game"]["status"] == "lost"
        assert body["game"]["reward"] == 0


async def test_hilo_allows_only_one_active_round(client):
    headers, _ = await _login(client, 6007)
    await client.post("/api/solo/hilo/play", json={"action": "start", "bet": 50}, headers=headers)
    second = await client.post("/api/solo/hilo/play", json={"action": "start", "bet": 50}, headers=headers)
    assert second.status_code == 409


async def test_ice_arena_run(client):
    headers, _ = await _login(client, 6008)
    started = await client.post(
        "/api/solo/ice-arena/play", json={"action": "start", "bet": 100}, headers=headers
    )
    assert started.status_code == 200, started.text
    game_id = started.json()["state"]["game_id"]

    advanced = await client.post(
        "/api/solo/ice-arena/play",
        json={"action": "advance", "game_id": game_id, "difficulty": "easy"},
        headers=headers,
    )
    assert advanced.status_code == 200
    body = advanced.json()
    assert len(body["state"]["history"]) == 1

    if body["game"]["status"] == "active":
        cashed = await client.post(
            "/api/solo/ice-arena/play", json={"action": "cash_out", "game_id": game_id}, headers=headers
        )
        assert cashed.status_code == 200
        assert cashed.json()["game"]["reward"] == round(100 * body["state"]["multiplier"])


async def test_cannot_touch_another_players_round(client):
    owner_headers, _ = await _login(client, 6009)
    started = await client.post(
        "/api/solo/ice-arena/play", json={"action": "start", "bet": 50}, headers=owner_headers
    )
    game_id = started.json()["state"]["game_id"]

    intruder_headers, _ = await _login(client, 6010)
    response = await client.post(
        "/api/solo/ice-arena/play",
        json={"action": "advance", "game_id": game_id, "difficulty": "easy"},
        headers=intruder_headers,
    )
    assert response.status_code == 404


async def test_plinko_tables_return_the_configured_edge(client):
    headers, _ = await _login(client, 6011)
    config = (await client.get("/api/solo/config", headers=headers)).json()
    from math import comb

    for key, table in config["plinko"]["tables"].items():
        rows = int(key.split(":")[0])
        total = 2**rows
        expected = sum(comb(rows, i) / total * m for i, m in enumerate(table))
        assert expected == pytest.approx(1 - config["house_edge"], rel=1e-3)
