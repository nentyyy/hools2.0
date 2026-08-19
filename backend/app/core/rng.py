"""Provably fair randomness.

Outcomes come from HMAC-SHA256(server_seed, f"{client_seed}:{nonce}:{cursor}").
The player sees sha256(server_seed) up front and the plain server seed after it
is rotated, so every past round can be recomputed and checked. The frontend
still never learns a result before the backend has written it down.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

MAX_UINT32 = 2**32


def new_server_seed() -> tuple[str, str]:
    """Returns (server_seed, sha256_hash_of_seed)."""
    seed = secrets.token_hex(32)
    return seed, hashlib.sha256(seed.encode()).hexdigest()


def new_client_seed() -> str:
    return secrets.token_hex(8)


def hash_seed(server_seed: str) -> str:
    return hashlib.sha256(server_seed.encode()).hexdigest()


def _digest(server_seed: str, client_seed: str, nonce: int, cursor: int) -> bytes:
    message = f"{client_seed}:{nonce}:{cursor}".encode()
    return hmac.new(server_seed.encode(), message, hashlib.sha256).digest()


def floats(server_seed: str, client_seed: str, nonce: int, count: int) -> list[float]:
    """`count` uniformly distributed floats in [0, 1)."""
    out: list[float] = []
    cursor = 0
    while len(out) < count:
        digest = _digest(server_seed, client_seed, nonce, cursor)
        for i in range(0, 32, 4):
            if len(out) >= count:
                break
            out.append(int.from_bytes(digest[i : i + 4], "big") / MAX_UINT32)
        cursor += 1
    return out


def single_float(server_seed: str, client_seed: str, nonce: int) -> float:
    return floats(server_seed, client_seed, nonce, 1)[0]


def weighted_pick(values: list[float], weights: list[float], roll: float) -> int:
    """Index of the bucket `roll` (in [0,1)) falls into for the given weights."""
    total = sum(weights)
    if total <= 0:
        raise ValueError("weights must sum to a positive number")
    threshold = roll * total
    acc = 0.0
    for index, weight in enumerate(weights):
        acc += weight
        if threshold < acc:
            return index
    return len(weights) - 1
