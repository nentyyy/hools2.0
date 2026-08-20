# gg.gram

A Telegram Mini App and bot: PvP pot games, five solo modes, giveaways, an
internal GG currency topped up with Telegram Stars, and TON Connect for wallet
features.

```
frontend/   React 18 + TypeScript + Vite + Telegram Mini Apps SDK + TON Connect
backend/    FastAPI + SQLAlchemy 2 (async) + Alembic + PostgreSQL + Redis + WebSocket
bot/        aiogram 3 (polling or webhook)
shared/     enums, GG packages and TS types both sides import
database/   schema notes, init.sql, invariants
api/        Vercel serverless entry point for the backend
deploy/     deployment scripts and the Vercel env template
```

## The one rule everything follows

**The server decides; the client renders.** The frontend never computes a game
result, never adjusts a balance, and is never trusted with a user identity — it
may only forward the `initData` string Telegram signed. Every GG movement is a
row in an append-only ledger, written inside a database transaction while the
user row is locked.

---

## Setup, step by step

### 1. Install dependencies

```bash
git clone <this repo> && cd gg.gram

# backend (Python 3.11+)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pip install -e ../shared            # gg_shared: enums + GG price table
pip install -e ../bot               # only needed if the API serves the bot webhook
cd ..

# frontend (Node 20+)
cd frontend && npm install && cd ..
```

### 2. Create the PostgreSQL database

Locally:

```bash
createdb gg
psql -c "CREATE USER gg WITH PASSWORD 'gg'; GRANT ALL PRIVILEGES ON DATABASE gg TO gg;"
```

Or with Docker: `docker compose up -d postgres`.

Managed (Neon / Supabase / RDS) works too — take the connection string and set
`DB_STATEMENT_CACHE_SIZE=0` when connecting through a transaction-mode pooler.

### 3. Create Redis

```bash
docker compose up -d redis          # or: redis-server
```

Redis is not a cache here — it holds the distributed locks, idempotency records
and rate-limit counters, and fans websocket events out across workers. Upstash
(`rediss://…`) works for serverless.

### 4. Create the Telegram bot

