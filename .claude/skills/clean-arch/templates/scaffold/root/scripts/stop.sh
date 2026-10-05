#!/usr/bin/env bash
set -euo pipefail

_STOP_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=./resolve-env.sh
source "$_STOP_DIR/resolve-env.sh"

HAS_DB="__HAS_DB__"
CLEAN=false

for arg in "$@"; do
    case "$arg" in
        --clean) CLEAN=true ;;
        *) echo "[stop] unknown flag: $arg" >&2; exit 1 ;;
    esac
done

log() { echo "[stop] $*"; }

kill_pid_file() {
    local label="$1"
    local pid_file="$PIDS_DIR/${label}.pid"
    [ -f "$pid_file" ] || return 0

    local pid
    if pid="$(app_read_pid_file "$pid_file")" && app_pid_matches_project "$pid"; then
        local pgid
        pgid="$(app_process_group "$pid")"
        if [ -n "$pgid" ]; then kill -- "-${pgid}" 2>/dev/null || true; fi
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        log "${label}: stopped."
    fi
    rm -f "$pid_file"
}

drop_database() {
    [ "$HAS_DB" = "true" ] || return 0
    command -v pg_isready > /dev/null 2>&1 || return 0
    pg_isready -h 127.0.0.1 -p "$APP_PG_PORT" > /dev/null 2>&1 || return 0

    if [ -f "$PROJECT_DIR/docker-compose.yml" ] && command -v docker > /dev/null 2>&1 \
        && docker ps --format '{{.Names}}' 2>/dev/null | grep -qE '(^|[-_])postgres([-_]|$)'; then
        PGPASSWORD=postgres dropdb --if-exists -h 127.0.0.1 -p "$APP_PG_PORT" -U postgres "$APP_DB_NAME" || true
        return
    fi
    dropdb --if-exists -h 127.0.0.1 -p "$APP_PG_PORT" -U "$USER" "$APP_DB_NAME" || true
}

kill_pid_file "backend"
kill_pid_file "web"

if $CLEAN; then
    drop_database
    log "Clean complete."
fi

log "Done."
