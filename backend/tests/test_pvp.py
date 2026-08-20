import asyncio
import itertools

import pytest

from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


async def _login(client, telegram_id):
    auth = await authenticate(client, telegram_id)
    return auth_header(auth["token"]), auth["user"]


async def test_full_round_pays_the_winner(client):
    host, host_user = await _login(client, 7001)
    guest, guest_user = await _login(client, 7002)

    created = await client.post("/api/pvp/create", json={"amount": 300}, headers=host)
    assert created.status_code == 200, created.text
    game = created.json()["game"]
    game_id = game["id"]
    assert game["status"] == "waiting"
    assert created.json()["balance"] == 700

    joined = await client.post(f"/api/pvp/{game_id}/join", json={"amount": 200}, headers=guest)
    assert joined.status_code == 200, joined.text
    body = joined.json()["game"]
    assert body["status"] == "starting"
    assert body["total_pool"] == 500
    chances = {p["user_id"]: p["chance"] for p in body["players"]}
    assert chances[host_user["id"]] == pytest.approx(0.6)
    assert chances[guest_user["id"]] == pytest.approx(0.4)

    # Countdown (1s) + spin (1s) are driven by timestamps, so simply waiting and
    # reading the state is enough to settle the round.
    await asyncio.sleep(2.4)
    state = (await client.get(f"/api/pvp/{game_id}", headers=host)).json()["game"]
    assert state["status"] == "finished"
    assert state["winner_id"] in {host_user["id"], guest_user["id"]}
    assert state["rake"] == 25  # 5% of 500
    assert state["prize"] == 475
    assert state["server_seed"], "seed is revealed after the round"

    winner_headers = host if state["winner_id"] == host_user["id"] else guest
    loser_headers = guest if state["winner_id"] == host_user["id"] else host
    winner_bet = 300 if state["winner_id"] == host_user["id"] else 200

    winner_balance = (await client.get("/api/balance", headers=winner_headers)).json()["balance"]
    loser_balance = (await client.get("/api/balance", headers=loser_headers)).json()["balance"]
    assert winner_balance == 1000 - winner_bet + 475
    assert loser_balance == 1000 - (500 - winner_bet)

    # Reading it again must not pay out a second time.
    await client.get(f"/api/pvp/{game_id}", headers=host)
    assert (await client.get("/api/balance", headers=winner_headers)).json()["balance"] == winner_balance


async def test_ticket_ranges_cover_the_pool_exactly(client):
    host, _ = await _login(client, 7003)
    guest, _ = await _login(client, 7004)
    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]
    game = (await client.post(f"/api/pvp/{game_id}/join", json={"amount": 400}, headers=guest)).json()["game"]

    players = sorted(game["players"], key=lambda p: p["ticket_from"])
    assert players[0]["ticket_from"] == 0
    assert players[-1]["ticket_to"] == game["total_pool"]
    for previous, following in itertools.pairwise(players):
        assert previous["ticket_to"] == following["ticket_from"]


async def test_cannot_join_a_finished_round(client):
    host, _ = await _login(client, 7005)
    guest, _ = await _login(client, 7006)
    latecomer, _ = await _login(client, 7007)

    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]
    await client.post(f"/api/pvp/{game_id}/join", json={"amount": 100}, headers=guest)
    await asyncio.sleep(2.4)

    response = await client.post(f"/api/pvp/{game_id}/join", json={"amount": 100}, headers=latecomer)
    assert response.status_code == 409
    assert (await client.get("/api/balance", headers=latecomer)).json()["balance"] == 1000


async def test_join_below_minimum_is_rejected(client):
    host, _ = await _login(client, 7008)
    response = await client.post("/api/pvp/create", json={"amount": 1}, headers=host)
    assert response.status_code == 422


async def test_bet_is_refused_without_funds(client):
    host, user = await _login(client, 7009)
    response = await client.post("/api/pvp/create", json={"amount": 5000}, headers=host)
    assert response.status_code == 402

    # The failed debit rolls the whole request back: no orphan lobby is left.
    lobbies = (await client.get("/api/pvp", headers=host)).json()["items"]
    assert all(lobby["creator_id"] != user["id"] for lobby in lobbies)


