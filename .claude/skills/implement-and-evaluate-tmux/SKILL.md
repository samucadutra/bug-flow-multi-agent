---
name: implement-and-evaluate-tmux
description: Dispatches an entire PRD wave in parallel by spawning one isolated git worktree + tmux window per feature, each running `/implement-and-evaluate` independently. The Main Claude session orchestrates only the spawn (worktree creation, tmux layout, throttling), then polls until every team reaches a terminal status, then emits a single consolidated chat report and writes `wave-status.md`. Each team opens its own PR (with conflict resolution) on success; failures keep their worktree for inspection. Use when the user wants to drive a whole wave concurrently — e.g. `/implement-and-evaluate-tmux wave 3`, `/implement-and-evaluate-tmux F03,F05,F07`, `/implement-and-evaluate-tmux wave 3 except F04`.
---

# Implement with Teammates

End-to-end **wave-level** dispatcher. Where `implement-and-evaluate` shepherds **one** feature through `impl → eval → fix → eval → PR`, this skill spawns **N independent teams** — one per feature in the wave — each in its own git worktree and tmux window, each running its own `/implement-and-evaluate` invocation.

The Main Claude session is a **dispatcher and consolidator**, not a strict orchestrator: it creates worktrees, lays out the tmux session, throttles concurrency, then polls. It never decides anything mid-cycle for any team — that decision-making lives entirely inside each team's `/implement-and-evaluate`.

## Core principles

1. **One team per feature, one worktree per team, one tmux window per team.** Cross-feature parallelism is real and physical (separate processes, separate working trees, separate branches, separate DBs and ports thanks to `scripts/resolve-env.sh`).
2. **Reuse, don't reinvent.** Each team is literally `claude /implement-and-evaluate F<ID>` running in its window. The retry loop, circuit-breaker, journaling, conflict-resolution, and PR creation are all the existing skill's job.
3. **No Main-Claude orchestration during cycles.** The Main session does NOT supervise individual cycles, intervene on stuck teams (other than wall-clock timeout), or rewrite per-team artifacts. It dispatches, waits, consolidates.
4. **Independence over coordination.** A team's failure does not abort other teams. A user Ctrl-C of the Main session does not kill the teams.

---

## INPUT

Free-form. Three families of tokens are recognized; everything else is forwarded verbatim to each team's `/implement-and-evaluate` invocation.

### Family 1 — Selection (which features go in this wave)

| Form | Effect |
|---|---|
| `wave <N>` | All PRD Section 8 features tagged wave `<N>` whose `prd_progress.json` status is in {`pending`, `fail`, `implemented`}. |
| `F0X,F0Y,...` | Explicit feature IDs (comma-separated, optional spaces). |
| `wave <N> except F0X[,F0Y]` | Wave minus exclusions. |
| `wave <N> only F0X[,F0Y]` | Wave restricted to inclusions (intersection). |
| Mix: `F0X wave <N> except F0Y` | Union of explicit IDs and wave members, then exclusions. |

Selection MUST resolve to ≥1 feature. Empty selection → abort with the resolved set explained.

Each selected feature MUST have:
- A folder `docs/F<ID>-<slug>/` containing `spec.md`, `plan.md`, and `contract.md`.
- `prd_progress.json` status NOT in {`done`, `removed`, `pr-blocked`, `implementing`} — see **Pre-flight** for warnings/aborts.
- All declared dependencies (PRD Section 8) with status = `done` in `prd_progress.json` (else abort — same-wave deps are explicitly out of scope; see **EDGE CASES**).

### Family 2 — Dispatcher overrides (apply to the wave, not forwarded)

| Override | Effect | Default |
|---|---|---|
| `max-parallel=<N>` | Cap on concurrent teams. `N ≥ 1`. | `3` |
| `team-timeout=<N>m` | Wall-clock timeout per team. After this, Main kills the tmux window and marks the team `timeout` (see **Step 6**). | `90m` |
| `keep worktrees` | Do NOT delete worktrees on team success. | off |
| `clean worktrees` | Delete worktrees even on failure. Mutually exclusive with `keep worktrees`. | off |
| `progress-path=<path>` | Single `prd_progress.json` path used by every team and by the Main reconcile. Forwarded to each team. | auto-discover |

### Family 3 — Forwarded overrides (per-team, passed verbatim to `/implement-and-evaluate`)

Anything in `/implement-and-evaluate`'s grammar that is NOT in Family 4 is forwarded verbatim to each team's invocation. Examples: `max <N> retries`, `no retries`, `unlimited retries`, `keep eval env`, `skip lint`, `stub OpenAI`, `only phases 1 and 2`. Same value for all teams (no per-feature targeting in v1).

### Family 4 — Blocked overrides (incompatible with parallelism)

