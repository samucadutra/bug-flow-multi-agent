#!/usr/bin/env bash
set -euo pipefail

_INIT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./resolve-env.sh
source "$_INIT_DIR/resolve-env.sh"

cd "$PROJECT_DIR"
mkdir -p "$PIDS_DIR"

HAS_DB="__HAS_DB__"
HAS_WEB="__HAS_WEB__"
MAX_WAIT=30

log() { echo "[init] $*"; }
die() { echo "[init] ERROR: $*" >&2; exit 1; }

require_command() {
    command -v "$1" > /dev/null 2>&1 || die "missing required command: $1"
}

require_startup_commands() {
    for command_name in awk lsof node npm ps sed; do
        require_command "$command_name"
    done
    if [ "$HAS_DB" = "true" ]; then require_command pg_isready; fi
}

ensure_postgres() {
    [ "$HAS_DB" = "true" ] || return 0
    if pg_isready -h 127.0.0.1 -p "$APP_PG_PORT" > /dev/null 2>&1; then
        APP_PG_MODE="reuse"
        log "PostgreSQL already running on :${APP_PG_PORT}."
        return 0
    fi
    if [ -f "$PROJECT_DIR/docker-compose.yml" ] && command -v docker > /dev/null 2>&1 && docker info > /dev/null 2>&1; then
        docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d postgres
        APP_PG_MODE="docker"
        wait_for_pg
        return 0
    fi
    if [[ "$OSTYPE" == "darwin"* ]] && command -v brew > /dev/null 2>&1; then
        local formula
        formula=$(brew services list 2>/dev/null | awk '/^postgresql@/ {print $1; exit}')
        if [ -n "$formula" ]; then
            brew services start "$formula" > /dev/null
            APP_PG_MODE="brew"
            wait_for_pg
            return 0
        fi
    fi
    die "PostgreSQL is not running. Start Postgres or Docker, then re-run."
}

wait_for_pg() {
    for _ in $(seq 1 30); do
        pg_isready -h 127.0.0.1 -p "$APP_PG_PORT" > /dev/null 2>&1 && return 0
        sleep 1
    done
    die "PostgreSQL did not become ready on :${APP_PG_PORT}."
}

ensure_database() {
    [ "$HAS_DB" = "true" ] || return 0
    case "$APP_PG_MODE" in
        reuse|brew) APP_DB_URL="postgres://${USER}@127.0.0.1:${APP_PG_PORT}/${APP_DB_NAME}"; create_db_as_local_user ;;
        docker) APP_DB_URL="postgres://postgres:postgres@127.0.0.1:${APP_PG_PORT}/${APP_DB_NAME}"; create_db_as_postgres_pwd ;;
        *) die "unknown APP_PG_MODE=${APP_PG_MODE}" ;;
    esac
    log "Database ready: ${APP_DB_NAME}."
}

create_db_as_local_user() {
    psql -h 127.0.0.1 -p "$APP_PG_PORT" -U "$USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${APP_DB_NAME}'" 2>/dev/null | grep -q 1 && return 0
    createdb -h 127.0.0.1 -p "$APP_PG_PORT" -U "$USER" "$APP_DB_NAME"
}

create_db_as_postgres_pwd() {
    PGPASSWORD=postgres psql -h 127.0.0.1 -p "$APP_PG_PORT" -U postgres -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='${APP_DB_NAME}'" 2>/dev/null | grep -q 1 && return 0
    PGPASSWORD=postgres createdb -h 127.0.0.1 -p "$APP_PG_PORT" -U postgres "$APP_DB_NAME"
}

is_label_alive() {
    local label="$1"
    local pid
    pid="$(app_read_pid_file "$PIDS_DIR/${label}.pid")" || return 1
    app_pid_matches_project "$pid"
}

resolve_ports() {
    if is_label_alive "backend"; then
        APP_BACKEND_PORT="$(app_read_env_key "$PROJECT_DIR/apps/backend/.env" "PORT" || echo "")"
    fi
    if [ "$HAS_WEB" = "true" ] && is_label_alive "web"; then
        APP_WEB_PORT="$(app_read_env_key "$PROJECT_DIR/apps/web/.env.local" "PORT" || echo "")"
    fi
    [ -z "${APP_BACKEND_PORT:-}" ] && APP_BACKEND_PORT="$(app_find_free_port $((4000 + APP_OFFSET)))"
    [ -z "${APP_WEB_PORT:-}" ] && APP_WEB_PORT="$(app_find_free_port $((3000 + APP_OFFSET)))"
    export APP_BACKEND_PORT APP_WEB_PORT
}

