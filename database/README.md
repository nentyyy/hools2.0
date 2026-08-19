# database

PostgreSQL 16 is the source of truth for balances, games and payments.

## Schema

Owned by Alembic, in `backend/alembic/versions/`. Never edit tables by hand:

```bash
cd backend
alembic upgrade head            # apply
alembic revision --autogenerate -m "what changed"
alembic downgrade -1            # roll back one step
```

## Invariants enforced by the database

These are constraints, not conventions — application bugs cannot get around them:

| Constraint | Table | What it prevents |
| --- | --- | --- |
| `balance >= 0` | `users` | a negative balance from any code path |
| `balance_after = balance_before + amount` | `transactions` | a ledger row that does not add up |
| `balance_after >= 0` | `transactions` | recording an overdraft |
| unique `idempotency_key` | `transactions` | the same operation being paid twice |
| unique `(giveaway_id, user_id)` | `giveaway_participants` | two entries in one giveaway |
| unique `(game_id, user_id)` | `pvp_players` | two seats in one round |
| unique `payload`, unique `telegram_payment_charge_id` | `star_payments` | crediting a replayed payment twice |
| unique `(referrer_id, referred_id, kind)` | `referral_bonuses` | paying a referral bonus twice |
| unique `boc_hash` | `ton_transactions` | verifying the same transfer twice |

## Concurrency model

* `SELECT ... FOR UPDATE` on the user row before every balance change, always
  loaded with `populate_existing` so the locked row is re-read rather than
  served from the session's identity map.
* Redis locks around multi-row state machines (PvP rounds, giveaway draws).
* Lock ordering is always game → user, which keeps deadlocks out.

## Backups

```bash
docker compose exec postgres pg_dump -U gg gg | gzip > backup-$(date +%F).sql.gz
gunzip -c backup-2026-01-01.sql.gz | docker compose exec -T postgres psql -U gg gg
```
