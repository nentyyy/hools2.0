"""XP and level curve.

Level N needs 100 * N * (N + 1) / 2 XP in total, i.e. every level costs 100 XP
more than the one before it.
"""

from __future__ import annotations

from app.models import User

XP_STEP = 100


def total_xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    n = level - 1
    return XP_STEP * n * (n + 1) // 2


def level_for_xp(xp: int) -> int:
    level = 1
    while total_xp_for_level(level + 1) <= xp:
        level += 1
    return level


def level_progress(xp: int) -> dict:
    level = level_for_xp(xp)
    current = total_xp_for_level(level)
    nxt = total_xp_for_level(level + 1)
    span = max(nxt - current, 1)
    return {
        "level": level,
        "xp": xp,
        "xp_current_level": current,
        "xp_next_level": nxt,
        "xp_into_level": xp - current,
        "xp_needed": nxt - xp,
        "progress": round(min((xp - current) / span, 1.0), 4),
    }


def grant_xp(user: User, amount: int) -> int:
    """Add XP to a user and recompute their level. Returns levels gained."""
    if amount <= 0:
        return 0
    before = user.level
    user.xp = int(user.xp) + int(amount)
    user.level = level_for_xp(user.xp)
    return max(user.level - before, 0)


def xp_for_wager(amount: int) -> int:
    """1 XP per 10 GG wagered, always at least 1 for a real bet."""
    return max(int(amount) // 10, 1 if amount > 0 else 0)