| Override | Reason | Action |
|---|---|---|
| `pause between cycles` | Three panels can't all pause for human input — order is undefined. | Abort with: `"'pause between cycles' incompatible with parallel wave; invoke /implement-and-evaluate per-feature for stepped runs"`. |
| `pause between phases` | Same. | Same abort. |

### Override parsing

Parse Family 2 first (longest-match), then Family 4 (abort if present), then leave the rest as the **`tail`** forwarded to each team. If a Family 2 token has an invalid value (`max-parallel=five`, `team-timeout=2hours`), abort with the offending text and the expected shape.

---

## OUTPUT

Per run:

1. **Tmux session** named `iaet-<wave-tag>-<run-id>` containing:
   - **Window 0 — `dashboard`** running `scripts/dashboard.sh` (copied into the wave dir at Step 3.3) under `watch -n 5`. Source of live status during the wave.
   - **Windows 1..N — one per feature**, named `<F-ID>-<slug>`, each running `scripts/team-driver.sh` (copied into the wave dir at Step 3.3). The driver `cd`s into the worktree and execs `claude /implement-and-evaluate F<ID> <tail>`; on exit, it writes the team's terminal status file.

2. **Wave directory** at `.claude/worktrees/.wave-<run-id>/` containing:
   - `wave.lock` — wave-level PID lockfile.
   - `wave.meta` — key=value: wave-tag, started_at, max_parallel, team_timeout, tail, selected_features.
   - `status/F<ID>.status` — one terminal status file per team, written by the team driver on `claude` exit.
   - `wave-status.md` — final consolidated artifact (see template in `references/wave-status-template.md`).

3. **Per-team worktrees** at `.claude/worktrees/F<ID>-<slug>/` (kept on failure unless `clean worktrees`; deleted on success unless `keep worktrees`).

4. **Per-team artifacts inside each worktree** (produced by `/implement-and-evaluate` — not by this skill):
   - `docs/F<ID>-<slug>/orchestration-<ts>.md` (the team's journal)
   - `docs/F<ID>-<slug>/eval-report-<ts>.md` (one per evaluator invocation)
   - Branch `feat/F<ID>-<slug>` pushed (on success) and a PR opened.

5. **Consolidated chat report** emitted by Main Claude after every team reaches terminal status. Format pinned by `references/wave-status-template.md`.

This skill itself never edits source code, never commits, never opens PRs. Code/commits/PRs are produced by the per-team `/implement-and-evaluate` invocations, each from its own worktree.

---

## EXECUTION STEPS

### Step 1 — Resolve input

1.1 — **Compute `<run-id>`** = ISO 8601 timestamp normalized for filename safety (e.g., `2026-05-02T18-02-13Z`). Used in tmux session name, wave dir, every status file.

1.2 — **Compute `<wave-tag>`** for human readability: if input contains `wave <N>`, `<wave-tag>` = `wave-<N>`; else `<wave-tag>` = `adhoc`. Used only in session/window names.

1.3 — **Parse families** per **INPUT** rules. Abort on invalid Family 2 values or any Family 4 token.

1.4 — **Resolve selection to a concrete `(feature_id, slug)` pair list**.
- If selection contains `wave <N>`, locate `prd.md` (search up from CWD max 4 levels) and read Section 8 to find features tagged that wave. Apply `except` / `only` filters. Sort lexicographically by feature ID for determinism.
- For each resolved feature ID, **derive the slug by scanning `docs/`** for a folder matching `F<ID>-*/`. Exactly one match required:
  - Zero matches → abort: `"No docs folder found for F<ID>; expected docs/F<ID>-<slug>/. Run spec-writer first."`.
  - Multiple matches → abort: `"Ambiguous docs folder for F<ID>: <list>. Resolve manually before re-running."`.
  - Exactly one → record the `(feature_id, slug)` pair (e.g., `(F03, video-upload)`).
- The pair list (not just IDs) is what gets persisted in `wave.meta` and forwarded to every downstream step.

1.5 — **Validate each selected feature**:
- Folder `docs/F<ID>-<slug>/` exists with `spec.md` + `plan.md` + `contract.md` → if not, abort listing the missing triple.
- Read `prd_progress.json` (use `progress-path=<path>` if provided, else auto-discover up from CWD max 4 levels).
  - Status `done` → emit warning (re-running may regress) but include the feature.
  - Status `removed` → emit warning (resurrects) but include.
  - Status `pr-blocked` → emit warning (may overwrite resolution attempt) but include.
  - Status `implementing` → emit warning (likely stale from a prior crashed run) but include.
  - Status `pending` / `fail` / `implemented` → no warning.
- For each PRD Section 8 dependency of this feature, check status = `done`. If any dep is not `done`, abort with: `"F<ID> depends on F<DEP> (status=<S>); same-wave deps are out of scope. Implement F<DEP> first via /implement-and-evaluate, then re-run."`.
- **Explicit ID without PRD Section 8 entry** (the user passed `F99` but PRD has no F99 row): skip the dep check for that feature, log a soft-fail `"F<ID> not in PRD Section 8; dep validation skipped"` (recorded in `wave-status.md` Soft-fails at finalize), and proceed. The triple check still applies.

1.6 — **Empty selection after filters** → abort with the explained empty set.

### Step 2 — Acquire wave lockfile

2.1 — Create `.claude/worktrees/.wave-<run-id>/` (mkdir -p, ignore-exists for the dir itself).

2.2 — **Wave lockfile** at `.claude/worktrees/.wave-<run-id>/wave.lock`. One-line file: `<PID> <run-id>`.

- The path is run-id-scoped, so two **different** run-ids never collide. The aliveness check below matters when a prior run crashed mid-flight and left its lockfile behind under the same `<run-id>` — extremely rare in practice (run-id is a fresh timestamp every time) but worth guarding.
- **Lock acquisition:**
  1. If the lockfile does not exist → write it with the current PID and `<run-id>`. Proceed.
  2. If it exists, read the PID and check `kill -0 <pid>`:
     - PID alive → abort: `"concurrent /implement-and-evaluate-tmux run for <run-id>: PID <N> alive. Wait or stop it before re-running."`.
     - PID dead → prior run crashed; overwrite the lockfile and proceed. Log under `wave-status.md` Soft-fails: `"stale wave lockfile from PID <dead-pid>; overwrote"`.
- **Lock retention:** see Step 7.5 — the lockfile is intentionally NOT released. New runs use new run-ids; the old lockfile is forensic only.

2.3 — **Per-feature collision checks** (worktree AND branch are independent — both must be clean):

For each selected feature, run two checks:

**a) Worktree existence** at `.claude/worktrees/F<ID>-<slug>/`:
- If present (`git worktree list --porcelain` shows it OR the path simply exists), prompt: `"Worktree for F<ID> already exists at <path> (likely from a prior run). Recreate it (deletes the worktree, force-removes the branch, drops the branch DB)? [y/N]"`.
- If user accepts (`y` / `yes` / `s` / `sim`):
  1. From inside the worktree, best-effort `./scripts/stop.sh --clean` (drops the branch DB; ignore errors if the worktree is corrupted).
  2. `git worktree remove --force <path>`.
  3. `git branch -D feat/F<ID>-<slug>` (always — the branch outlives the worktree by default).
