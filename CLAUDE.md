# gg.gram — working notes

Context for anyone (or any session) picking this up. The README covers setup and
the API surface; this file covers how the thing is put together, what must stay
true, and where it currently stands.

- **Repo:** `nentyyy/hools2.0` · default branch `claude/telegram-bot-mini-app-lmuuyf`
- **Production:** https://hools2-0.vercel.app — Mini App, API and the bot webhook
  all served from one Vercel project
- **Bot:** @GGggrambot · admin access is granted by `ADMIN_TELEGRAM_IDS`

## The rule everything follows

**The server decides; the client renders.** The frontend never computes a game
result, never adjusts a balance, and is never trusted with an identity — it may
only forward the `initData` string Telegram signed. Every GG movement is a row in
an append-only ledger written inside a database transaction while the user row is
locked.

If a change would let the client influence an outcome, it is the wrong change.

## Layout

```
frontend/   React 18 + TypeScript + Vite + Telegram Mini Apps SDK + TON Connect
backend/    FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis, WebSocket
bot/        aiogram 3 — webhook (serverless) or polling (docker/VPS)
shared/     enums, GG packages, gift catalogue, TS types both sides import
api/        Vercel entry point: adds backend/shared/bot to sys.path, exports `app`
database/   schema notes and the invariants the database enforces
deploy/     deployment scripts and the Vercel env template
```

## Invariants worth protecting

* `app/services/ledger.py` is the **only** module that writes `users.balance`. It
  locks the user row with `SELECT … FOR UPDATE` — always with
  `populate_existing`, or SQLAlchemy hands back the identity-mapped copy with the
  pre-lock balance and two concurrent bets read the same stale value.
* Money-shaped operations carry an idempotency key. The unique index on
  `transactions.idempotency_key` is what actually prevents a double spend; the
  Redis cache in front of it is a convenience and fails open.
* Redis locks guarantee exactly-once settlement (PvP rounds, giveaway draws) and
  fail **closed**. Rate limiting and the idempotency cache fail **open** — they
  must not take the API down with them.
* Lock ordering is always game → user. Keep it that way.
* Outcomes come from `HMAC-SHA256(server_seed, "client_seed:nonce:cursor")`. The
  seed hash is public before a round; the seed itself only after it rotates.

## Things that are easy to get wrong here

* **PvP rounds are time-driven, not task-driven.** A round carries `spin_at`;
  `ensure_progress()` advances it on any request, websocket frame or cron tick,
  under a lock. This is what makes it work on serverless. Do not add a background
  loop it depends on.
* **The draw is published when the spin starts**, not when it settles — joins are
  closed by then and the seed already fixed the outcome. Without that the client
  learns the result after the animation window has passed and the wheel snaps.
  Settlement recomputes the same number from the same seed.
* **Wheel and ice are separate games** (`pvp_games.mode`). Bets never cross;
  matchmaking is locked per mode.
* **No websockets on Vercel.** The client detects the failed upgrade and polls
  `/api/pvp/{id}/state`, which returns the same authoritative snapshot plus
  buffered events. The Hobby plan also caps cron at once a day, so nothing may
  depend on the tick — giveaways resolve on read, rounds resolve on any request.
* **The bot shares the process with the backend** in webhook mode, so
  `gg_bot.api` talks to FastAPI through an ASGI transport rather than HTTP.
  A separate bot process falls back to `BACKEND_URL`.
* **Telegram refuses a non-HTTPS Mini App button.** `keyboards.app_button()`
  degrades to a plain link rather than letting the Bot API reject the keyboard.
* **pydantic-settings JSON-parses list fields before validators run.** Both
  configs mark the CSV-style settings `NoDecode` and parse the three documented
  forms themselves. This bug took the bot down once already.

## Commands

```bash
# backend
cd backend && python -m pytest          # needs a live Postgres and Redis
ruff check app tests ../bot/gg_bot
alembic revision --autogenerate -m "..." && alembic upgrade head

# frontend
cd frontend && npx tsc --noEmit && npm run build

# everything, locally
docker compose up -d --build && docker compose exec backend alembic upgrade head
```

The test suite runs against real stores on purpose: it covers locking,
constraints and idempotency, none of which a stub would exercise. `test_concurrency.py`
fires parallel bets and joins and then walks the whole ledger to prove no row is
out of step with the balance — keep it passing.

## Operating the deployment

* `/api/health` is the first thing to open when something misbehaves. It reports
  Postgres, Redis, the applied migration against the head this build ships, and
  which required settings are still empty (names only, never values).
* `/api/internal/setup?token=<CRON_SECRET>` applies migrations, points Telegram's
  webhook at the deployment and registers the bot's commands. Idempotent. It also
  accepts `&browser_login=true|false` for guest play.
* A `schema_outdated` error means the code is ahead of the database — run setup.
* Secrets live only in Vercel's environment. Values that appeared in git history
  (commit `7cf87ba`, public repo) should be replaced; `JWT_SECRET` in particular
  would let anyone sign a session as any user.

## Where it stands

Done: auth, ledger, Stars payments with refunds, PvP (both modes, replays),
solo modes, shop and Lucky Buy, giveaways, inventory, referrals, admin API and
an in-app admin panel, TON Connect, guest play, the black-and-beige design pass.
91 tests, ruff clean.

Open:

* migration `0002_pvp_modes` still needs applying in production (run setup)
* grant 1,000,000 GG to `bless` and `bastilov` — Profile → Admin panel
* `TON_RECEIVER_ADDRESS` is unset, so on-chain verification has no destination
* Stars payments have not been exercised with a real purchase yet
* the single-player Ice Run endpoints still exist but are no longer linked from
  the UI, which moved Ice Arena to PvP
