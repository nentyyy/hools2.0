#!/usr/bin/env bash
# Deploy the whole app (Mini App + API + bot webhook) to Vercel.
#
#   ./deploy/deploy-vercel.sh                 # preview deployment
#   ./deploy/deploy-vercel.sh --prod          # production deployment
#
# Prerequisites: `npm i -g vercel`, `vercel login`, and the environment
# variables from deploy/vercel-env.example set in the project.

set -euo pipefail

cd "$(dirname "$0")/.."

if ! command -v vercel >/dev/null 2>&1; then
  echo "vercel CLI not found. Install it with: npm i -g vercel" >&2
  exit 1
fi

TARGET=${1:-}

echo "==> Type-checking and building the frontend"
(cd frontend && npm install --no-audit --no-fund && npm run build)

echo "==> Deploying to Vercel"
if [[ "$TARGET" == "--prod" ]]; then
  vercel deploy --prod
else
  vercel deploy
fi

cat <<'NEXT'

Deployed. Two things must still point at the new URL:

  1. Telegram webhook:
       cd bot && python set_webhook.py https://<deployment>/api/telegram/webhook
  2. BotFather → /newapp (or /myapps) → Mini App URL → https://<deployment>

Database migrations are not run by this script. Apply them against the managed
database from your machine:

       cd backend && DATABASE_URL='<production url>' alembic upgrade head
NEXT