- Anything else → abort the **entire wave** (no partial proceed).

**b) Branch existence** (only if worktree didn't exist or was just cleaned): `git rev-parse --verify --quiet feat/F<ID>-<slug>`. If the branch exists:
- Prompt: `"Branch feat/F<ID>-<slug> already exists locally (likely orphaned from a prior run). Force-delete it? [y/N]"`.
- If user accepts → `git branch -D feat/F<ID>-<slug>`.
- Anything else → abort the entire wave.

Either prompt aborting takes the whole wave with it. Same reason as **a)**: keeps the semantics simple.

2.4 — **Pre-flight `gh` check.** First check the binary exists: `command -v gh >/dev/null 2>&1`. If absent, abort: `"gh CLI not installed; PR creation requires it. Install via 'brew install gh' (or your platform's equivalent) and retry."`. Then run `gh auth status`. If not authenticated, abort: `"gh CLI not authenticated; PR creation will fail. Run 'gh auth login' and retry."`. Cheaper to fail here than after 30min of cycle work.

### Step 3 — Initialize wave artifacts

3.1 — Write `.claude/worktrees/.wave-<run-id>/wave.meta`:
```
run_id=<run-id>
wave_tag=<wave-tag>
started_at=<ISO-8601>
max_parallel=<N>
team_timeout=<Nm>
progress_path=<absolute path or empty>
tail=<verbatim Family 3 tail>
selected_features=F03:video-upload,F05:transcription,F07:admin-panel
```

`selected_features` uses **`F<ID>:<slug>` pairs** separated by commas. Slugs were derived in Step 1.4. The dispatcher and the dashboard parse this format identically (`tr ',' '\n' | cut -d: -f1` for IDs, `cut -d: -f2` for slugs).

3.2 — Create `.claude/worktrees/.wave-<run-id>/status/` (empty dir for now).

3.3 — Copy (or symlink — copy is safer if the skills folder is on a different filesystem) the bundled scripts:
- `scripts/team-driver.sh` → `.claude/worktrees/.wave-<run-id>/team-driver.sh`
- `scripts/dashboard.sh` → `.claude/worktrees/.wave-<run-id>/dashboard.sh`
Make both executable (`chmod +x`). The skill ships them with the executable bit already set, but copying may strip it depending on the filesystem.

