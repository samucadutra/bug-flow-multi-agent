#!/usr/bin/env bash
set -euo pipefail

_MIG_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./resolve-env.sh
source "$_MIG_DIR/resolve-env.sh"

if [ "__HAS_DB__" != "true" ]; then
    echo "[migrate-dev] this project was scaffolded without database support." >&2
    exit 64
fi

if [ "${1:-}" = "--" ]; then shift; fi
if [ "$#" -eq 0 ]; then
    echo "[migrate-dev] usage: ./scripts/migrate-dev.sh -- --name <change>" >&2
    exit 64
fi

DB_URL="$(app_read_env_key "$PROJECT_DIR/apps/backend/.env" "DATABASE_URL" || true)"
if [ -z "$DB_URL" ]; then
    echo "[migrate-dev] DATABASE_URL missing. Run ./scripts/init.sh first." >&2
    exit 1
fi

cd "$PROJECT_DIR/apps/backend"
DATABASE_URL="$DB_URL" npx prisma migrate dev "$@"
