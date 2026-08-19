"""Single player game modes.

Every mode follows the same skeleton, implemented once in `engine.py`:

    lock the seed row -> lock the user row -> debit the bet -> compute the
    outcome from the provably-fair stream -> persist it -> credit any win

The client sends a bet and (for round based modes) an action; it never sends,
and is never asked for, a result.
"""

from app.services.solo import hilo, ice_arena, lucky_buy, plinko, upgrade

__all__ = ["hilo", "ice_arena", "lucky_buy", "plinko", "upgrade"]
