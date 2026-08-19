"""The GG ledger — the only place in the codebase that mutates `users.balance`.

Rules enforced here:

* the user row is locked with `SELECT ... FOR UPDATE` before it is read, so two
  concurrent bets can never both see the same pre-bet balance;
* every change writes a Transaction row with before/after snapshots;
* debits are refused when funds are insufficient, and a CHECK constraint backs
  that up in the database;
* an optional idempotency key is stored on the transaction under a unique index,
  turning a duplicated request into a conflict instead of a double spend.

Callers must already be inside a database transaction and must commit it.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ConflictError, InsufficientFundsError, NotFoundError
from app.models import Transaction, User
from app.services.leveling import grant_xp
from gg_shared import TransactionType

logger = logging.getLogger(__name__)

# Types that count towards "total earned" on the profile.
EARNING_TYPES = {
    TransactionType.PVP_WIN,
    TransactionType.SOLO_WIN,
    TransactionType.GIVEAWAY_REWARD,
    TransactionType.REFERRAL_BONUS,
}


async def lock_user(session: AsyncSession, user_id: int) -> User:
    """Fetch a user row with a write lock held until the transaction ends.

    `populate_existing` is essential: without it SQLAlchemy would return the
    copy already in the identity map — with the balance it had *before* the lock
    was taken — and two concurrent bets would both read the same stale value.
    """
    result = await session.execute(select(User)
        .where(User.id == user_id)
        .with_for_update()
        .execution_options(populate_existing=True))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    return user


async def apply_change(
    session: AsyncSession,
    user: User,
    *,
    amount: int,
    tx_type: TransactionType | str,
    reference_id: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
    extra: dict | None = None,
    xp: int = 0,
) -> Transaction:
    """Apply a signed `amount` to a *locked* user row and record it.

    Positive amounts credit, negative amounts debit. Returns the ledger row.
    """
    amount = int(amount)
    balance_before = int(user.balance)
    balance_after = balance_before + amount

    if amount < 0 and balance_after < 0:
        raise InsufficientFundsError(
            "Not enough GG for this operation",
            details={"balance": balance_before, "required": -amount},
        )

    user.balance = balance_after
    if amount < 0:
        user.total_wagered += -amount
    tx_type_value = TransactionType(tx_type) if not isinstance(tx_type, TransactionType) else tx_type
    if amount > 0 and tx_type_value in EARNING_TYPES:
        user.total_earned += amount
    if xp:
        grant_xp(user, xp)

    transaction = Transaction(
        user_id=user.id,
        type=tx_type_value.value,
        amount=amount,
        balance_before=balance_before,
        balance_after=balance_after,
        reference_id=reference_id,
        description=description,
        idempotency_key=idempotency_key,
        extra=extra,
    )
    try:
        # A SAVEPOINT keeps a duplicate idempotency key from poisoning the
        # surrounding transaction: only this insert is rolled back.
        async with session.begin_nested():
            session.add(transaction)
    except IntegrityError as exc:
        user.balance = balance_before
        logger.warning(
            "ledger conflict user=%s type=%s key=%s", user.id, tx_type_value, idempotency_key
        )
        raise ConflictError("This operation was already processed") from exc

    logger.info(
        "ledger_change",
        extra={
            "user_id": user.id,
            "tx_type": tx_type_value.value,
            "amount": amount,
            "balance_after": balance_after,
            "reference_id": reference_id,
        },
    )
    return transaction


async def debit(
    session: AsyncSession,
    user: User,
    amount: int,
    *,
    tx_type: TransactionType,
    reference_id: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
    extra: dict | None = None,
) -> Transaction:
    if amount <= 0:
        raise ValueError("debit amount must be positive")
    return await apply_change(
        session,
        user,
        amount=-amount,
        tx_type=tx_type,
        reference_id=reference_id,
        description=description,
        idempotency_key=idempotency_key,
        extra=extra,
    )


async def credit(
    session: AsyncSession,
    user: User,
    amount: int,
    *,
    tx_type: TransactionType,
    reference_id: str | None = None,
    description: str | None = None,
    idempotency_key: str | None = None,
    extra: dict | None = None,
    xp: int = 0,
) -> Transaction:
    if amount <= 0:
        raise ValueError("credit amount must be positive")
    return await apply_change(
        session,
        user,
        amount=amount,
        tx_type=tx_type,
        reference_id=reference_id,
        description=description,
        idempotency_key=idempotency_key,
        extra=extra,
        xp=xp,
    )
