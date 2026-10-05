# BugFlow v2 — Execution Guide

How to build the project wave by wave with the `spec-writer` and `implement-and-evaluate-tmux` skills. Source of truth for waves: Section 8 of `docs/prd.md` (also mirrored in `docs/prd_progress.json`).

**Total: 11 waves, 15 features.** Run **spec-writer for wave N only after wave N-1 is implemented and merged**, so each spec can observe the code that already exists.

## The loop (repeat for each wave)

1. **Specs:** `/spec-writer wave N` (or `/spec-writer F0X` for one feature)
2. **Implement:** `/implement-and-evaluate-tmux wave N` (or `/implement-and-evaluate F0X` for a single-feature wave)
3. **Merge** every PR the wave opened into `main` (and pull). The next wave starts from a `main` that contains this wave.
4. Check `docs/prd_progress.json`: every feature of the wave must be `done` before you continue.

## Wave table

| Wave | Features | Parallel? | Spec command | Implementation command |
|---|---|---|---|---|
| 1 | F01 Project Foundation | no | `/spec-writer F01` | `/implement-and-evaluate F01` |
| 2 | F02 Schema, Migrations and Seed | no | `/spec-writer F02` | `/implement-and-evaluate F02` |
| 3 | F03 Service Layer, Bug Management and CLI Skeleton | no | `/spec-writer F03` | `/implement-and-evaluate F03` |
| 4 | F04 Embeddings Index and Similar Search | no | `/spec-writer F04` | `/implement-and-evaluate F04` |
| 5 | F05 Triage Agents | no | `/spec-writer F05` | `/implement-and-evaluate F05` |
| 6 | F06 Background Runs, F07 Report Rendering, F08 Reopen | yes (3) | `/spec-writer wave 6` | `/implement-and-evaluate-tmux wave 6` |
| 7 | F09 API, Operations and Parity | no | `/spec-writer F09` | `/implement-and-evaluate F09` |
| 8 | F10 Frontend Shell and Dashboard | no | `/spec-writer F10` | `/implement-and-evaluate F10` |
| 9 | F11 Bug List/Detail, F13 Operations Console, F14 Search Page | yes (3) | `/spec-writer wave 9` | `/implement-and-evaluate-tmux wave 9` |
| 10 | F12 Agent Trace View | no | `/spec-writer F12` | `/implement-and-evaluate F12` |
| 11 | F15 End-to-End Smoke Test and Quickstart | no | `/spec-writer F15` | `/implement-and-evaluate F15` |

Why single-feature waves use the single-feature commands: `/spec-writer F0X` runs the interactive interview (better for the foundation features where stack decisions are made), and `/implement-and-evaluate F0X` is the same loop `/implement-and-evaluate-tmux` runs inside each window, without the tmux overhead. `/implement-and-evaluate-tmux wave N` also works for a one-feature wave if you prefer a uniform command.

Only **waves 6 and 9** benefit from tmux: they are the only waves with parallel features. Wave 6 touches different modules (background runner, report templates, reopen), and wave 9 touches different frontend pages.

## Before the first wave (one-time)

- **Resolve the spec-folder conflict.** `spec-writer` writes `docs/F<ID>-<name>/` (`spec.md`, `plan.md`, `contract.md`), but `AGENTS.md` says specs live in `specs/NNN-feature-name/` and refers to `specs/constitution.md`. Decide which convention wins and update `AGENTS.md` or accept the skills' `docs/` layout, so assistants don't read the wrong folder. Also note `AGENTS.md` quality-gate commands run from `backend/` in this project.
- **Prerequisites for the tmux skill:** `tmux`, `git` worktrees, and an authenticated `gh` CLI (`gh auth status`) because each team opens a pull request. The GitHub MCP server in this environment currently fails to connect (authorization header error); this does not replace `gh`, but fix it if you want MCP-based GitHub tooling.
- **Push the repo to a GitHub remote** with `main` as default branch so PR creation works.
- Make sure `docs/prd.md` is committed on `main`; worktrees are created from the default branch and need it.
- Wave 1 (F01) creates `scripts/resolve-env.sh`, which the tmux skill expects for per-worktree ports and databases. Until F01 is merged, do not run the tmux skill.
- Set `OPENAI_API_KEY` in your own `.env` only for manual demos; automated tests use a mocked LLM.

## Per-wave notes

**Wave 1 — F01 Foundation.** Creates the monorepo skeleton, config, Docker Compose and `scripts/resolve-env.sh`. Check: `docker compose up -d` is healthy and the quality gate passes from `backend/`.

**Wave 2 — F02 Schema.** Check: `init_db` twice is idempotent, seed leaves 20 bugs.

**Wave 3 — F03 Services/CLI.** Check: `uv run bugflow --help` and `uv run bugflow check` from `backend/`.

**Wave 4 — F04 Search.** Needs a real `OPENAI_API_KEY` only for manual verification (`bugflow index`, `bugflow search`).

**Wave 5 — F05 Triage agents.** The core of the demo. Check the mocked end-to-end test, then run one real `bugflow triage --bug 1` and read the stored step inputs.

**Wave 6 — F06, F07, F08 (parallel).** Use `/implement-and-evaluate-tmux wave 6` (default `max-parallel=3`, `team-timeout=90m`). Merge the three PRs; if two touch the triage pipeline hook (F06/F07), resolve conflicts before wave 7.

**Wave 7 — F09 API.** Check: `uv run bugflow serve`, open `http://127.0.0.1:8000/docs`, parity test green.

**Wave 8 — F10 Frontend shell.** Scaffolds `frontend/` (Next.js). Run it alone: it is a foundation feature.

**Wave 9 — F11, F13, F14 (parallel).** Use `/implement-and-evaluate-tmux wave 9`. Merge the three PRs.

**Wave 10 — F12 Agent Trace.** The demo centerpiece. Check live updates with a real triage.

**Wave 11 — F15 Smoke + Quickstart.** Final: follow the README from a fresh clone and walk the end-to-end script.

## Useful options for the tmux dispatcher

- `max-parallel=<N>` (default 3), `team-timeout=<N>m` (default 90m)
- `wave 6 except F08`, `wave 9 only F11,F14` to run part of a wave
- `keep worktrees` / `clean worktrees` to control worktree cleanup
- Re-run the same command to retry features whose status is `fail` or `implemented`; features already `done` are skipped.

## Order at a glance

```
W1 F01 -> W2 F02 -> W3 F03 -> W4 F04 -> W5 F05 -> W6 [F06 | F07 | F08] -> W7 F09
 -> W8 F10 -> W9 [F11 | F13 | F14] -> W10 F12 -> W11 F15
```