async def test_duplicate_join_key_does_not_double_charge(client):
    host, _ = await _login(client, 7010)
    guest, _ = await _login(client, 7011)
    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]

    headers = {**guest, "X-Idempotency-Key": "join-once"}
    first = await client.post(f"/api/pvp/{game_id}/join", json={"amount": 250}, headers=headers)
    second = await client.post(f"/api/pvp/{game_id}/join", json={"amount": 250}, headers=headers)

    assert first.status_code == second.status_code == 200
    assert first.json()["balance"] == second.json()["balance"] == 750
    assert second.json()["game"]["total_pool"] == 350


async def test_quick_join_puts_players_in_the_same_round(client):
    """The arena shows one round, so matchmaking must not fragment it."""
    a, _ = await _login(client, 7101)
    b, _ = await _login(client, 7102)
    c, _ = await _login(client, 7103)

    # Open a fresh round explicitly: the newest open lobby is the one matchmaking
    # should pick, whatever earlier tests left lying around.
    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=a)).json()["game"]["id"]

    second = await client.post("/api/pvp/quick-join", json={"amount": 200}, headers=b)
    third = await client.post("/api/pvp/quick-join", json={"amount": 50}, headers=c)

    assert second.status_code == third.status_code == 200
    assert second.json()["created"] is False
    assert third.json()["created"] is False
    assert second.json()["game"]["id"] == game_id
    assert third.json()["game"]["id"] == game_id
    assert third.json()["game"]["total_pool"] == 350


async def test_current_returns_the_live_round_then_the_last_result(client):
    import asyncio

    a, _ = await _login(client, 7104)
    b, _ = await _login(client, 7105)

    game_id = (await client.post("/api/pvp/quick-join", json={"amount": 100}, headers=a)).json()["game"]["id"]
    live = (await client.get("/api/pvp/current", headers=a)).json()
    assert live["game"]["id"] == game_id
    assert live["config"]["rake_percent"] == 5

    await client.post("/api/pvp/quick-join", json={"amount": 100}, headers=b)
    await asyncio.sleep(2.4)

    settled = (await client.get("/api/pvp/current", headers=a)).json()
    assert settled["game"]["status"] == "finished"
    assert settled["game"]["winner_id"] is not None


async def test_highlights_report_the_last_and_biggest_rounds(client):
    a, _ = await _login(client, 7106)
    response = await client.get("/api/pvp/highlights", headers=a)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"last", "top", "online"}
    assert body["online"] >= 1
    if body["last"]:
        assert body["last"]["winner"]["name"]
        assert body["last"]["prize"] > 0


async def test_the_draw_is_published_when_the_spin_starts(client):
    """Clients need the result before the animation, not after it."""
    host, _ = await _login(client, 7107)
    guest, _ = await _login(client, 7108)

    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]
    joined = await client.post(f"/api/pvp/{game_id}/join", json={"amount": 100}, headers=guest)
    assert joined.json()["game"]["winning_roll"] is None, "nothing is drawn while players can still join"

    # Countdown is 1s in tests and the spin 1s: land in the middle of the spin.
    await asyncio.sleep(1.3)
    spinning = (await client.get(f"/api/pvp/{game_id}", headers=host)).json()["game"]
    assert spinning["status"] == "spinning"
    roll = spinning["winning_roll"]
    assert roll is not None and 0 <= roll < 1
    assert spinning["server_seed"] is None, "the seed stays hidden until the round ends"

    await asyncio.sleep(1.4)
    settled = (await client.get(f"/api/pvp/{game_id}", headers=host)).json()["game"]
    assert settled["status"] == "finished"
    # Settlement must land on the number that was already published.
    assert settled["winning_roll"] == roll
    assert settled["server_seed"]


async def test_the_arena_clears_once_a_result_has_been_read(client, monkeypatch):
    """A finished round lingers, then the arena is empty again rather than stuck."""
    from datetime import timedelta

    from app.services import pvp as service

    host, _ = await _login(client, 7109)
    guest, _ = await _login(client, 7110)

    await client.post("/api/pvp/quick-join", json={"amount": 100}, headers=host)
    await client.post("/api/pvp/quick-join", json={"amount": 100}, headers=guest)
    await asyncio.sleep(2.4)

    settled = (await client.get("/api/pvp/current", headers=host)).json()
    assert settled["game"]["status"] == "finished", "the result is shown right after the draw"

    monkeypatch.setattr(service, "RESULT_LINGER", timedelta(seconds=0))
    cleared = (await client.get("/api/pvp/current", headers=host)).json()
    assert cleared["game"] is None


