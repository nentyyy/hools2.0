from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, PrimaryKeyMixin, TimestampMixin


class GameSeed(Base, PrimaryKeyMixin, TimestampMixin):
    """Active provably-fair seed pair for a user.

    `nonce` is bumped once per resolved round under a row lock, which also
    doubles as the per-user serialisation point for solo play.
    """

    __tablename__ = "game_seeds"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    server_seed: Mapped[str] = mapped_column(String(128), nullable=False)
    server_seed_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    client_seed: Mapped[str] = mapped_column(String(64), nullable=False)
    nonce: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    previous_server_seed: Mapped[str | None] = mapped_column(String(128))
    previous_server_seed_hash: Mapped[str | None] = mapped_column(String(64))
