"""ICE ARENA — walk across a frozen arena one tile at a time.

Each round you choose a difficulty; the harder the tile, the lower the survival
chance and the bigger the step multiplier. Step multiplier is
`(1 - edge) / p(survive)`, so pushing further never changes the expected return,
only the risk. Cash out any time; one crack and the run is over.

Every round is written to `solo_rounds`, giving a full replayable history.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ValidationError
from app.models import SoloGame, User
from app.services.seeds import get_or_create_seed
from app.services.solo import engine
from gg_shared import SoloGameType, SoloStatus

MAX_ROUNDS = 12

DIFFICULTIES: dict[str, float] = {
    "easy": 0.90,
    "normal": 0.75,
    "hard": 0.55,
    "extreme": 0.35,
}


def validate_difficulty(difficulty: str) -> str:
    if difficulty not in DIFFICULTIES:
        raise ValidationError(f"difficulty must be one of {list(DIFFICULTIES)}")
    return difficulty


def step_multiplier(difficulty: str) -> float:
    return round(engine.payout_factor() / DIFFICULTIES[validate_difficulty(difficulty)], 4)


def difficulty_table(bet: int, multiplier: float) -> list[dict]:
    return [
        {
            "difficulty": name,
            "chance": chance,
            "step": step_multiplier(name),
            "reward": round(bet * multiplier * step_multiplier(name)),
        }
        for name, chance in DIFFICULTIES.items()
    ]


def public_state(game: SoloGame) -> dict:
    state = dict(game.state or {})
    multiplier = float(state.get("multiplier", 1.0))
    return {
        "game_id": game.id,
        "status": game.status,
        "bet": int(game.bet),
        "round": int(state.get("round", 0)),
        "max_rounds": MAX_ROUNDS,
        "multiplier": round(multiplier, 4),
        "potential_reward": round(int(game.bet) * multiplier),
        "history": state.get("history", []),
        "options": difficulty_table(int(game.bet), multiplier),
        "server_seed_hash": game.server_seed_hash,
        "client_seed": game.client_seed,
        "nonce": game.nonce,
    }


async def start(
    session: AsyncSession, user_id: int, *, bet: int, idempotency_key: str | None = None
) -> tuple[User, SoloGame]:
    if await engine.find_active(session, user_id, SoloGameType.ICE_ARENA):
        raise ConflictError("You already have a run in progress")

    user, game, _seed = await engine.begin(
        session, user_id, SoloGameType.ICE_ARENA, bet, idempotency_key=idempotency_key
    )
    game.state = {"round": 0, "multiplier": 1.0, "history": []}
    await session.flush()
    return user, game


async def advance(
    session: AsyncSession,
    user_id: int,
    *,
    game_id: int,
    difficulty: str,
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame]:
    """Step onto the next tile."""
    validate_difficulty(difficulty)

    game = await engine.load_active(session, user_id, game_id, SoloGameType.ICE_ARENA)
    seed = await get_or_create_seed(session, user_id)
    state = dict(game.state or {})

    round_index = int(state.get("round", 0)) + 1
    if round_index > MAX_ROUNDS:
        raise ConflictError("You reached the far side — cash out")

    chance = DIFFICULTIES[difficulty]
    step = step_multiplier(difficulty)
    multiplier = round(float(state.get("multiplier", 1.0)) * step, 4)
    possible_reward = round(int(game.bet) * multiplier)

    roll = engine.round_rolls(seed.server_seed, game, round_index, 1)[0]
    survived = roll < chance

    history = list(state.get("history", []))
    history.append(
        {
            "round": round_index,
            "difficulty": difficulty,
            "chance": chance,
            "step": step,
            "survived": survived,
            "reward": possible_reward if survived else 0,
        }
    )

    await engine.add_round(
        session,
        game,
        round_number=round_index,
        difficulty=difficulty,
        success_chance=chance,
        possible_reward=possible_reward if survived else 0,
        roll=round(roll, 6),
        survived=survived,
    )

    user = await engine.lock_user_for(session, user_id)

    if not survived:
        game.state = {**state, "round": round_index, "history": history}
        await engine.finish(
            session,
            user,
            game,
            reward=0,
            multiplier=0.0,
            result={"reason": "fell_through", "round": round_index, "history": history},
            status=SoloStatus.LOST,
            reveal_seed=seed.server_seed,
        )
        return user, game

    game.state = {"round": round_index, "multiplier": multiplier, "history": history}
    await session.flush()

    if round_index >= MAX_ROUNDS:
        await _cash_out(session, user, game, seed.server_seed)
    return user, game


async def cash_out(session: AsyncSession, user_id: int, *, game_id: int) -> tuple[User, SoloGame]:
    game = await engine.load_active(session, user_id, game_id, SoloGameType.ICE_ARENA)
    seed = await get_or_create_seed(session, user_id)
    user = await engine.lock_user_for(session, user_id)
    await _cash_out(session, user, game, seed.server_seed)
    return user, game


async def _cash_out(session: AsyncSession, user: User, game: SoloGame, server_seed: str) -> None:
    state = dict(game.state or {})
    if int(state.get("round", 0)) == 0:
        raise ConflictError("Cross at least one tile before cashing out")
    multiplier = float(state.get("multiplier", 1.0))
    await engine.finish(
        session,
        user,
        game,
        reward=round(int(game.bet) * multiplier),
        multiplier=multiplier,
        result={"reason": "cash_out", "history": state.get("history", [])},
        status=SoloStatus.CASHED_OUT,
        reveal_seed=server_seed,
    )
