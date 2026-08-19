"""HI-LO — guess whether the next card beats the current one.

Each correct guess multiplies the running payout by `(1 - edge) / p(guess)`,
where p is the exact probability of that guess on a 13-rank deck drawn with
replacement. Cash out at any point; one wrong guess ends the run.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, ValidationError
from app.models import SoloGame, User
from app.services.seeds import get_or_create_seed
from app.services.solo import engine
from gg_shared import SoloGameType, SoloStatus

RANKS = 13
MAX_ROUNDS = 12
CHOICES = ("higher", "lower", "same")
RANK_NAMES = {1: "A", 11: "J", 12: "Q", 13: "K"}
SUITS = ("spades", "hearts", "diamonds", "clubs")


def rank_label(rank: int) -> str:
    return RANK_NAMES.get(rank, str(rank))


def probability(card: int, choice: str) -> float:
    """`higher`/`lower` include a tie, matching how the odds are displayed."""
    if choice == "higher":
        return (RANKS - card + 1) / RANKS
    if choice == "lower":
        return card / RANKS
    if choice == "same":
        return 1 / RANKS
    raise ValidationError(f"choice must be one of {list(CHOICES)}")


def step_multiplier(card: int, choice: str) -> float:
    p = probability(card, choice)
    if p <= 0:
        raise ValidationError("This guess cannot win on the current card")
    return round(engine.payout_factor() / p, 4)


def outcome(card: int, next_card: int, choice: str) -> bool:
    if choice == "higher":
        return next_card >= card
    if choice == "lower":
        return next_card <= card
    return next_card == card


def _draw(roll: float) -> int:
    return min(int(roll * RANKS) + 1, RANKS)


def odds_for(card: int) -> dict:
    return {
        choice: {
            "chance": round(probability(card, choice), 6),
            "multiplier": step_multiplier(card, choice),
        }
        for choice in CHOICES
    }


def public_state(game: SoloGame) -> dict:
    state = dict(game.state or {})
    card = int(state.get("card", 1))
    return {
        "game_id": game.id,
        "status": game.status,
        "bet": int(game.bet),
        "card": card,
        "card_label": rank_label(card),
        "suit": state.get("suit"),
        "round": int(state.get("round", 0)),
        "multiplier": round(float(state.get("multiplier", 1.0)), 4),
        "potential_reward": round(int(game.bet) * float(state.get("multiplier", 1.0))),
        "history": state.get("history", []),
        "odds": odds_for(card),
        "max_rounds": MAX_ROUNDS,
        "server_seed_hash": game.server_seed_hash,
        "client_seed": game.client_seed,
        "nonce": game.nonce,
    }


async def start(
    session: AsyncSession, user_id: int, *, bet: int, idempotency_key: str | None = None
) -> tuple[User, SoloGame]:
    if await engine.find_active(session, user_id, SoloGameType.HI_LO):
        raise ConflictError("Finish or cash out your current Hi-Lo round first")

    user, game, seed = await engine.begin(
        session, user_id, SoloGameType.HI_LO, bet, idempotency_key=idempotency_key
    )
    roll = engine.round_rolls(seed.server_seed, game, 0, 2)
    card = _draw(roll[0])
    game.state = {
        "card": card,
        "suit": SUITS[int(roll[1] * len(SUITS)) % len(SUITS)],
        "round": 0,
        "multiplier": 1.0,
        "history": [],
    }
    await session.flush()
    return user, game


async def guess(
    session: AsyncSession,
    user_id: int,
    *,
    game_id: int,
    choice: str,
    idempotency_key: str | None = None,
) -> tuple[User, SoloGame]:
    if choice not in CHOICES:
        raise ValidationError(f"choice must be one of {list(CHOICES)}")

    game = await engine.load_active(session, user_id, game_id, SoloGameType.HI_LO)
    seed = await get_or_create_seed(session, user_id)
    state = dict(game.state or {})
    round_index = int(state.get("round", 0)) + 1
    if round_index > MAX_ROUNDS:
        raise ConflictError("Round limit reached — cash out")

    card = int(state["card"])
    rolls = engine.round_rolls(seed.server_seed, game, round_index, 2)
    next_card = _draw(rolls[0])
    suit = SUITS[int(rolls[1] * len(SUITS)) % len(SUITS)]

    survived = outcome(card, next_card, choice)
    step = step_multiplier(card, choice)
    multiplier = round(float(state.get("multiplier", 1.0)) * step, 4) if survived else 0.0

    history = list(state.get("history", []))
    history.append(
        {
            "round": round_index,
            "card": card,
            "next_card": next_card,
            "choice": choice,
            "won": survived,
            "step": step,
        }
    )

    await engine.add_round(
        session,
        game,
        round_number=round_index,
        difficulty=choice,
        success_chance=probability(card, choice),
        possible_reward=round(int(game.bet) * multiplier) if survived else 0,
        roll=round(rolls[0], 6),
        survived=survived,
        payload={"card": card, "next_card": next_card, "suit": suit},
    )

    user = await engine.lock_user_for(session, user_id)

    if not survived:
        game.state = {**state, "round": round_index, "history": history, "card": next_card, "suit": suit}
        await engine.finish(
            session,
            user,
            game,
            reward=0,
            multiplier=0.0,
            result={"reason": "wrong_guess", "history": history, "final_card": next_card},
            status=SoloStatus.LOST,
            reveal_seed=seed.server_seed,
        )
        return user, game

    game.state = {
        "card": next_card,
        "suit": suit,
        "round": round_index,
        "multiplier": multiplier,
        "history": history,
    }
    await session.flush()

    if round_index >= MAX_ROUNDS:
        await _cash_out(session, user, game, seed.server_seed)
    return user, game


async def cash_out(
    session: AsyncSession, user_id: int, *, game_id: int
) -> tuple[User, SoloGame]:
    game = await engine.load_active(session, user_id, game_id, SoloGameType.HI_LO)
    seed = await get_or_create_seed(session, user_id)
    user = await engine.lock_user_for(session, user_id)
    await _cash_out(session, user, game, seed.server_seed)
    return user, game


async def _cash_out(session: AsyncSession, user: User, game: SoloGame, server_seed: str) -> None:
    state = dict(game.state or {})
    multiplier = float(state.get("multiplier", 1.0))
    if int(state.get("round", 0)) == 0:
        raise ConflictError("Make at least one guess before cashing out")

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
