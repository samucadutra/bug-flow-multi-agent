#!/usr/bin/env bash
# team-driver.sh — runs in a tmux window for a single team.
#
# Responsibilities:
#   1. Initialize the team's status file (status=running, phase=spawning).
#   2. cd into the team's worktree.
#   3. exec `claude /implement-and-evaluate F<ID> <tail>` in the foreground (this window).
#   4. On claude exit (any reason), parse the team's journal final-verdict block
#      and write the terminal status file.
#   5. sleep forever to keep the tmux window alive for inspection.
#
# Inputs (positional):
#   $1  feature_id      e.g. F03
#   $2  feature_slug    e.g. video-upload
#   $3  wave_dir        e.g. .claude/worktrees/.wave-2026-05-02T18-02-13Z
#   $4  tail            forwarded overrides for /implement-and-evaluate (may be empty)
#
# Status file: $wave_dir/status/$feature_id.status
# One field per line, key=value. Atomic write (write-to-tmp + rename).

set -uo pipefail

feature_id="${1:?missing feature_id}"
feature_slug="${2:?missing feature_slug}"
wave_dir="${3:?missing wave_dir}"
tail_override="${4:-}"

status_dir="$wave_dir/status"
status_file="$status_dir/$feature_id.status"
worktree_path=".claude/worktrees/${feature_id}-${feature_slug}"
# wave_dir is .claude/worktrees/.wave-<run-id>/ — three levels below project root.
project_root="$(cd "$wave_dir/../../.." && pwd)"
worktree_abspath="$project_root/$worktree_path"

mkdir -p "$status_dir"

now_iso() { date -u +"%Y-%m-%dT%H:%M:%SZ"; }

write_status() {
    local tmp="${status_file}.tmp.$$"
    printf '%s\n' "$@" > "$tmp"
    mv -f "$tmp" "$status_file"
}

# --- Initial status ---
started_at="$(now_iso)"
write_status \
    "feature_id=$feature_id" \
    "feature_slug=$feature_slug" \
    "worktree=$worktree_abspath" \
    "started_at=$started_at" \
    "last_updated=$started_at" \
    "phase=spawning" \
    "status=running"

# --- cd into worktree and run /implement-and-evaluate ---
if [ ! -d "$worktree_abspath" ]; then
    write_status \
        "feature_id=$feature_id" \
        "feature_slug=$feature_slug" \
        "worktree=$worktree_abspath" \
        "started_at=$started_at" \
        "last_updated=$(now_iso)" \
        "finished_at=$(now_iso)" \
        "phase=done" \
        "status=aborted" \
        "abort_reason=worktree-missing"
    echo "[team-driver] FATAL: worktree not found at $worktree_abspath" >&2
    exec sleep 99999
fi

cd "$worktree_abspath"

write_status \
    "feature_id=$feature_id" \
    "feature_slug=$feature_slug" \
    "worktree=$worktree_abspath" \
    "started_at=$started_at" \
    "last_updated=$(now_iso)" \
    "phase=running" \
    "status=running"

# Construct the /implement-and-evaluate input.
ie_input="$feature_id"
if [ -n "$tail_override" ]; then
    ie_input="$ie_input $tail_override"
fi

# Run claude interactively in this pane so the user can watch.
# We use `claude` with the slash command; --dangerously-skip-permissions is intentional
# inside the worktree (the wave consented to autonomous execution).
# Note: this script never enables `set -e` (only `-uo pipefail` at the top), so
# downstream best-effort parsing (grep with no match, awk no match) is allowed
# to "fail" without aborting the script.
claude --dangerously-skip-permissions "/implement-and-evaluate $ie_input"
claude_exit=$?

# --- Parse the team's journal final-verdict block ---
finished_at="$(now_iso)"
journal=""
status_value="aborted"
abort_reason=""
pr_url=""
cycles=""

# Find the most recent orchestration-*.md in the feature's docs folder.
feature_docs="docs/${feature_id}-${feature_slug}"
if [ -d "$feature_docs" ]; then
    journal="$(ls -1t "$feature_docs"/orchestration-*.md 2>/dev/null | head -n1)"
fi

if [ -n "$journal" ] && [ -f "$journal" ]; then
    # Extract the Final Verdict status line.
    fv_status="$(awk '
        /^## Final Verdict/ { in_fv=1; next }
        in_fv && /^\*\*Status:\*\*/ {
            sub(/^\*\*Status:\*\*[[:space:]]*/, "")
            gsub(/`/, "")
            print
            exit
        }
    ' "$journal")"

    case "$fv_status" in
        success|manual-pending|stuck|exhausted|aborted|pr-blocked)
            status_value="$fv_status"
            ;;
        *)
            status_value="aborted"
            abort_reason="journal-missing-final-verdict"
            ;;
    esac

    # Extract Total cycles.
    cycles="$(awk '
        /^\*\*Total cycles:\*\*/ {
            sub(/^\*\*Total cycles:\*\*[[:space:]]*/, "")
            gsub(/`/, "")
            print $1
            exit
        }
    ' "$journal")"

    # Try to find a PR URL in the journal. Empty string if no match — `|| true`
    # because pipefail would otherwise propagate grep's exit-1 (no match).
    pr_url="$( { grep -oE 'https://github\.com/[^[:space:]]+/pull/[0-9]+' "$journal" || true; } | tail -n1)"
else
    abort_reason="journal-not-found"
fi

# Map non-zero claude exit to aborted if no journal status was recovered.
if [ -z "$status_value" ] || [ "$status_value" = "aborted" ]; then
    if [ "$claude_exit" -ne 0 ] && [ -z "$abort_reason" ]; then
        abort_reason="claude-exit-${claude_exit}"
    fi
fi

# --- Final write ---
{
    printf '%s\n' \
        "feature_id=$feature_id" \
        "feature_slug=$feature_slug" \
        "worktree=$worktree_abspath" \
        "started_at=$started_at" \
        "last_updated=$finished_at" \
        "finished_at=$finished_at" \
        "phase=done" \
        "status=$status_value" \
        "claude_exit=$claude_exit"
    [ -n "$cycles" ]       && printf 'cycles=%s\n' "$cycles"
    [ -n "$journal" ]      && printf 'journal=%s\n' "$journal"
    [ -n "$pr_url" ]       && printf 'pr_url=%s\n' "$pr_url"
    [ -n "$abort_reason" ] && printf 'abort_reason=%s\n' "$abort_reason"
} > "${status_file}.tmp.$$"
mv -f "${status_file}.tmp.$$" "$status_file"

echo
echo "[team-driver] $feature_id terminal status: $status_value"
echo "[team-driver] window kept alive for inspection. tmux kill-window when done."

# Keep the tmux window alive so the user can inspect the final claude output.
exec sleep 99999
