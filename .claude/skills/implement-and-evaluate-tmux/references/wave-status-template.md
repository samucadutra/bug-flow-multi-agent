# Wave Status Template

Pinned format for **two artifacts** produced by `implement-and-evaluate-tmux` at finalize:

1. `<wave-dir>/wave-status.md` — persisted artifact, sibling of `wave.meta` and `status/`. Survives the tmux session being killed.
2. The **chat report** the Main Claude session emits at the end of Step 7. Same shape, slightly more terse.

Both follow the same structure: a compact summary at the top, then a per-failing-team detail section. Successful teams collapse to a single line each (PR URL is the only data the reader needs).

---

## `wave-status.md` template

```markdown
# Wave Status — `<wave-tag>` (run `<run-id>`)

**Status:** `all-success | partial-success | all-failed | aborted`
**Started:** `<ISO-8601>`
**Finished:** `<ISO-8601>` (`<HhMM>`m elapsed)
**Tmux session:** `iaet-<wave-tag>-<run-id>` — attach: `tmux attach -t iaet-<wave-tag>-<run-id>`
**Selected features:** `F0X, F0Y, F0Z` (`<N>` total)
**max-parallel:** `<N>` · **team-timeout:** `<Nm>`

---

## Teams

| ID | Slug | Status | Cycles | Elapsed | PR | Journal |
|---|---|---|---|---|---|---|
| F03 | video-upload      | ✓ success         | 2 | 16m | #142 https://github.com/.../pull/142 | docs/F03-video-upload/orchestration-<ts>.md |
| F05 | transcription     | ✗ stuck           | 4 | 18m | —                                    | docs/F05-transcription/orchestration-<ts>.md |
| F07 | admin-panel       | ✓ success         | 1 | 12m | #143 https://github.com/.../pull/143 | docs/F07-admin-panel/orchestration-<ts>.md |

**PRs opened:** `<M>` of `<N>`

---

## Worktrees preserved

*(Empty when every team succeeded and no `keep worktrees`.)*

- `.claude/worktrees/F05-transcription/` — cleanup: `git worktree remove .claude/worktrees/F05-transcription`

---

## Failure detail

*(One block per non-`success` team. `success` teams already covered by the table; no expansion needed.)*

### F05 transcription — stuck

- **Reason:** circuit breaker tripped at cycle 4 (same FAIL set, zero PASS delta)
- **Items still failing:** `API-TRANSCRIBE-CONCURRENT-01`, `EVENT-TRANSCRIPTION-PARTIAL-02`
- **Latest eval-report:** `docs/F05-transcription/eval-report-<ts>.md`
- **Worktree:** `.claude/worktrees/F05-transcription/`
- **Re-run:** `cd .claude/worktrees/F05-transcription && claude /implement-and-evaluate F05` (resumes from current branch state)

---

## Soft-fails (wave-level)

- *(none)*

---

## Overrides applied

- `max-parallel=3` (default)
- `team-timeout=90m` (default)
- *(forwarded to each team:)* *(none)*

## Overrides ignored

- *(none)*
```

---

## Chat report template

Emitted at end of Step 7. The Main Claude session prints this verbatim to chat. Slightly more compact than the persisted file (skips the empty sections).

```
implement-and-evaluate-tmux — Wave <wave-tag> (<N> teams)

Wave status: <all-success | partial-success | all-failed>
Started:  <ISO-8601>
Finished: <ISO-8601> (<HhMM>m elapsed)
Tmux session: iaet-<wave-tag>-<run-id>  (still alive — `tmux attach -t iaet-<wave-tag>-<run-id>`)

Teams:
  ✓ F03 video-upload      success     cycles 2  PR #142  https://github.com/.../pull/142
  ✗ F05 transcription     stuck       cycles 4  no PR    journal: docs/F05-transcription/orchestration-<ts>.md
  ✓ F07 admin-panel       success     cycles 1  PR #143  https://github.com/.../pull/143

PRs opened: <M> of <N>

Worktrees preserved (<K>):
  - .claude/worktrees/F05-transcription/   (cleanup: `git worktree remove .claude/worktrees/F05-transcription`)

────────────────────────────────────────
Failure detail

F05 transcription — stuck
  Reason: circuit breaker tripped at cycle 4 (same FAIL set, zero PASS delta)
  Items still failing: API-TRANSCRIBE-CONCURRENT-01, EVENT-TRANSCRIPTION-PARTIAL-02
  Eval-report: docs/F05-transcription/eval-report-<ts>.md
  Re-run: `cd .claude/worktrees/F05-transcription && claude /implement-and-evaluate F05`
────────────────────────────────────────

Wave status file: .claude/worktrees/.wave-<run-id>/wave-status.md
prd_progress.json reconciled from per-team journals.

Soft-fails (wave-level):
  - <line>     (omit section if none)

Overrides applied: max-parallel=3 (default), team-timeout=90m (default), <forwarded tail or none>
Overrides ignored: (none)                                                  (omit if none)
```

---

## Wave status vocabulary

| Status | Meaning |
|---|---|
| `all-success` | every team's terminal status was `success` |
| `partial-success` | at least one `success` AND at least one non-`success` |
| `all-failed` | zero `success` |
| `aborted` | Main session aborted before any team finished (Step 1/2 errors). No team table. |

## Per-team status vocabulary

Same as `/implement-and-evaluate`'s final-verdict status, plus `timeout` (added by this skill when wall-clock exceeds `team-timeout`):

`success` · `manual-pending` · `stuck` · `exhausted` · `aborted` · `pr-blocked` · `timeout`

---

## Notes for the writer

- **Markers in the table use Unicode (UTF-8)**: `✓`, `✗`, `⚠`, `●` — match the dashboard's vocabulary so the persisted file and the live dashboard look familiar. Terminal must support UTF-8.
- **Failed teams render the detail block in lexicographic order by feature ID** so the same wave run is byte-stable across two consecutive renders (idempotent write).
- **Successful teams never get a detail block.** The PR URL + journal path is enough — anything more is rot waiting to happen as the PR evolves.
- **Worktrees preserved section omits the heading entirely when empty.** `*(none)*` is reserved for sub-bullets, not whole sections.
- **`Re-run` lines** for failed teams ALWAYS use `cd <worktree>` first, so the user lands in the correct branch with the correct DB / port offsets from `resolve-env.sh`. Re-running from the main repo would hit a different branch's environment.
```