In [@BotFather](https://t.me/BotFather):

1. `/newbot` → name → username → copy the **token**.
2. `/mybots` → your bot → *Bot Settings* → *Payments*: Telegram Stars needs no
   provider token, digital goods are billed in `XTR` directly.
3. Keep the token for step 5. Your own Telegram user id (ask
   [@userinfobot](https://t.me/userinfobot)) goes into `ADMIN_TELEGRAM_IDS`.

### 5. Add the .env

```bash
cp .env.example .env
```

Fill in at minimum:

| Variable | What it is |
| --- | --- |
| `BOT_TOKEN`, `BOT_USERNAME` | from BotFather |
| `WEBAPP_URL` | public HTTPS URL of the Mini App |
| `DATABASE_URL`, `REDIS_URL` | from steps 2 and 3 |
| `JWT_SECRET` | `openssl rand -hex 32` |
| `INTERNAL_API_TOKEN` | shared secret between bot and backend |
| `CRON_SECRET` | protects `/api/internal/tick` |
| `TELEGRAM_WEBHOOK_SECRET` | random string, only for webhook mode |
| `ADMIN_TELEGRAM_IDS` | comma-separated Telegram ids |

The frontend gets its own `frontend/.env` (`cp frontend/.env.example
frontend/.env`). Only `VITE_*` values reach the browser — never put a secret
there.

### 6. Run the migrations

```bash
cd backend
alembic upgrade head
```

### 7. Start the backend

```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

`http://localhost:8000/docs` lists every endpoint;
`http://localhost:8000/api/health` reports database and Redis status.

### 8. Start the frontend

```bash
cd frontend
npm run dev            # http://localhost:5173, proxies /api and /ws to :8000
```

### 9. Connect the Mini App in BotFather

The Mini App must be served over HTTPS. For local work use a tunnel
(`cloudflared tunnel --url http://localhost:5173` or `ngrok http 5173`), then:

1. `/newapp` in BotFather → pick the bot → title, description, 640×360 image.
2. Web App URL → your HTTPS URL. Put the same value in `WEBAPP_URL`.
3. Optional: `/setmenubutton` → *Open gg.gram* → the same URL.

### 10. Start the Telegram bot

```bash
cd bot
pip install -r requirements.txt && pip install -e . -e ../shared
python -m gg_bot                    # polling — best for local and VPS
```

Webhook mode (required on serverless, where nothing runs between requests):

```bash
cd bot && python set_webhook.py https://your-domain/api/telegram/webhook
python set_webhook.py --delete      # switch back to polling
```

Send `/start` to your bot; the button opens the Mini App, the Mini App signs you
in, and the welcome bonus lands in your balance.

---

## Everything at once with Docker

```bash
cp .env.example .env                # fill it in
docker compose up -d --build
docker compose exec backend alembic upgrade head
```

Postgres, Redis, the API (websockets + scheduler), the bot in polling mode and
an nginx-served frontend on `:5173`.

## Deploying to Vercel

Frontend, API and the bot webhook run from one project — `vercel.json` builds
`frontend/` and routes `/api/*` to `api/index.py`.

You need a managed PostgreSQL (Neon, Supabase) and Redis (Upstash) first —
Vercel provides neither.

```bash
npm i -g vercel && vercel login
vercel link                                     # pick or create the project

cp deploy/vercel-env.example .env.production    # fill it in (gitignored)
./deploy/set-vercel-env.sh .env.production      # push all variables at once
./deploy/deploy-vercel.sh --prod

cd backend && DATABASE_URL='<production url>' alembic upgrade head
cd ../bot && python set_webhook.py https://<deployment>/api/telegram/webhook
```

Then BotFather → `/newapp` → Web App URL = the deployment URL, and set the same
value as `WEBAPP_URL`.

Two consequences of serverless worth knowing:

* **No websockets.** The Mini App detects the failed upgrade and polls
  `/api/pvp/{id}/state`, which returns the same authoritative snapshot plus the
  events published since the last cursor.
* **No background loop.** Nothing here depends on one: a PvP round and a
  giveaway both carry their deadline in the database and are resolved by
  whichever request arrives after it — under a Redis lock, so exactly once.
  `/api/internal/tick` is only a backstop for a game nobody opens.

`vercel.json` schedules that backstop daily (`0 3 * * *`) because the Hobby plan
only allows daily crons; on Pro, change it to `* * * * *` for a tighter sweep.
`.vercelignore` keeps the local virtualenv and `node_modules` out of the upload.

For websockets and second-level timing, run the Docker stack on a VPS instead
(`./deploy/deploy-vps.sh user@host`) and point the Mini App at that domain.

---

## How the money works

### GG ledger

`Transaction` rows are append-only and carry `balance_before` / `balance_after`.
`app/services/ledger.py` is the only module that writes `users.balance`, and it:

1. locks the user row with `SELECT … FOR UPDATE` (`populate_existing`, so the
   locked row is genuinely re-read);
2. refuses a debit that would overdraw — with a `balance >= 0` CHECK constraint
   behind it;
3. writes the ledger row with an optional `idempotency_key` under a unique
   index, turning a duplicate request into a conflict rather than a double
   spend.

### Telegram Stars (XTR)

Digital goods inside a Mini App must be sold for Stars, so the top-up flow is:

```
POST /api/payments/stars/create   backend → createInvoiceLink (currency XTR)
Telegram shows the payment sheet  Mini App → WebApp.openInvoice(link)
pre_checkout_query                bot → /api/payments/stars/precheckout
successful_payment                bot → /api/payments/stars/webhook
                                  → GG credited, ledger row written
```

Nothing is credited before `successful_payment`. The credit is keyed on
`telegram_payment_charge_id`, so a redelivered update is a no-op.
`/paysupport` is implemented, and refunds go through Telegram's official
`refundStarPayment` (`POST /api/payments/stars/refund`, admin only, or
`/refund <payment_id>` in the bot), which also claws the GG back.

### TON

TON Connect links a wallet for on-chain features. The backend stores the public
address and the verified `ton_proof` only — no keys, no custody. Transfers are
confirmed against a public indexer, never against what the client claims. TON is
**not** used to sell digital goods inside the Mini App; that is what Stars are
for.

## Games

| Mode | Endpoint | Model |
| --- | --- | --- |
| PvP | `POST /api/pvp/create`, `/api/pvp/{id}/join` | pot game — your share of the pot is your chance; 5% rake |
| Plinko | `POST /api/solo/plinko/play` | binomial slots, multipliers normalised to the configured edge |
| Upgrade | `POST /api/solo/upgrade/play` | pick a target, win chance is `(1 − edge) / target` |
| Lucky Buy | `POST /api/solo/lucky-buy/play` | weighted case, drop lands in the inventory |
| Hi-Lo | `POST /api/solo/hilo/play` | 13-rank deck, exact per-guess odds, cash out any time |
| Ice Arena | `POST /api/solo/ice-arena/play` | round-based run, per-tile difficulty, full history |

Outcomes come from `HMAC-SHA256(server_seed, "client_seed:nonce:cursor")`. You
get the seed hash before playing (`GET /api/fair`) and the seed itself when it
rotates (`POST /api/fair/rotate`), so any past round can be recomputed.

## Realtime

`/ws/pvp/{game_id}?token=<jwt>` emits `player_joined`, `player_left`,
`balance_updated`, `game_started`, `countdown`, `wheel_started`,
`winner_selected` and `game_finished`. Events are published through Redis
pub/sub so every worker delivers them, and buffered briefly so the polling
fallback can catch up.

## Security

* Telegram `initData` HMAC-verified against the bot token, with a freshness
  window; the user is read from the *verified* payload only.
* JWT sessions after that handshake; the bot token never reaches the browser.
* Redis rate limits per user (and per IP before sign-in) on auth, play and
  general endpoints.
* `X-Idempotency-Key` on every mutating call; where a repeat cannot be
  intentional (joining, selling, paying) a body-derived key also collapses
  double taps.
* Redis locks plus row locks around PvP rounds and giveaway draws — resolution
  happens exactly once.
* Ownership checks everywhere; another player's game or item returns 404, not a
  hint that it exists.
* Admin routes need both a valid session and either the `is_admin` flag or
  membership of `ADMIN_TELEGRAM_IDS`.
* Internal routes (`/api/internal/*`) need the service token; the cron tick
  needs the cron secret. Both compared in constant time.
* Secrets live only in the environment. `.env` is gitignored.

## Tests

```bash
cd backend
DATABASE_URL=postgresql+asyncpg://gg:gg@localhost:5432/gg \
REDIS_URL=redis://localhost:6379/1 \
python -m pytest
```

The suite runs against a real Postgres and Redis, because what it checks —
locking, constraints, idempotency — cannot be exercised against a stub. It
covers signature forgery, referral double-payment, insufficient funds, payment
replay, refunds, giveaway double-entry, ban enforcement, and a concurrency
suite that fires parallel bets and joins and then walks the whole ledger to
prove no row is out of step with the balance.

## API surface

Auth & profile: `POST /api/auth/telegram`, `GET /api/me`, `/api/balance`,
`/api/profile`, `/api/transactions`, `/api/inventory`, `/api/inventory/{id}`,
`POST /api/inventory/{id}/sell`, `/api/referrals`, `/api/fair`.

PvP: `GET /api/pvp`, `POST /api/pvp/create`, `POST /api/pvp/{id}/join`,
`GET /api/pvp/{id}`, `GET /api/pvp/{id}/state`.

Solo: `GET /api/solo/config`, `/api/solo/active`, `/api/solo/history`, and
`POST /api/solo/{plinko|upgrade|lucky-buy|hilo|ice-arena}/play`.

Giveaways: `GET /api/giveaways`, `/api/giveaways/{id}`,
`POST /api/giveaways/{id}/join`, `GET /api/giveaways/{id}/participants`.

Payments: `GET /api/payments/packages`, `POST /api/payments/stars/create`,
`/stars/precheckout`, `/stars/webhook`, `/stars/refund`,
`GET /api/payments/history`, `/api/payments/support`.

TON: `GET /api/ton/wallet`, `POST /api/ton/connect`, `/api/ton/disconnect`,
`/api/ton/verify`, `GET /api/ton/transactions`.

Admin: `/api/admin/stats`, `/users`, `/users/{id}`, `/users/{id}/ban`,
`/users/{id}/unban`, `/users/{id}/balance`, `/transactions`, `/payments`,
`/giveaways` (create, patch, finish), `/pvp`, `/solo`.

System: `GET /api/health`, `GET|POST /api/internal/tick`,
`POST /api/telegram/webhook`.

## Licence

Private project. Configure your own bot, database and payment settings before
running it anywhere public.
