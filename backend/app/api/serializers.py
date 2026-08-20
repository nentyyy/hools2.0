"""Model -> API payload helpers shared by several routers."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models import Giveaway, PvPGame, User
from gg_shared import PvPStatus


async def serialize_pvp(session: AsyncSession, game: PvPGame) -> dict:
    players = list(game.players or [])
    user_ids = [p.user_id for p in players]
    users: dict[int, User] = {}
    if user_ids:
        rows = (await session.execute(select(User).where(User.id.in_(user_ids)))).scalars().all()
        users = {u.id: u for u in rows}

    finished = game.status == PvPStatus.FINISHED.value
    return {
        "id": game.id,
        "status": game.status,
        "mode": game.mode,
        "total_pool": int(game.total_pool),
        "prize": int(game.prize),
        "rake": int(game.rake),
        "min_bet": int(game.min_bet),
        "max_players": int(game.max_players),
        "creator_id": game.creator_id,
        "winner_id": game.winner_id,
        "players": [
            {
                "user_id": p.user_id,
                "name": users[p.user_id].display_name if p.user_id in users else f"Player #{p.user_id}",
                "username": users[p.user_id].username if p.user_id in users else None,
                "avatar": users[p.user_id].avatar if p.user_id in users else None,
                "amount": int(p.amount),
                "chance": float(p.chance),
                "ticket_from": int(p.ticket_from),
                "ticket_to": int(p.ticket_to),
                "is_winner": bool(p.is_winner),
            }
            for p in players
        ],
        "created_at": game.created_at,
        "started_at": game.started_at,
        "spin_at": game.spin_at,
        "finished_at": game.finished_at,
        "server_seed_hash": game.server_seed_hash,
        # The seed is revealed only once the round can no longer be influenced.
        "server_seed": game.server_seed if finished else None,
        "client_seed": game.client_seed,
        "nonce": int(game.nonce),
        "winning_roll": game.winning_roll,
        "countdown_seconds": settings.pvp_countdown_seconds,
        "spin_seconds": settings.pvp_spin_seconds,
        "server_time": datetime.now(UTC),
    }


def serialize_giveaway(giveaway: Giveaway, *, joined: bool = False, winner: User | None = None) -> dict:
    return {
        "id": giveaway.id,
        "title": giveaway.title,
        "description": giveaway.description,
        "image": giveaway.image,
        "prize_type": giveaway.prize_type,
        "prize_value": int(giveaway.prize_value),
        "prize_payload": giveaway.prize_payload,
        "entry_cost": int(giveaway.entry_cost),
        "min_level": int(giveaway.min_level),
        "max_participants": giveaway.max_participants,
        "participants_count": int(giveaway.participants_count),
        "start_at": giveaway.start_at,
        "end_at": giveaway.end_at,
        "status": giveaway.status,
        "winner_id": giveaway.winner_id,
        "finished_at": giveaway.finished_at,
        "created_at": giveaway.created_at,
        "joined": joined,
        "winner": (
            {
                "id": winner.id,
                "name": winner.display_name,
                "username": winner.username,
                "avatar": winner.avatar,
            }
            if winner
            else None
        ),
    }