write_backend_env() {
    local block
    block="PORT=${APP_BACKEND_PORT}
LOG_LEVEL=info"
    if [ "$HAS_DB" = "true" ]; then
        block="${block}
DATABASE_URL=${APP_DB_URL}"
    fi
    app_write_env_keys "$PROJECT_DIR/apps/backend/.env" '^(PORT|LOG_LEVEL|DATABASE_URL)=' "$block"
}

write_web_env() {
    [ "$HAS_WEB" = "true" ] || return 0
    local block
    block="PORT=${APP_WEB_PORT}
BACKEND_INTERNAL_URL=http://localhost:${APP_BACKEND_PORT}
NEXT_PUBLIC_WEB_BASE_URL=http://localhost:${APP_WEB_PORT}"
    app_write_env_keys "$PROJECT_DIR/apps/web/.env.local" '^(PORT|BACKEND_INTERNAL_URL|NEXT_PUBLIC_WEB_BASE_URL)=' "$block"
}

install_npm_deps() {
    if [ ! -d "$PROJECT_DIR/node_modules" ] || [ "$PROJECT_DIR/package-lock.json" -nt "$PROJECT_DIR/node_modules/.package-lock.json" ]; then
        npm install --no-audit --no-fund
        return
    fi
    log "npm dependencies present."
}

run_prisma() {
    [ "$HAS_DB" = "true" ] || return 0
    npm --workspace __BACKEND_PACKAGE__ run prisma:generate --silent > /dev/null
    (cd "$PROJECT_DIR/apps/backend" && DATABASE_URL="$APP_DB_URL" npx prisma migrate deploy)
}

start_detached() {
    local log_file="$1"
    local pid_file="$2"
    shift 2
    node "$PROJECT_DIR/scripts/spawn-detached.mjs" "$log_file" "$pid_file" "$@"
}

start_backend() {
    if is_label_alive "backend"; then return 0; fi
    PORT="$APP_BACKEND_PORT" start_detached "$PIDS_DIR/backend.log" "$PIDS_DIR/backend.pid" \
        npm --workspace __BACKEND_PACKAGE__ run dev
}

start_web() {
    [ "$HAS_WEB" = "true" ] || return 0
    if is_label_alive "web"; then return 0; fi
    PORT="$APP_WEB_PORT" start_detached "$PIDS_DIR/web.log" "$PIDS_DIR/web.pid" \
        npm --workspace __WEB_PACKAGE__ run dev
}

wait_for_ready() {
    local url="$1"
    local port="$2"
    local label="$3"
    if ! command -v curl > /dev/null 2>&1; then
        wait_for_port "$port" "$label"
        return
    fi
    for _ in $(seq 1 "$MAX_WAIT"); do
        if curl -fsS "$url" > /dev/null 2>&1; then return 0; fi
        sleep 1
    done
    log "ERROR: ${label} failed readiness check at ${url}."
    tail -20 "$PIDS_DIR/${label}.log" 2>/dev/null || true
    log "Processes were left running for inspection. Run ./scripts/stop.sh to stop them."
    return 1
}

wait_for_port() {
    local port="$1"
    local label="$2"
    for _ in $(seq 1 "$MAX_WAIT"); do
        local pid
        pid="$(app_read_pid_file "$PIDS_DIR/${label}.pid")" || return 1
        app_port_owned_by_pid_group "$port" "$pid" && return 0
        sleep 1
    done
    log "ERROR: ${label} did not bind :${port}."
    return 1
}

require_startup_commands
ensure_postgres
ensure_database
resolve_ports
write_backend_env
write_web_env
install_npm_deps
run_prisma
start_backend
wait_for_ready "http://localhost:${APP_BACKEND_PORT}/health" "$APP_BACKEND_PORT" "backend"
start_web
if [ "$HAS_WEB" = "true" ]; then wait_for_ready "http://localhost:${APP_WEB_PORT}/" "$APP_WEB_PORT" "web"; fi

log "Ready."
log "  Backend  http://localhost:${APP_BACKEND_PORT}"
if [ "$HAS_WEB" = "true" ]; then log "  Web      http://localhost:${APP_WEB_PORT}"; fi
if [ "$HAS_DB" = "true" ]; then log "  Database ${APP_DB_NAME}"; fi
log "  Logs     ${PIDS_DIR}/{backend,web}.log"
