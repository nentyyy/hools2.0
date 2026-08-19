#!/usr/bin/env bash
# Deploy the full stack to a server over SSH using docker compose.
#
#   ./deploy/deploy-vps.sh user@host [/remote/path]
#
# Copies the repository (excluding local artefacts and .env), then builds and
# starts the stack and applies migrations. The remote .env is left untouched —
# create it once from .env.example on the server.

set -euo pipefail

REMOTE=${1:?"usage: deploy-vps.sh user@host [/remote/path]"}
REMOTE_PATH=${2:-/opt/gg-gram}

cd "$(dirname "$0")/.."

echo "==> Syncing sources to ${REMOTE}:${REMOTE_PATH}"
ssh "$REMOTE" "mkdir -p ${REMOTE_PATH}"
rsync -az --delete \
  --exclude '.git' \
  --exclude '.env' \
  --exclude 'node_modules' \
  --exclude '.venv' \
  --exclude 'dist' \
  --exclude '__pycache__' \
  ./ "${REMOTE}:${REMOTE_PATH}/"

echo "==> Building and starting containers"
ssh "$REMOTE" "cd ${REMOTE_PATH} && \
  test -f .env || { echo 'Create .env on the server from .env.example first'; exit 1; } && \
  docker compose up -d --build && \
  docker compose exec -T backend alembic upgrade head && \
  docker compose ps"

echo "==> Done. Logs: ssh ${REMOTE} 'cd ${REMOTE_PATH} && docker compose logs -f --tail=100'"
