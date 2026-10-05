#!/usr/bin/env bash
# services-tail.sh — runs in the right pane of a team's tmux window.
# Waits for service log files to be created by the team's evaluator (which
# triggers `./scripts/init.sh`), then `tail -F`s them so the user sees backend
# and web (Next.js) output live alongside the claude TUI.
#
# Inputs (positional):
#   $1  worktree_abspath  e.g. /Users/wesley/.../.claude/worktrees/F05-folder-organization
#
# Files watched (relative to worktree):
#   .pids/backend.log
#   .pids/web.log
#
# Uses `tail -F` (capital F) which:
#   - tolerates files that don't exist yet (retries)
#   - follows file rotation/recreation
#   - prints `==> filename <==` headers between sources

set -uo pipefail

worktree="${1:?usage: services-tail.sh <worktree_abspath>}"
pids_dir="$worktree/.pids"
backend_log="$pids_dir/backend.log"
web_log="$pids_dir/web.log"

echo "═══════════════════════════════════════════"
echo " $(basename "$worktree")"
echo " watching: .pids/{backend,web}.log"
echo "═══════════════════════════════════════════"

# Wait for at least one file to exist before starting tail (otherwise tail -F
# spams "cannot open" errors). Quiet loop — no periodic chatter.
while [ ! -f "$backend_log" ] && [ ! -f "$web_log" ]; do
    sleep 5
done

echo
# tail -F handles missing-then-appearing files and rotation.
# Both files passed even if only one exists yet — tail -F retries.
exec tail -F "$backend_log" "$web_log" 2>&1
