#!/usr/bin/env bash
# Push environment variables from a local file into a Vercel project.
#
#   ./deploy/set-vercel-env.sh .env.production            # -> production
#   ./deploy/set-vercel-env.sh .env.production preview    # -> preview
#
# Existing values are replaced. The file is never uploaded anywhere but Vercel's
# encrypted environment store, and it must stay out of git (.env* is ignored).

set -euo pipefail

ENV_FILE=${1:?"usage: set-vercel-env.sh <env-file> [production|preview|development]"}
TARGET=${2:-production}

cd "$(dirname "$0")/.."

if ! command -v vercel >/dev/null 2>&1; then
  echo "vercel CLI not found. Install it with: npm i -g vercel" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "No such file: $ENV_FILE" >&2
  exit 1
fi

REQUIRED=(BOT_TOKEN BOT_USERNAME WEBAPP_URL DATABASE_URL REDIS_URL JWT_SECRET INTERNAL_API_TOKEN CRON_SECRET)
missing=()
for name in "${REQUIRED[@]}"; do
  grep -qE "^${name}=.+" "$ENV_FILE" || missing+=("$name")
done
if (( ${#missing[@]} )); then
  echo "These required variables are empty or absent in ${ENV_FILE}:" >&2
  printf '  - %s\n' "${missing[@]}" >&2
  exit 1
fi

count=0
while IFS= read -r line || [[ -n "$line" ]]; do
  # Skip comments and blanks; split on the first '=' only.
  [[ "$line" =~ ^[[:space:]]*# ]] && continue
  [[ "$line" =~ ^[[:space:]]*$ ]] && continue
  [[ "$line" != *=* ]] && continue

  name=${line%%=*}
  value=${line#*=}
  name=$(echo "$name" | tr -d '[:space:]')
  # Strip surrounding quotes if present.
  value=${value%\"}; value=${value#\"}
  value=${value%\'}; value=${value#\'}
  [[ -z "$value" ]] && continue

  vercel env rm "$name" "$TARGET" --yes >/dev/null 2>&1 || true
  printf '%s' "$value" | vercel env add "$name" "$TARGET" >/dev/null
  echo "  set ${name}"
  count=$((count + 1))
done < "$ENV_FILE"

echo "==> ${count} variables written to the ${TARGET} environment."
echo "    Redeploy for them to take effect: ./deploy/deploy-vercel.sh --prod"
