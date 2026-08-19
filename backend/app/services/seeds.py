"""Provably fair seed management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import rng
from app.models import GameSeed


async def get_or_create_seed(session: AsyncSession, user_id: int, *, lock: bool = False) -> GameSeed:
    stmt = select(GameSeed).where(GameSeed.user_id == user_id)
    if lock:
        # Locking the seed row serialises all solo rounds for this user, which
        # is what stops two parallel /play calls from sharing a nonce.
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    seed = (await session.execute(stmt)).scalar_one_or_none()
    if seed is not None:
        return seed

    server_seed, server_hash = rng.new_server_seed()
    seed = GameSeed(
        user_id=user_id,
        server_seed=server_seed,
        server_seed_hash=server_hash,
        client_seed=rng.new_client_seed(),
        nonce=0,
    )
    session.add(seed)
    await session.flush()
    return seed


async def next_nonce(session: AsyncSession, user_id: int) -> GameSeed:
    """Lock the user's seed row and consume one nonce."""
    seed = await get_or_create_seed(session, user_id, lock=True)
    seed.nonce += 1
    return seed


async def rotate_seed(session: AsyncSession, user_id: int, client_seed: str | None = None) -> GameSeed:
    """Reveal the current server seed and issue a fresh pair."""
    seed = await get_or_create_seed(session, user_id, lock=True)
    seed.previous_server_seed = seed.server_seed
    seed.previous_server_seed_hash = seed.server_seed_hash
    server_seed, server_hash = rng.new_server_seed()
    seed.server_seed = server_seed
    seed.server_seed_hash = server_hash
    seed.client_seed = (client_seed or rng.new_client_seed())[:64]
    seed.nonce = 0
    await session.flush()
    return seed
