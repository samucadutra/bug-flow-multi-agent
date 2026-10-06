# Implementation Plan: F01. Project Foundation

**Prerequisites:**
- `uv` (0.12 or newer) able to provision Python 3.12
- Docker Engine with Compose v2 (27.x / 2.32 or newer)
- `git` 2.34 or newer (worktree support) and `bash`
- Latest stable `typer` and `pydantic-settings`, pinned in `uv.lock`; `pytest` and `ruff` as development dependencies. Verify each API against the installed package version before use, since the spec is a sketch
- No environment variables are required to start. `OPENAI_API_KEY` is not needed for this feature
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: Repository and Backend Skeleton

**1. Monorepo Scaffolding** - Create the root layout (`docs/` already exists): `scripts/`, `.gitignore` and a short English `README.md` stub that replaces the SDD-kit text. Make sure the git-ignore rules cover `.env` but not `.env.example`. See spec sections 1 and 4.

**2. Backend uv Project** - Initialize `backend/` as a uv project with src layout, package `bugflow`, Python 3.12 pin and the `bugflow` console script. Add only the dependencies named in spec assumption 15, and configure Ruff and pytest (including the `integration` marker that is skipped by default) as described in spec assumption 14.

**3. Test Harness Conventions** - Create the `tests/` tree with shared fixtures, the `unit` and `integration` folders, and the empty `fixtures/` and `mocks/` folders that later features reuse. The harness must isolate tests from the developer's real environment and `.env` file.

### Stage 2: Configuration, Logging and CLI

**4. Environment Contract** - Write `.env.example` listing every variable of the PRD table with the documented defaults, an empty `OPENAI_API_KEY` and placeholder-only passwords. Keep it aligned with the configuration model in spec section 6.

**5. Config Module** - Implement `bugflow.config` as the only reader of environment variables, following the interface and fail-fast behavior of spec section 5.1. Secrets must never be echoed by the settings representation or by any error message.

**6. Logging with Redaction** - Implement `bugflow.logging_config` with the one-line format, optional run ID segment and the redaction mechanism described in spec section 5.2 and assumption 7. Redaction must cover messages, interpolated arguments and exception text.

**7. CLI Entry Point** - Implement the minimal Typer app behind the `bugflow` console script with `--version` and an English `--help`. It must work on a bare clone without any environment configuration; F03 will extend it with real commands.

### Stage 3: Local Infrastructure

**8. Docker Compose Database** - Add `docker-compose.yml` with the single `db` service defined in spec section 5.5 and assumption 11: pgvector image, loopback-only port, named volume, health check and `.env.example` defaults as interpolation fallbacks.

**9. Worktree Environment Script** - Write `scripts/resolve-env.sh` implementing the offset derivation, output format, `--export` flag and error handling of spec section 5.4 and assumptions 9 and 10. Mark it executable and make it work from any directory inside a checkout, including linked worktrees created under the repository.

### Stage 4: Skeleton Readiness

**10. Quality Gate on the Skeleton** - Run the full quality gate from `backend/` and fix any formatting or lint findings so the empty skeleton is green. Commit `uv.lock` together with the project files.

**11. Foundation Handoff Check** - Confirm that `bugflow --version` runs through `uv run` from `backend/`, that the database service becomes healthy and survives a down and up cycle, and that no text in the repository is in a language other than English. Record any deviation from the spec so it can be reported.