### Step 4 — Create worktrees and tmux session

4.1 — **For each selected feature**, create the worktree:
```
git worktree add -b feat/F<ID>-<slug> .claude/worktrees/F<ID>-<slug> main
```

If the project's default branch is not `main`, substitute. (Determine via `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`; cache it.)

4.2 — **Create the tmux session and dashboard window**:
```
tmux new-session -d -s iaet-<wave-tag>-<run-id> -n dashboard \
    "watch -n 5 .claude/worktrees/.wave-<run-id>/dashboard.sh .claude/worktrees/.wave-<run-id>"
```

The dashboard script takes the wave dir as its argument; it reads each team's journal (latest cycle log row) and status file, renders a table.

### Step 5 — Dispatch the initial batch

Throttling and queue management are **split between Step 5 (initial dispatch) and Step 6 (respawn from queue)**. This avoids any single Bash call needing to run longer than the platform's timeout — only short, individual `tmux new-window` invocations happen here.

5.1 — Split the resolved `(feature_id, slug)` pair list into two:
- **`initial`** — the first `min(max-parallel, len(selected))` pairs. Spawn these now.
- **`queue`** — the remaining pairs (possibly empty). Hand off to Step 6, which respawns from the queue as running teams reach terminal status.

5.2 — For each pair in `initial`, spawn a tmux window with **three panes**:

```
┌───────────────────────┬───────────────────┐
│                       │ services-tail     │
│   claude TUI          │ (.pids/*.log)     │
│   pane .0             │ pane .1 (~65%h)   │
│   ~70% width          │                   │
│                       ├───────────────────┤
│                       │ ports-tail        │
│                       │ (lsof)            │
│                       │ pane .2 (~35%h)   │
└───────────────────────┴───────────────────┘
```

- **Pane .0 (left ~70%):** `claude /implement-and-evaluate` via `team-driver.sh`.
- **Pane .1 (top right):** `services-tail.sh` — `tail -F <worktree>/.pids/{backend,web}.log`. Project-specific log paths (works for projects that put service logs in `.pids/`).
- **Pane .2 (bottom right):** `ports-tail.sh` — `lsof`-based, **project-agnostic** discovery of TCP ports listened on by processes whose CWD is inside the worktree.

Concrete shape (per pair):

```bash
WAVE_DIR=".claude/worktrees/.wave-<run-id>"
SESSION="iaet-<wave-tag>-<run-id>"
WAVE_ABS="$(pwd)/$WAVE_DIR"
TAIL="<verbatim Family 3 tail>"
WORKTREE_ABS="$(pwd)/.claude/worktrees/F03-video-upload"
WIN="F03-video-upload"

# 1) Create the team window with claude as the sole pane.
tmux new-window -t "$SESSION" -n "$WIN" \
    "$WAVE_ABS/team-driver.sh F03 video-upload $WAVE_ABS \"$TAIL\""

# 2) Vertical divider — right column = services-tail (pane .1).
#    -p 50 → right column = 50% of window width, claude = 50%.
tmux split-window -h -p 50 -t "${SESSION}:${WIN}" \
    "$WAVE_ABS/services-tail.sh $WORKTREE_ABS"

# 3) Horizontal divider INSIDE the right column — bottom = ports-tail (pane .2).
#    -l 14 makes ports-tail 14 rows tall (room for header + ~7 listening ports
#    with full command lines). Adjust if your project binds more or fewer.
tmux split-window -v -l 14 -t "${SESSION}:${WIN}.1" \
    "$WAVE_ABS/ports-tail.sh $WORKTREE_ABS"

# 4) Capture ONLY the claude pane (.0) for the .log debug artifact.
tmux pipe-pane -t "${SESSION}:${WIN}.0" -o "cat >> $WAVE_ABS/status/F03.log"
```

Important: do NOT pipe the team-driver through `| tee` — that breaks claude's TTY (claude detects "not a terminal" and produces no output). Use `tmux pipe-pane` after window creation; it captures pane output without interfering with the TTY of the running process.

(Repeat per pair in `initial`.) Each `tmux ...` call returns immediately — none of them block.

5.3 — Persist the queue at `.claude/worktrees/.wave-<run-id>/queue.txt` (one `F<ID>:<slug>` per line). Step 6 consumes it.

What the team driver (`scripts/team-driver.sh`) does inside each window:
- Initial status file write (`status=running`, `started_at=<now>`, `phase=spawning`).
- `cd` into the worktree.
- `exec claude --dangerously-skip-permissions "/implement-and-evaluate F<ID> <tail>"` (foreground in the tmux window).
- On `claude` exit (any reason): parse the team's journal final-verdict block from `docs/F<ID>-<slug>/orchestration-*.md` (newest), write the terminal status file, then `sleep 99999` (keeps the window alive for inspection until `tmux kill-window` or session teardown).

