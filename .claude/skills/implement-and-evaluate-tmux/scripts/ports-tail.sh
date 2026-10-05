#!/usr/bin/env bash
# ports-tail.sh — periodically show TCP ports listened on by processes whose
# working directory is inside the team's worktree. Project-agnostic: does not
# read any project-specific env files; uses `lsof` only.
#
# Inputs (positional):
#   $1  worktree_abspath  e.g. /Users/wesley/.../.claude/worktrees/F05-folder-organization
#
# Run in a small (~10-line) tmux pane on the right side of a team window, below
# services-tail.

set -uo pipefail

worktree="${1:?usage: ports-tail.sh <worktree>}"
INTERVAL=5

# Strip any trailing slash so the prefix match is canonical.
worktree="${worktree%/}"

require_lsof() {
    if ! command -v lsof >/dev/null 2>&1; then
        echo "lsof not installed — cannot discover ports."
        exit 0
    fi
}
require_lsof

# Discover PIDs whose CWD is inside the worktree. Pure lsof, portable across
# macOS and Linux.
discover_pids() {
    lsof -nP -d cwd -F pn 2>/dev/null | awk -v wt="$worktree/" '
        /^p/ { pid = substr($0, 2) }
        /^n/ {
            cwd = substr($0, 2) "/"
            if (index(cwd, wt) == 1) print pid
        }
    ' | sort -u
}

print_header() {
    printf '═══ %s ═══\n' "$(basename "$worktree")"
    printf '%s\n' "$(date '+%H:%M:%S')"

    if [ -e "$worktree/.git" ]; then
        local branch
        branch=$(cd "$worktree" 2>/dev/null && git branch --show-current 2>/dev/null) || branch=""
        [ -n "$branch" ] && printf 'branch: %s\n' "$branch"
    fi
    echo
}

list_listening_ports() {
    local pids="$1"
    if [ -z "$pids" ]; then
        echo "(no processes with cwd inside worktree)"
        return
    fi

    local pid_csv
    pid_csv=$(echo "$pids" | paste -sd, -)

    # lsof: TCP LISTEN sockets owned by any of the matching PIDs.
    # Output format (single line per socket):
    #   COMMAND PID USER FD TYPE DEVICE SIZE NODE NAME
    # NAME is something like *:3000 or 127.0.0.1:5432 (LISTEN)
    local rows
    rows=$(lsof -nP -iTCP -sTCP:LISTEN -a -p "$pid_csv" 2>/dev/null | tail -n +2)

    if [ -z "$rows" ]; then
        echo "(no listening TCP ports yet)"
        return
    fi

    printf '%-5s %-7s %s\n' "PORT" "PID" "COMMAND"
    printf '%s\n' "─────────────────────────────────────────────"
    # First pass: extract pid+port from lsof; second pass: enrich with full
    # command line via `ps`. Project-agnostic — no .pid file lookups.
    echo "$rows" | awk '{
        pid = $2
        name = $9
        n = split(name, parts, ":")
        port = parts[n]
        gsub(/\(.*\)/, "", port)
        print port "\t" pid
    }' | sort -u | sort -n -k1 | while IFS=$'\t' read -r port pid; do
        # Full command line. `ps -o command=` strips the header.
        cmd=$(ps -p "$pid" -o command= 2>/dev/null)
        cmd="${cmd#"${cmd%%[! ]*}"}"  # trim leading whitespace
        # Make the line readable: every absolute path token (starts with `/`)
        # gets basenamed. Relative paths and flags pass through.
        # Example: "/opt/.../bin/node /Users/.../tsx/dist/loader.mjs src/main.ts"
        #       → "node loader.mjs src/main.ts"
        cmd=$(echo "$cmd" | awk '{
            for (i = 1; i <= NF; i++) {
                if (substr($i, 1, 1) == "/") {
                    n = split($i, parts, "/")
                    $i = parts[n]
                }
            }
            print
        }')
        # If still too long, truncate from the END (the prefix is now meaningful).
        max=60
        if [ ${#cmd} -gt $max ]; then
            cmd="${cmd:0:$((max - 3))}..."
        fi
        printf '%-5s %-7s %s\n' "$port" "$pid" "$cmd"
    done
}

while true; do
    clear
    print_header
    pids=$(discover_pids)
    list_listening_ports "$pids"
    sleep "$INTERVAL"
done