async def test_wheel_and_ice_rounds_never_share_a_pot(client):
    """The two boards are separate games; a bet must not cross between them."""
    a, _ = await _login(client, 7201)
    b, _ = await _login(client, 7202)

    wheel = await client.post("/api/pvp/quick-join", json={"amount": 100, "mode": "wheel"}, headers=a)
    ice = await client.post("/api/pvp/quick-join", json={"amount": 100, "mode": "ice"}, headers=b)

    assert wheel.status_code == ice.status_code == 200
    assert wheel.json()["game"]["mode"] == "wheel"
    assert ice.json()["game"]["mode"] == "ice"
    assert wheel.json()["game"]["id"] != ice.json()["game"]["id"]
    # An ice bet joined an ice round, so the wheel pot is untouched by it.
    assert ice.json()["game"]["total_pool"] == 100

    current_wheel = (await client.get("/api/pvp/current?mode=wheel", headers=a)).json()["game"]
    current_ice = (await client.get("/api/pvp/current?mode=ice", headers=a)).json()["game"]
    assert current_wheel["mode"] == "wheel"
    assert current_ice["mode"] == "ice"
    assert current_wheel["id"] != current_ice["id"]


async def test_matchmaking_keeps_each_mode_together(client):
    a, _ = await _login(client, 7203)
    b, _ = await _login(client, 7204)

    # Open a fresh ice round so the assertion does not depend on what earlier
    # tests left waiting.
    first = await client.post("/api/pvp/create", json={"amount": 50, "mode": "ice"}, headers=a)
    assert first.json()["game"]["mode"] == "ice"

    second = await client.post("/api/pvp/quick-join", json={"amount": 70, "mode": "ice"}, headers=b)
    assert second.json()["game"]["id"] == first.json()["game"]["id"]
    assert second.json()["game"]["total_pool"] == 120

    # A wheel player pressing the button at the same moment opens their own round.
    c, _ = await _login(client, 7206)
    wheel = await client.post("/api/pvp/quick-join", json={"amount": 70, "mode": "wheel"}, headers=c)
    assert wheel.json()["game"]["id"] != first.json()["game"]["id"]


async def test_an_unknown_mode_is_rejected(client):
    a, _ = await _login(client, 7205)
    response = await client.post("/api/pvp/quick-join", json={"amount": 50, "mode": "roulette"}, headers=a)
    assert response.status_code == 422


async def test_a_round_can_be_replayed_from_the_first_bet(client):
    """The replay is derived from the round itself, not a second record of it."""
    a, first = await _login(client, 7301)
    b, second = await _login(client, 7302)

    game_id = (await client.post("/api/pvp/create", json={"amount": 300}, headers=a)).json()["game"]["id"]
    await asyncio.sleep(0.2)
    await client.post(f"/api/pvp/{game_id}/join", json={"amount": 100}, headers=b)
    await asyncio.sleep(2.4)

    response = await client.get(f"/api/pvp/{game_id}/replay", headers=a)
    assert response.status_code == 200, response.text
    timeline = response.json()["replay"]

    assert timeline["status"] == "finished"
    assert timeline["mode"] == "wheel"

    kinds = [event["type"] for event in timeline["events"]]
    assert kinds[0] == "player_joined"
    assert kinds.count("player_joined") == 2
    assert {"countdown", "spin", "finished"} <= set(kinds)

    joins = [event for event in timeline["events"] if event["type"] == "player_joined"]
    # The first bet anchors the timeline and the pot grows in order.
    assert joins[0]["at"] == 0
    assert joins[0]["user_id"] == first["id"] and joins[0]["pool"] == 300
    assert joins[1]["user_id"] == second["id"] and joins[1]["pool"] == 400
    assert joins[1]["at"] > 0

    end = next(event for event in timeline["events"] if event["type"] == "finished")
    assert end["prize"] == 380
    assert end["roll"] == response.json()["game"]["winning_roll"]
    assert timeline["duration"] >= end["at"]
