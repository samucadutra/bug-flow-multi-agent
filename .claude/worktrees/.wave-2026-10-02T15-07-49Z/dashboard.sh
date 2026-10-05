#!/usr/bin/env bash
# dashboard.sh — renders the live wave status table.
# Run under `watch -n 5` in window 0 of the wave's tmux session.
#
# Reads:
#   - $1/wave.meta             (wave metadata)
#   - $1/status/*.status        (per-team terminal status — written on team driver exit)
#   - <worktree>/docs/F<ID>-<slug>/orchestration-*.md  (per-team journal — for live phase/cycle/items)
#
# Output: a table to stdout. `watch` redraws every 5s.
#
# Usage: dashboard.sh <wave_dir>

set -uo pipefail
wave_dir="${1:?usage: dashboard.sh <wave_dir>}"

meta_file="$wave_dir/wave.meta"
status_dir="$wave_dir/status"

[ -f "$meta_file" ] || { echo "no wave.meta at $meta_file"; exit 0; }

# --- Read wave meta ---
get_meta() { awk -F= -v k="$1" '$1==k { sub(/^[^=]+=/, ""); print; exit }' "$meta_file"; }

run_id=$(get_meta run_id)
wave_tag=$(get_meta wave_tag)
started_at=$(get_meta started_at)
max_parallel=$(get_meta max_parallel)
team_timeout=$(get_meta team_timeout)
selected=$(get_meta selected_features)

