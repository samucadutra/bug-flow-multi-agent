#!/usr/bin/env bash
# Source this from init.sh, stop.sh, and migrate-dev.sh. Do not execute directly.
set -euo pipefail

_APP_SCRIPT_SOURCE="${BASH_SOURCE[0]:-${(%):-%x}}"
PROJECT_DIR="$(cd "$(dirname "$_APP_SCRIPT_SOURCE")/.." && pwd)"
PIDS_DIR="$PROJECT_DIR/.pids"

if git -C "$PROJECT_DIR" rev-parse --git-dir > /dev/null 2>&1; then
    _APP_BRANCH="$(git -C "$PROJECT_DIR" rev-parse --abbrev-ref HEAD)"
else
    _APP_BRANCH="default"
fi

APP_SUFFIX="$(echo "$_APP_BRANCH" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]/_/g' | cut -c1-40)"
[ -z "$APP_SUFFIX" ] && APP_SUFFIX="default"

if [ "$APP_SUFFIX" = "main" ] || [ "$APP_SUFFIX" = "default" ]; then
    APP_OFFSET=0
else
    _APP_HASH=$(echo -n "$APP_SUFFIX" | cksum | awk '{print $1}')
    APP_OFFSET=$(( (_APP_HASH % 99) + 1 ))
fi

APP_PG_PORT=5432
APP_DB_NAME="__DB_NAME_PREFIX___${APP_SUFFIX}"

app_read_env_key() {
    local file="$1"
    local key="$2"
    [ -f "$file" ] || return 1
    awk -F= -v key="$key" '$1 == key { value=substr($0, index($0, "=") + 1) }
        END { if (value != "") print value; else exit 1 }' "$file"
}

app_read_pid_file() {
    local pid_file="$1"
    [ -f "$pid_file" ] || return 1
    local pid
    pid="$(cat "$pid_file")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    echo "$pid"
}

app_process_group() {
    ps -o pgid= -p "$1" 2>/dev/null | tr -d ' '
}

app_process_cwd() {
    lsof -a -p "$1" -d cwd -Fn 2>/dev/null | awk '/^n/ { print substr($0, 2); exit }'
}

app_pid_matches_project() {
    local pid="$1"
    kill -0 "$pid" 2>/dev/null || return 1
    [ "$(app_process_cwd "$pid")" = "$PROJECT_DIR" ] || return 1
    ps -p "$pid" -o command= 2>/dev/null | grep -Eq '(^|/)npm .*run dev|^npm run dev'
}

app_listener_pids_for_port() {
    lsof -nP -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

app_port_owned_by_pid_group() {
    local port="$1"
    local pid="$2"
    local expected_pgid
    expected_pgid="$(app_process_group "$pid")"
    [ -n "$expected_pgid" ] || return 1
    local listener_pid
    for listener_pid in $(app_listener_pids_for_port "$port"); do
        [ "$(app_process_group "$listener_pid")" = "$expected_pgid" ] && return 0
    done
    return 1
}

app_find_free_port() {
    local base="$1"
    local port="$base"
    while [ "$port" -lt $((base + 1000)) ]; do
        if [ -z "$(app_listener_pids_for_port "$port")" ]; then
            echo "$port"
            return 0
        fi
        port=$((port + 100))
    done
    echo "[resolve-env] ERROR: no free port in range $base..$((base + 1000))" >&2
    return 1
}

app_write_env_keys() {
    local target="$1"
    local keys_regex="$2"
    local block="$3"
    [ -f "$target" ] || : > "$target"

    local tmp="${target}.tmp"
    grep -Ev "$keys_regex" "$target" > "$tmp" 2>/dev/null || true
    sed -i.bak -e :a -e '/^$/{$d;N;ba' -e '}' "$tmp" 2>/dev/null || true
    rm -f "${tmp}.bak"
    {
        cat "$tmp"
        [ -s "$tmp" ] && echo ""
        printf '%s\n' "$block"
    } > "$target"
    rm -f "$tmp"
}

export APP_SUFFIX APP_OFFSET APP_PG_PORT APP_DB_NAME PROJECT_DIR PIDS_DIR
echo "[resolve-env] branch=${_APP_BRANCH} suffix=${APP_SUFFIX} offset=${APP_OFFSET} db=${APP_DB_NAME}"