The `.log` files captured by `tee` in 5.2 are debug-only artifacts — neither the dashboard nor Step 7 consumes them.

### Step 6 — Wait for terminal status, respawn from queue, enforce timeout

This is the only long-lived step. Main Claude does NOT block in a foreground `Bash` call — wave runtimes routinely exceed Bash's 10-minute timeout. Use **`Monitor`** (watching the wave dir for status-file changes) or **`ScheduleWakeup`** at 300s intervals.

On every tick, run the polling logic. Conceptually:

```
loop:
  read all .claude/worktrees/.wave-<run-id>/status/*.status files
  TERMINAL = {success, manual-pending, stuck, exhausted, aborted, pr-blocked, timeout}
  for each spawned team (status file exists):
    if status ∈ TERMINAL: mark done
    elif (now - started_at) > team_timeout:
      tmux kill-window -t iaet-<wave-tag>-<run-id>:<F-ID>-<slug>
      write status file: status=timeout, finished_at=<now>, journal=<latest or empty>
      mark done
    else: mark still-running

  RUNNING_COUNT = (still-running teams)
  while RUNNING_COUNT < max_parallel AND queue non-empty:
    pop next (F<ID>, slug) from queue.txt
    tmux new-window … team-driver.sh F<ID> <slug> …
    RUNNING_COUNT += 1

  if queue empty AND every spawned team is done: break
  else: schedule next tick (Monitor / ScheduleWakeup), exit this turn
```

Concrete tick implementation (one short Bash call, well under the 10-minute cap):

```bash
WAVE_DIR=".claude/worktrees/.wave-<run-id>"
SESSION="iaet-<wave-tag>-<run-id>"
TIMEOUT_S=$((<team-timeout-minutes> * 60))
NOW=$(date -u +%s)

# 1. Enforce timeout on running teams.
for sf in "$WAVE_DIR"/status/*.status; do
    [ -f "$sf" ] || continue
    status=$(awk -F= '$1=="status"     { sub(/^[^=]+=/,""); print; exit }' "$sf")
    started=$(awk -F= '$1=="started_at" { sub(/^[^=]+=/,""); print; exit }' "$sf")
    [ "$status" = "running" ] || continue
    s0=$(date -u -j -f "%Y-%m-%dT%H:%M:%SZ" "$started" +%s 2>/dev/null || echo "$NOW")
    if [ $((NOW - s0)) -gt "$TIMEOUT_S" ]; then
        fid=$(basename "$sf" .status)
        slug=$(awk -F= '$1=="feature_slug" { sub(/^[^=]+=/,""); print; exit }' "$sf")
        tmux kill-window -t "${SESSION}:${fid}-${slug}" 2>/dev/null || true
        # Re-write status atomically — preserve fields, flip status to timeout.
        # (Implementation detail; see scripts/team-driver.sh's write_status pattern.)
    fi
done

# 2. Respawn from queue if capacity available.
running=$(grep -lE '^status=running$' "$WAVE_DIR"/status/*.status 2>/dev/null | wc -l | tr -d ' ')
while [ "$running" -lt "<max-parallel>" ] && [ -s "$WAVE_DIR/queue.txt" ]; do
    line=$(head -n1 "$WAVE_DIR/queue.txt")
    fid="${line%%:*}"; slug="${line#*:}"
    sed -i.bak '1d' "$WAVE_DIR/queue.txt" && rm -f "$WAVE_DIR/queue.txt.bak"
    tmux new-window -t "$SESSION" -n "${fid}-${slug}" \
        "$WAVE_DIR/team-driver.sh $fid $slug $WAVE_DIR \"<TAIL>\" 2>&1 | tee -a $WAVE_DIR/status/${fid}.log"
    running=$((running + 1))
done

# 3. Done condition: queue empty AND every status file is terminal.
queue_empty=$([ ! -s "$WAVE_DIR/queue.txt" ] && echo 1 || echo 0)
non_terminal=$(grep -lE '^status=running$' "$WAVE_DIR"/status/*.status 2>/dev/null | wc -l | tr -d ' ')
spawned=$(ls "$WAVE_DIR"/status/*.status 2>/dev/null | wc -l | tr -d ' ')
selected_total=<N>
if [ "$queue_empty" -eq 1 ] && [ "$non_terminal" -eq 0 ] && [ "$spawned" -eq "$selected_total" ]; then
    echo "ALL_DONE"  # Main reads this and proceeds to Step 7.
fi
```

A short chat status update each tick (`"3 teams running, 1 in queue, 2 done"`) is acceptable but optional.

6.2 — **Timeout side effects**: the worktree and tmux window of a timed-out team are preserved (`clean worktrees` does NOT delete timeout teams). `status=timeout` is a terminal state for wave purposes and is mapped to `fail` in any reconcile (Step 7.1).

