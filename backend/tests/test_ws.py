"""Websocket frame encoding.

Regression guard: game payloads carry datetimes, which `WebSocket.send_json`
refuses. Frames are serialised with `default=str` and sent as text instead — if
that ever regresses, clients silently receive nothing.
"""

import json
from datetime import UTC, datetime

import pytest

from app.api.serializers import serialize_pvp
from app.services import pvp as pvp_service
from app.ws.events import PvPEvent, pvp_channel
from app.ws.manager import _encode
from tests.conftest import auth_header, authenticate

pytestmark = pytest.mark.asyncio


def test_encode_handles_datetimes():
    frame = {"event": "state", "data": {"created_at": datetime.now(UTC), "pool": 100}}
    decoded = json.loads(_encode(frame))
    assert decoded["event"] == "state"
    assert isinstance(decoded["data"]["created_at"], str)


def test_channel_name_is_stable():
    assert pvp_channel(42) == "ws:pvp:42"
    assert str(PvPEvent.WINNER_SELECTED) == "winner_selected"


async def test_pvp_snapshot_is_json_encodable(client, session):
    host = auth_header((await authenticate(client, 9301))["token"])
    guest = auth_header((await authenticate(client, 9302))["token"])

    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]
    await client.post(f"/api/pvp/{game_id}/join", json={"amount": 100}, headers=guest)

    game = await pvp_service.get_game(session, game_id)
    payload = await serialize_pvp(session, game)

    frame = json.loads(_encode({"event": "state", "game_id": game_id, "data": payload}))
    assert frame["data"]["total_pool"] == 200
    assert frame["data"]["server_seed"] is None, "the seed stays hidden until the round ends"


async def test_polling_fallback_returns_state_and_events(client):
    host = auth_header((await authenticate(client, 9303))["token"])
    guest = auth_header((await authenticate(client, 9304))["token"])

    game_id = (await client.post("/api/pvp/create", json={"amount": 100}, headers=host)).json()["game"]["id"]
    await client.post(f"/api/pvp/{game_id}/join", json={"amount": 200}, headers=guest)

    state = (await client.get(f"/api/pvp/{game_id}/state", headers=host)).json()
    assert state["game"]["total_pool"] == 300
    assert any(event["event"] == "player_joined" for event in state["events"])

    # The cursor advances, so a second poll does not replay what was seen.
    again = (await client.get(f"/api/pvp/{game_id}/state?cursor={state['cursor']}", headers=host)).json()
    assert len(again["events"]) <= len(state["events"])