# --- Header ---
elapsed_s=$(( $(date -u +%s) - $(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$started_at" +%s 2>/dev/null || echo 0) ))
elapsed_h=$(( elapsed_s / 3600 ))
elapsed_m=$(( (elapsed_s % 3600) / 60 ))
elapsed_str=$(printf "%dh%02dm" "$elapsed_h" "$elapsed_m")

printf 'Wave %s — run %s\n' "$wave_tag" "$run_id"
printf 'Started: %s · elapsed: %s · max-parallel=%s · team-timeout=%s\n\n' \
    "$started_at" "$elapsed_str" "$max_parallel" "$team_timeout"

# --- Table ---
printf '%-5s  %-20s  %-12s  %-5s  %-10s  %-9s  %s\n' \
    "ID" "Slug" "Phase" "Cycle" "P/F/B/M" "Elapsed" "Status"
printf '%s\n' "$(printf '%.0s-' {1..96})"

IFS=',' read -r -a pairs <<< "$selected"
for pair in "${pairs[@]}"; do
    pair_trim="$(echo "$pair" | tr -d ' ')"
    # selected_features is "F03:video-upload,F05:transcription,..."
    fid_trim="${pair_trim%%:*}"
    pair_slug="${pair_trim#*:}"
    [ "$pair_slug" = "$pair_trim" ] && pair_slug=""  # no slug suffix
    sf="$status_dir/$fid_trim.status"
    if [ ! -f "$sf" ]; then
        printf '%-5s  %-20s  %-12s  %-5s  %-10s  %-9s  %s\n' \
            "$fid_trim" "${pair_slug:-(pending)}" "—" "—" "—" "—" "queued"
        continue
    fi

    # Read status fields.
    feat_slug=$(awk -F= '$1=="feature_slug"  { sub(/^[^=]+=/,""); print; exit }' "$sf")
    [ -z "$feat_slug" ] && feat_slug="$pair_slug"
    started=$(  awk -F= '$1=="started_at"    { sub(/^[^=]+=/,""); print; exit }' "$sf")
    finished=$( awk -F= '$1=="finished_at"   { sub(/^[^=]+=/,""); print; exit }' "$sf")
    phase=$(    awk -F= '$1=="phase"         { sub(/^[^=]+=/,""); print; exit }' "$sf")
    status=$(   awk -F= '$1=="status"        { sub(/^[^=]+=/,""); print; exit }' "$sf")
    pr_url=$(   awk -F= '$1=="pr_url"        { sub(/^[^=]+=/,""); print; exit }' "$sf")
    journal=$(  awk -F= '$1=="journal"       { sub(/^[^=]+=/,""); print; exit }' "$sf")
    worktree=$( awk -F= '$1=="worktree"      { sub(/^[^=]+=/,""); print; exit }' "$sf")

    # Live cycle/items from the journal's last cycle log row (if available).
    cycle_str="—"
    items_str="—/—/—/—"
    live_phase="$phase"
    if [ -z "$journal" ] && [ -n "$worktree" ] && [ -d "$worktree/docs/${fid_trim}-${feat_slug}" ]; then
        journal="$(ls -1t "$worktree/docs/${fid_trim}-${feat_slug}"/orchestration-*.md 2>/dev/null | head -n1)"
    fi
    if [ -n "$journal" ] && [ -f "$journal" ]; then
        # Last data row (skips header + separator) of the Cycle Log table.
        last_row="$(awk '
            /^## Cycle Log/ { in_log=1; next }
            in_log && /^## / { exit }
            in_log && /^\| *[0-9]+ *\|/ { last=$0 }
            END { print last }
        ' "$journal")"
        if [ -n "$last_row" ]; then
            cycle_num=$(  echo "$last_row" | awk -F'|' '{ gsub(/ /,"",$2); print $2 }')
            cycle_kind=$( echo "$last_row" | awk -F'|' '{ gsub(/^ +| +$/,"",$3); print $3 }')
            cycle_str="$cycle_num"
            live_phase="$cycle_kind"
            # Extract P=N F=N B=N M=N from the Counts cell.
            counts_cell=$(echo "$last_row" | awk -F'|' '{ print $5 }')
            p=$(echo "$counts_cell" | grep -oE 'P=[0-9]+' | head -n1 | cut -d= -f2)
            f=$(echo "$counts_cell" | grep -oE 'F=[0-9]+' | head -n1 | cut -d= -f2)
            b=$(echo "$counts_cell" | grep -oE 'B=[0-9]+' | head -n1 | cut -d= -f2)
            m=$(echo "$counts_cell" | grep -oE 'M=[0-9]+' | head -n1 | cut -d= -f2)
            items_str="${p:-—}/${f:-—}/${b:-—}/${m:-—}"
        fi
    fi

    # Elapsed.
    if [ -n "$started" ]; then
        end_ref="${finished:-$(date -u +%Y-%m-%dT%H:%M:%SZ)}"
        s0=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$started" +%s 2>/dev/null || echo 0)
        s1=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$end_ref" +%s 2>/dev/null || echo 0)
        diff=$(( s1 - s0 ))
        h=$(( diff / 3600 )); mn=$(( (diff % 3600) / 60 ))
        elapsed_team=$(printf "%dh%02dm" "$h" "$mn")
    else
        elapsed_team="—"
    fi

    # Status decoration.
    case "$status" in
        success)        marker="✓ success" ;;
        manual-pending) marker="⚠ manual-pending" ;;
        stuck)          marker="✗ stuck" ;;
        exhausted)      marker="✗ exhausted" ;;
        aborted)        marker="✗ aborted" ;;
        pr-blocked)     marker="✗ pr-blocked" ;;
        timeout)        marker="✗ timeout" ;;
        running)        marker="● running" ;;
        *)              marker="? $status" ;;
    esac
    [ -n "$pr_url" ] && marker="$marker ($pr_url)"

    printf '%-5s  %-20s  %-12s  %-5s  %-10s  %-9s  %s\n' \
        "$fid_trim" "${feat_slug:-—}" "${live_phase:-—}" "$cycle_str" "$items_str" "$elapsed_team" "$marker"
done

echo
done_count=$(grep -lE '^status=(success|manual-pending|stuck|exhausted|aborted|pr-blocked|timeout)$' "$status_dir"/*.status 2>/dev/null | wc -l | tr -d ' ')
running_count=$(grep -lE '^status=running$' "$status_dir"/*.status 2>/dev/null | wc -l | tr -d ' ')
total=${#pairs[@]}
queued=$(( total - done_count - running_count ))
printf 'Totals: %s done · %s running · %s queued · %s total\n' \
    "$done_count" "$running_count" "$queued" "$total"