### Step 7 — Consolidate, finalize, emit report

7.1 — **Reconcile `prd_progress.json` — conditional on `progress-path`.**

There are two regimes, with very different correctness implications:

**Regime A — `progress-path` NOT provided (default).**
Each team's `/implement-and-evaluate` ran inside its own worktree, on its own branch, and wrote to its own branch's copy of `prd_progress.json`. Those writes are **already correct and committed inside the team's branch** — they propagate to `main` when each team's PR is merged. There was never any cross-worktree contention to reconcile.

→ **Do NOT touch `prd_progress.json` in the main checkout.** Writing it here would create uncommitted dirty state in the main working tree that conflicts with the upcoming PR merges (`git merge` blocks on dirty trees; even if it didn't, it'd produce per-line conflicts because each PR carries the same field updates).

The wave's status snapshot lives entirely in `wave-status.md` (Step 7.3). Failed teams' state stays as-is in main's `prd_progress.json` until the user re-runs them; successful teams' state arrives via PR merges. This is correct and conflict-free.

**Regime B — `progress-path=<absolute path>` provided.**
The user explicitly pointed every team at the SAME `prd_progress.json` outside the worktrees. All N teams wrote concurrently with potential lost updates (per **PROGRESS TRACKING**). Reconcile is necessary and safe (the file is outside any branch, so PR merges don't touch it).

For each team in this regime:
- Read the latest `docs/F<ID>-<slug>/orchestration-<ts>.md` from the team's worktree.
- Map its **Final Verdict.Status** to the appropriate fields (status, failure_reason, updated_at, completed_at, cycles, report_path). Same mapping rules as `implement-and-evaluate`'s **PROGRESS TRACKING** finalize block.
- For `timeout` teams: `status=fail`, `failure_reason="implement-and-evaluate-tmux: wall-clock timeout (<Nm>) exceeded"`.

Atomic write the merged file (read-modify-write the whole file once — single-writer reconcile).

If a journal is missing or unparseable in either regime, log a soft-fail and skip that team's reconcile (the file keeps its prior state).

7.2 — **Cleanup worktrees**:
- For each team with `status=success`: delete its worktree unless `keep worktrees` was set (`git worktree remove .claude/worktrees/F<ID>-<slug>`). The branch and PR remain on GitHub.
- For each team with non-success status: keep the worktree and the tmux window unless `clean worktrees` was set (and even then, NOT for `timeout` teams).

7.3 — **Write `wave-status.md`** at `.claude/worktrees/.wave-<run-id>/wave-status.md` per `references/wave-status-template.md`.

7.4 — **Emit consolidated chat report** per `references/wave-status-template.md`'s "Chat Report" section. Format D (compact summary on top + failure detail per failing team).

7.5 — **DO NOT release the wave lockfile yet.** Leave it for forensic clarity. Future `/implement-and-evaluate-tmux` runs use a different `<run-id>`, so they don't collide. The wave lockfile is implicitly retired the moment the chat report is emitted.

7.6 — **Note the tmux session is still alive.** The chat report includes the attach command. The user can inspect failing-team windows, then `tmux kill-session -t iaet-<wave-tag>-<run-id>` to tear it down. (Don't kill it ourselves — preserves user inspection.)

---

## PROGRESS TRACKING

This skill never writes `prd_progress.json` during Steps 1–6. Each team's `/implement-and-evaluate` writes to its own branch's copy of the file (or to a shared file under Regime B; see Step 7.1).

**Two regimes determined by `progress-path`:**

- **Regime A (default — no `progress-path`).** Each worktree's branch has its own `prd_progress.json`. Per-team writes are isolated by definition; there is no cross-worktree contention. Successful teams' updates reach `main` when their PRs merge. Failed teams' updates stay in their (preserved) worktrees until the user re-runs them. **Main does NOT touch `prd_progress.json` at finalize** — touching it would create dirty state in main that blocks PR merges.

- **Regime B (`progress-path=<absolute path>`).** All teams wrote to a single shared file. Concurrent writes can produce lost updates. **Main reconciles at Step 7.1**, single-writer, by reading every team's final-verdict and rewriting the whole file.

In both regimes, `wave-status.md` is the canonical wave-level snapshot (always written by Main at Step 7.3).

**Failure modes — silent continuation (Regime B only):**
- `prd_progress.json` at `<progress-path>` not found or unparseable → log to Soft-fails, skip the rebuild.
- A team's journal is missing or malformed → log to Soft-fails, skip that team's entry (the JSON keeps whatever transient value it had).

**Pre-flight (Step 1.5)** is the only time the skill READS `prd_progress.json` — for selection validation and dep checking. It never writes during pre-flight.

---

## RULES

**Always:**

- Validate the triple (`spec.md` + `plan.md` + `contract.md`) for every selected feature in Step 1.5.
- Validate dependency closure: every dep must be `done`. Same-wave dep = abort.
- Acquire `.claude/worktrees/.wave-<run-id>/wave.lock` before creating any worktree.
- Use `git worktree add -b feat/F<ID>-<slug> <path> <default-branch>` to create each worktree on a unique branch — this is what gives the project's `resolve-env.sh` the per-team APP_OFFSET / DB isolation.
- Throttle to `max-parallel` concurrent teams (default 3).
- Enforce `team-timeout` (default 90m) per team via wall-clock comparison against the team's `started_at`.
- On timeout, kill the team's tmux window and write `status=timeout` to its status file. Preserve worktree.
- After all teams reach terminal status, reconcile `prd_progress.json` from journals **only if `progress-path` was provided** (Regime B). Without `progress-path`, leave the main checkout's `prd_progress.json` untouched (each PR brings its own state on merge — see PROGRESS TRACKING).
- Emit the consolidated chat report per the template's Chat Report section.
- Leave the tmux session alive after Step 7 for user inspection. Print attach command in chat report.

**Never:**

- Edit source code, commit, push, or open PRs from the Main session. All of that is done by per-team `/implement-and-evaluate` from inside the team's own worktree.
- Block in a foreground `Bash` call waiting for teams. Bash's 10-minute timeout will kill long waves. Use `Monitor` or `ScheduleWakeup`.
- Kill a team mid-cycle for any reason except wall-clock timeout. The team's `/implement-and-evaluate` owns the decision tree (circuit-breaker, retry budget). The Main session does not intervene.
- Kill teams on Main Claude Ctrl-C / abort. Teams in tmux survive the Main session's death by design.
- Forward Family 4 overrides (`pause between cycles` / `pause between phases`) — abort upfront.
- Run two waves with the same `<run-id>` — the run-id is timestamp-based and never reused.
- Modify another feature's `prd_progress.json` entry beyond the selected wave members.
- Delete a `timeout`-status worktree, even if `clean worktrees` is set. Timeout = debug needed.
- Open a PR ourselves on a wave-level "all green" check. Each team owns its own PR.
- Re-implement any logic from `/implement-and-evaluate`. Bug fixes go upstream.

---

## OVERRIDES

| Override | Family | Effect | Default |
|---|---|---|---|
| `wave <N>` | 1 | Selection: all PRD wave-N features in valid status. | — |
| `F0X,F0Y,...` | 1 | Selection: explicit IDs. | — |
| `... except F0X[,...]` | 1 | Filter out from selection. | — |
| `... only F0X[,...]` | 1 | Restrict selection. | — |
| `max-parallel=<N>` | 2 | Concurrent team cap. | 3 |
| `team-timeout=<N>m` | 2 | Wall-clock per-team timeout. | 90m |
| `keep worktrees` | 2 | Don't delete on success. | off |
| `clean worktrees` | 2 | Delete even on failure (except timeout). | off |
| `progress-path=<path>` | 2 | Forwarded to all teams; Main reconciles into same file. | auto |
| `max <N> retries` | 3 | Forwarded to each team. | (team's default 3) |
| `no retries` | 3 | Forwarded to each team. | — |
| `unlimited retries` | 3 | Forwarded to each team. | — |
| `keep eval env` | 3 | Forwarded to each team. | off |
| (other) | 3 | Forwarded verbatim to each team's `/implement-and-evaluate`. | — |
| `pause between cycles` | 4 | **Abort.** | — |
| `pause between phases` | 4 | **Abort.** | — |

**Immutable core (cannot be overridden):**
- One worktree per team, on a unique branch from the default branch.
- `max-parallel ≥ 1`; concurrent execution model.
- Reconcile-from-journals at finalize.
- Tmux session preserved after finalize.
- Worktree preserved on non-success.

---

## EDGE CASES

- **Empty selection after filters** → abort, print resolved set so user understands what got filtered out.
- **Selected feature has same-wave dependency** → abort with the offending pair. The skill explicitly does NOT topo-sort intra-wave; that's a misuse signal (PRD should split the wave).
- **Selected feature's deps include cross-wave deps not yet `done`** → abort with the offending dep + status. User implements deps first.
- **Worktree exists from prior run** → interactive prompt (Step 2.3). If user declines, abort the whole wave.
- **`gh` not authenticated** → abort upfront in Step 2.4. PR creation would fail at end of every team otherwise.
- **`git worktree add` fails** (uncommitted changes in main? branch already exists?) → abort with the git error; cleanup any worktrees already created in this run.
- **A team's `/implement-and-evaluate` aborts pre-phase** (missing dep, contract empty) → its journal's final-verdict captures this; status file gets `status=aborted`. Other teams continue.
- **Wall-clock timeout fires** → kill that team's tmux window via `tmux kill-pane`; write `status=timeout`. Worktree preserved. Other teams continue.
- **All teams timeout** → consolidated report shows N timeouts. Wave status = `all-failed`. User investigates each worktree.
- **Team's claude process crashes without writing journal final-verdict** → status file shows `status=running` (driver never got to write terminal). Main treats as `aborted` after timeout fires; logs `crashed-without-status` in soft-fails.
- **PR collision: two teams' PRs touch the same files** → not the skill's problem. Each `/implement-and-evaluate` resolves merge conflicts at its own Step 7. If the user later merges both PRs in sequence, GitHub handles the human merge of the second.
- **Main Claude Ctrl-C / SIGTERM** → teams continue in tmux. No consolidated chat report emitted. User can manually `tmux attach -t iaet-<wave-tag>-<run-id>`. The tmux session was created detached (`new-session -d`) precisely so it outlives the Main session.
- **`max-parallel=1`** → fully serial wave; still runs in worktrees + tmux for isolation. Useful for debugging cross-feature contention hypotheses.
- **`max-parallel=N` larger than number of features** → no throttling; everyone spawns immediately. Fine.
- **Wave runs > 24h cumulative** → not the skill's job. The team-timeout caps individual teams; wave duration = max(team durations) for parallel section + queue time. User can set `team-timeout=4h` if their build genuinely needs that.
- **PRD not found** → abort with: `"prd.md not found in CWD or up to 4 parents; cannot resolve 'wave <N>'. Pass explicit feature IDs or run from the project root."`.
- **Same feature listed twice** (e.g., `wave 3 F03` where F03 is in wave 3) → de-duplicate silently in selection.
- **A team finishes in seconds** (already-done feature, vacuous-truth contract) → status file goes straight to `success`. Worktree gets cleaned up (unless `keep worktrees`). No special-case.
- **User attaches mid-wave to dashboard window, then detaches** → no impact. Dashboard is `watch`-driven, runs regardless of attach.
- **User attaches to a team's window and types into the Claude prompt** → that's the user's prerogative; injected text becomes part of that team's `claude` interaction. Outside the skill's scope.
- **Branch `feat/F<ID>-<slug>` exists from a prior run but worktree was already removed** → caught by Step 2.3 (b); interactive prompt to force-delete. Decline aborts the wave.
- **Multiple folders match `docs/F<ID>-*/`** (e.g., `F03-video-upload-old/` lingering next to `F03-video-upload/`) → Step 1.4 aborts with the candidate list. User resolves manually.
- **`stop.sh --clean` fails inside a stale worktree during Step 2.3 cleanup** (e.g., DB already dropped, scripts changed shape) → swallow the error; the subsequent `git worktree remove --force` is what actually frees the path. Log a soft-fail.
- **`gh` CLI not installed** → caught by Step 2.4 `command -v gh` precheck, distinct from `gh auth status` failures.
- **Linux host (not macOS)** → the dashboard's `date -u -j -f` BSD-syntax calls won't parse and elapsed times render as `0h00m`. Functional otherwise. Project's target is macOS per CLAUDE.md; documented limitation.
- **Long wave with `max-parallel < total`** → first batch dispatches in Step 5; remaining features go to `queue.txt` and Step 6's polling tick respawns them as slots open. No single Bash call exceeds the platform timeout because each tick is short-lived.
- **`progress-path=<relative path>`** (e.g., `progress-path=docs/prd_progress.json`) → resolved per-team relative to each team's CWD (their worktree), so each team writes to its own branch's copy — same as Regime A. Only an **absolute** `progress-path` produces shared-file semantics (Regime B). The skill does not normalize relative→absolute.

---

## BUNDLED FILES

**`scripts/`** — executables copied into the wave dir at Step 3.3 and run from there:
- `scripts/team-driver.sh` — bash script run in the LEFT pane (.0) of each team's tmux window. Spawns `claude /implement-and-evaluate`, writes terminal status file on exit.
- `scripts/services-tail.sh` — bash script run in the TOP-RIGHT pane (.1) of each team's tmux window. Waits for `<worktree>/.pids/{backend,web}.log` and `tail -F`s them so the user sees server output live next to claude. Project-specific (assumes `.pids/` log paths).
- `scripts/ports-tail.sh` — bash script run in the BOTTOM-RIGHT pane (.2). Periodically `lsof`-discovers TCP LISTEN sockets owned by processes whose CWD is inside the worktree. **Project-agnostic** — no `.env` reads, no project-specific assumptions.
- `scripts/dashboard.sh` — bash script for window 0; reads journals + status files, renders the live status table.

**`references/`** — read-only docs and templates the orchestrator consults but never executes:
- `references/wave-status-template.md` — pinned format for `wave-status.md` AND for the consolidated chat report.
