# Spec: F01. Project Foundation

**Complexity:** medium (several cooperating components, no endpoints, no database tables, one container integration).

## 1. Technical Overview

**What.** Create the monorepo skeleton and the shared base every later feature builds on: the `backend/` uv project (package `bugflow`, console script `bugflow`), the `bugflow.config` settings module, a structured logger with secret redaction, the `.env.example` contract, a Docker Compose service running Postgres with pgvector, and `scripts/resolve-env.sh` for per-worktree isolation. The Ruff and pytest quality gate must pass on the empty skeleton.

**Why.** F02 consumes the settings, the logger and the running database. F03 and later features extend the CLI entry point and the test harness created here. Deciding the layout, the configuration rules and the redaction mechanism once prevents drift (the original project's L2 defect printed a database URL with its password). `scripts/resolve-env.sh` is required by `/implement-and-evaluate-tmux` so parallel worktree teams do not collide on ports, database or compose project.

**Scope.**

Included:
- Monorepo layout: `backend/`, `docs/`, `scripts/`, `docker-compose.yml`, `.env.example`, `.gitignore`, root `README.md` stub. `frontend/` is not created (F10).
- Backend uv project: Python 3.12, src layout, package `bugflow`, console script `bugflow`, Ruff (format and lint), pytest with an `integration` marker.
- `bugflow.config`: the only code reading environment variables; validation, secret masking, fail-fast errors in English that never echo values.
- `bugflow.logging_config`: logging setup, run-ID aware formatter, redaction filter.
- Minimal Typer app exposing `bugflow --version` (F03 adds `check` and `db`).
- `.env.example` listing every variable of the PRD F01 table, no real secret; `.env` git-ignored.
- `docker-compose.yml` with one `db` service (`pgvector/pgvector:pg17`).
- `scripts/resolve-env.sh`.
- Test harness: `tests/conftest.py`, unit tests, integration tests (marker `integration`, only on request).

Excluded (PRD Section 7 and later features):
- Database schema, migrations, the `vector` extension creation, seed data (F02).
- `check`, `db init|seed|reset` commands and the run recorder (F03).
- Any LLM or embedding client (F04), CrewAI (F05), FastAPI (F09), the frontend (F10).
- Running backend or frontend inside Docker Compose; CI/CD; authentication; cloud services.
- A full README quickstart (F15).

**Cross-cutting concerns integrated:** secret safety (redaction, masked repr, no value echo in errors), English-only text, per-worktree isolation.

## 2. Architecture Impact

Affected components (all new; the repository currently holds only documentation and tooling):

- `backend/` uv project (`pyproject.toml`, `uv.lock`, `.python-version`)
- `backend/src/bugflow/config.py`, `logging_config.py`, `cli.py`, `__init__.py`
- `backend/tests/` harness
- `docker-compose.yml`, `.env.example`, `.gitignore`, `README.md`
- `scripts/resolve-env.sh`

```mermaid
graph TD
    Dev["Developer / presenter"] --> CLI["bugflow CLI (bugflow.cli)"]
    CLI -->|"--version only"| Ver["Package metadata"]
    EnvFile[".env (git-ignored) / process env"] --> Cfg["bugflow.config (Settings)"]
    Cfg --> Log["bugflow.logging_config"]
    Cfg -->|"consumed by F02"| F02["F02 init_db"]
    Log -->|"consumed by F02"| F02
    Compose["docker-compose.yml: db"] --> PG["Postgres 17 + pgvector"]
    F02 --> PG
    Resolve["scripts/resolve-env.sh"] -->|"APP_OFFSET, ports, names"| Compose
    Git["git worktree layout"] --> Resolve
```

Data flow: environment variables (process env wins over the root `.env`) are read only by `bugflow.config`; every other module receives a `Settings` object. The logging setup receives the secret values from `Settings` so the redaction filter knows what to mask. `scripts/resolve-env.sh` is independent of Python: it prints variables that a worktree bootstrapper exports before running `docker compose` and the apps.

## 3. Technical Decisions

| Decision | Chosen Approach | Alternative Considered | Trade-off |
|----------|----------------|----------------------|-----------|
| Package layout | src layout: `backend/src/bugflow/`, tests in `backend/tests/` | Flat `backend/bugflow/` | One extra directory level; prevents tests from importing the uncommitted tree by accident (user decision) |
| CLI entry point | Minimal Typer app now, extended by F03 | argparse stub replaced in F03 | Typer becomes a plan dependency in F01; no throwaway code (user decision) |
| Logging | stdlib `logging` with a redaction `Filter` and a custom `Formatter` | structlog | No extra dependency; less structured output than structlog (user decision) |
| `DATABASE_URL` default | No default in code; the documented default lives only in `.env.example`. Unset, empty or malformed fails fast | Code default of the localhost URL | A developer must copy `.env.example` first; the "missing `DATABASE_URL` fails fast" criterion becomes testable (user decision) |
| `--version` independence | `bugflow --version` never loads settings | Load settings in the app callback | `--version` works on a bare clone; settings errors surface only for commands that need them |
| Secret masking in `repr` | `SecretStr` fields plus an overridden `Settings.__repr__` rendering `***` | Rely on pydantic's default `SecretStr('**********')` | The PRD requires the literal `***`; small override to maintain |
| Env file location | Root-level `.env`, resolved from the config module's path (`parents[3]`), shared with Docker Compose | `backend/.env` | One file for compose and backend; the path logic lives in one place |
| Worktree detection | `git rev-parse --git-dir` vs `--git-common-dir` (equal means main checkout, offset 0) | Compare path to a hard-coded main path | Requires git; robust to the repository being cloned anywhere |
| Offset derivation | `cksum` of the absolute worktree top-level path, `(sum % 99) + 1` for linked worktrees | Random or counter-based | Deterministic and stateless; two worktrees can collide (about 1 in 99), `APP_OFFSET` override resolves it |

### Assumptions and Decisions (review and override as needed)

PRD blocks that did not pin a detail, and the choice made here:

1. **Config field model.** `DATABASE_URL` and `TEST_DATABASE_URL` have no code default (the PRD default column is realized in `.env.example`). `TEST_DATABASE_URL` is optional in `Settings` (only integration tests need it); when present it is validated like `DATABASE_URL`. All other variables have the code defaults of the PRD table.
2. **Accepted `DATABASE_URL` shape.** Scheme `postgresql` or `postgresql+<driver>`, non-empty host, non-empty database name. Error text is exactly `DATABASE_URL is missing or invalid`.
3. **Other invalid variables.** Error text `<VARIABLE> is invalid` (variable name only, never the value). Numeric bounds: `LLM_TIMEOUT_SECONDS` ≥ 1, `LLM_MAX_RETRIES` ≥ 0, `SIMILAR_BUGS_K` 1–20 (F04 caps search at 20), `API_PORT` 1–65535. `LOG_LEVEL` accepts `DEBUG|INFO|WARNING|ERROR|CRITICAL`, case-insensitive.
4. **`CORS_ORIGINS`** accepts a comma-separated list; default is the single origin `http://localhost:3000`.
5. **Variables not owned by the backend** (`POSTGRES_*`, `NEXT_PUBLIC_API_BASE_URL`) are ignored by `Settings` (they live in `.env` for compose and the frontend).
6. **Missing `OPENAI_API_KEY`.** `Settings` loads with an empty key; `Settings.require_openai_key()` raises `ConfigError("OPENAI_API_KEY is not set")`. F04 and F05 call it before using the key.
7. **Redaction strategy.** Value-based masking of the configured API key and of the passwords found in `DATABASE_URL` / `TEST_DATABASE_URL`, plus password masking in any `scheme://user:password@host` text, plus masking of any token shaped like `sk-` followed by 16 or more key characters (defense in depth for keys not loaded from settings). Empty secrets are never used as patterns (they would mask everything).
8. **Log output.** One line per event on stderr: `<UTC ISO-8601 timestamp> <LEVEL> [run=<id>] <message>`; the `[run=<id>]` segment is present only when a run ID is bound. CLI results go to stdout, logs to stderr.
9. **`resolve-env.sh` interface.** Prints six `KEY=value` lines: `APP_OFFSET`, `POSTGRES_PORT`, `POSTGRES_DB`, `COMPOSE_PROJECT_NAME`, `API_PORT`, `FRONTEND_PORT`. Offset 0 gives `5432`, `bugflow`, `bugflow`, `8000`, `3000`; offset N>0 gives `5432+N`, `bugflow_wN`, `bugflow_wN`, `8000+N`, `3000+N`. `--export` prefixes each line with `export `. A preset `APP_OFFSET` environment variable (integer 0–99) overrides the derivation; any other value exits non-zero with an English message on stderr.
10. **Connection URLs are not printed by `resolve-env.sh`** (they carry passwords). Aligning `DATABASE_URL` / `TEST_DATABASE_URL` with the printed port and database name is left to the worktree bootstrap that writes or exports them. **Open question for the user:** if the tmux skill should get ready-to-use URLs, decide whether printing the local demo credentials is acceptable.
11. **Compose.** Service `db`; variables `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` interpolated with the `.env.example` defaults as fallbacks; port published as `127.0.0.1:${POSTGRES_PORT}:5432`; named volume `bugflow_pgdata` (compose prefixes it with the project name, which isolates worktrees); health check `pg_isready` against the configured user and database, short interval so the service is healthy in about 15 seconds on a warm image. No init scripts: the `vector` extension is created by the F02 migration and `bugflow_test` is F02's concern.
12. **Conventions established for later features** (greenfield, nothing to observe): persistent test state is created by pytest fixtures in `backend/tests/conftest.py` (later features add migrations plus `seed_db`); static inputs live in `backend/tests/fixtures/` (none in F01); mocks and fakes live in `backend/tests/mocks/` (first used by F04/F05); there is no `.env.test` — tests inject variables with `monkeypatch` and build settings with the env file disabled, and integration tests read `TEST_DATABASE_URL` only.
13. **Quality gates.** Confirmed by the user: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`, all from `backend/`. No wrapper script that consolidates them exists in the repository (the `clean-arch` skill's `run-gates.mjs` targets TypeScript projects).
14. **Ruff/pytest settings.** Ruff line length 100, rule sets `E, F, I, UP, B`; pytest `testpaths = ["tests"]`, strict markers, and `addopts = -m "not integration"` so `uv run pytest -m integration` (last `-m` wins) runs the integration tests only on request.
15. **Dependencies.** Runtime: `pydantic-settings`, `typer`. Development group: `pytest`, `ruff`. No database driver in F01 (F02 adds it); compose checks use `docker compose exec db psql`.
16. **Source-document conflict.** `AGENTS.md` still mentions Pinecone and `psycopg.sql`; the PRD (higher precedence) uses pgvector in Docker. Nothing in F01 depends on this, but `AGENTS.md` should be refreshed.

### PRD Traceability

| PRD block | Where it lands in this spec |
|---|---|
| Provides: settings through `bugflow.config` | §4 `config.py`, §5 Settings contract, §6 configuration model |
| Provides: structured logger with redaction | §4 `logging_config.py`, §5 Logging contract |
| Provides: running Postgres with pgvector | §4 `docker-compose.yml`, §5 Compose contract |
| Capabilities: monorepo layout, backend project, env table, `.env.example` policy, compose, worktree isolation, logging, quality gate | §1 Scope, §4, §5, §6 |
| Experience | §5 CLI contract and compose contract |
| Error Handling | §5 error behavior per interface; §3 assumptions 2, 3, 6, 7 |

## 4. Component Overview

**Repository root**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `.gitignore` | New | Ignore local artifacts | Ignores `.env`, virtualenv, Python and tool caches, `node_modules`, `.next`; does not ignore `.env.example` |
| `.env.example` | New | Environment contract | Lists all 17 variables with placeholders; empty `OPENAI_API_KEY`; no real secret |
| `docker-compose.yml` | New | Local database | Service `db`, loopback-bound port, named volume, health check |
| `README.md` | Modified | Stub | Replace the SDD-kit text with a short project stub (completed in F15); English |
| `scripts/resolve-env.sh` | New | Worktree isolation | Derive `APP_OFFSET` and print per-worktree values |

**Backend (`backend/`)**

| File Path | New/Modified | Purpose | Key Responsibilities |
|-----------|--------------|---------|---------------------|
| `backend/pyproject.toml` | New | Project definition | Package `bugflow`, Python 3.12, console script `bugflow`, dependencies, Ruff and pytest configuration, `integration` marker |
| `backend/.python-version` | New | Interpreter pin | `3.12` |
| `backend/uv.lock` | New | Locked dependencies | Generated by `uv sync` and committed |
| `backend/src/bugflow/__init__.py` | New | Package root | Exposes `__version__` from package metadata |
| `backend/src/bugflow/config.py` | New | Settings | `Settings`, `ConfigError`, `load_settings`, cached `get_settings`, masked repr, fail-fast messages |
| `backend/src/bugflow/logging_config.py` | New | Logging | `Redactor`, `RedactingFilter`, formatter, `configure_logging`, run-bound logger helper |
| `backend/src/bugflow/cli.py` | New | CLI | Typer app with `--version`, `main()` entry point; no settings loaded |
| `backend/tests/conftest.py` | New | Shared fixtures | Clean-environment fixture, canary secrets, settings factory with env file disabled |
| `backend/tests/unit/test_smoke.py` | New | Package smoke | Import and version |
| `backend/tests/unit/test_config.py` | New | Settings behavior | Defaults, overrides, validation, masking, errors |
| `backend/tests/unit/test_logging.py` | New | Logging behavior | Format, run ID, redaction, level |
| `backend/tests/unit/test_cli.py` | New | CLI behavior | `--version`, `--help` |
| `backend/tests/unit/test_resolve_env.py` | New | Script behavior | Main vs linked worktree, override, export |
| `backend/tests/unit/test_repo_hygiene.py` | New | Repository rules | `.env.example` content, git-ignore rule, env reads confined to `config.py` |
| `backend/tests/integration/test_compose_db.py` | New | Compose behavior | Healthy service, loopback binding, volume persistence, pgvector availability |
| `backend/tests/fixtures/`, `backend/tests/mocks/` | New | Convention placeholders | Kept (with `.gitkeep`) so later features reuse the paths |

**Database:** no migrations in F01 (no tables).

## 5. Interface Contracts

Section 5 describes non-HTTP interfaces; F01 exposes no endpoints.

### 5.1 Settings (`bugflow.config`)

- `load_settings(env_file: Path | None = <repo root .env>) -> Settings`: builds settings; process environment overrides the file; passing `None` disables the file. Raises `ConfigError` on invalid or missing required values.
- `get_settings() -> Settings`: cached `load_settings()` for application code.
- `Settings.require_openai_key() -> str`: returns the key or raises `ConfigError("OPENAI_API_KEY is not set")`.
- `ConfigError`: carries the variable name and an English message; never carries a value.
- `repr(settings)` and `str(settings)`: every secret (API key, database passwords) appears as `***`.
- Validation errors are translated from pydantic errors using only the field location; the offending input is never included.

| Situation | Behavior |
|---|---|
| `OPENAI_API_KEY` unset or empty | Settings load; `require_openai_key()` raises `ConfigError("OPENAI_API_KEY is not set")` |
| `DATABASE_URL` unset, empty or malformed | `ConfigError("DATABASE_URL is missing or invalid")` at load time |
| Other invalid variable | `ConfigError("<VARIABLE> is invalid")` |

### 5.2 Logging (`bugflow.logging_config`)

- `configure_logging(settings: Settings) -> None`: configures the `bugflow` logger hierarchy at `settings.log_level` with a stderr handler, the run-aware formatter and the redaction filter seeded with the secret values of `settings`. Idempotent.
- `get_logger(name: str) -> logging.Logger`; `bind_run(logger, run_id: int) -> logging.LoggerAdapter`: lines emitted through the adapter include `[run=<id>]`.
- Redaction applies to the message after argument interpolation and to formatted exception text.

Example line: `2026-10-05T14:03:11Z INFO [run=42] Seeded 20 bugs`.

### 5.3 CLI (`bugflow.cli`)

- `bugflow --version` prints `bugflow <version>` to stdout, exits 0, loads no settings, writes nothing to stderr.
- `bugflow --help` prints an English description and lists `--version`.
- Console script `bugflow` maps to `bugflow.cli:main`.

### 5.4 `scripts/resolve-env.sh`

Invocation: `scripts/resolve-env.sh [--export]`, run from anywhere inside a checkout.

```
APP_OFFSET=3
POSTGRES_PORT=5435
POSTGRES_DB=bugflow_w3
COMPOSE_PROJECT_NAME=bugflow_w3
API_PORT=8003
FRONTEND_PORT=3003
```

Exit code 0 on success; non-zero with an English stderr message when `APP_OFFSET` is preset to an invalid value or the directory is not inside a git work tree.

### 5.5 Docker Compose

- Service `db`, image `pgvector/pgvector:pg17`, host port `127.0.0.1:${POSTGRES_PORT}` mapped to container port 5432, volume `bugflow_pgdata` mounted at the Postgres data directory, health check using `pg_isready`.
- `docker compose down` keeps the volume; `docker compose down -v` is the only way data is removed.
- Host port conflict: compose fails with Docker's own message; the fix is `POSTGRES_PORT` or `resolve-env.sh` (documented fully in F15).

## 6. Configuration Model

Replaces the data model section: F01 creates no tables.

| Variable | Settings field | Type | Code default | Validation | Secret |
|---|---|---|---|---|---|
| `DATABASE_URL` | `database_url` | URL string | none (required) | scheme `postgresql[+driver]`, host, database name | password masked |
| `TEST_DATABASE_URL` | `test_database_url` | URL string or none | none | same as above when present | password masked |
| `OPENAI_API_KEY` | `openai_api_key` | `SecretStr` | empty | none | yes |
| `OPENAI_MODEL` | `openai_model` | string | `gpt-4o-mini` | non-empty | no |
| `OPENAI_EMBEDDING_MODEL` | `openai_embedding_model` | string | `text-embedding-3-small` | non-empty | no |
| `LLM_TIMEOUT_SECONDS` | `llm_timeout_seconds` | int | `60` | ≥ 1 | no |
| `LLM_MAX_RETRIES` | `llm_max_retries` | int | `2` | ≥ 0 | no |
| `SIMILAR_BUGS_K` | `similar_bugs_k` | int | `5` | 1–20 | no |
| `API_HOST` | `api_host` | string | `127.0.0.1` | non-empty | no |
| `API_PORT` | `api_port` | int | `8000` | 1–65535 | no |
| `CORS_ORIGINS` | `cors_origins` | list of strings (comma-separated input) | `["http://localhost:3000"]` | non-empty entries | no |
| `LOG_LEVEL` | `log_level` | enum | `INFO` | `DEBUG, INFO, WARNING, ERROR, CRITICAL` (case-insensitive) | no |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | not read by `Settings` | — | `bugflow` ×3, `5432` (in `.env.example` and compose fallbacks) | — | password |
| `NEXT_PUBLIC_API_BASE_URL` | not read by `Settings` | — | `http://localhost:8000/api/v1` (in `.env.example`) | — | no (public by design) |

## 7. Testing Strategy

Unit tests run by default; integration tests carry the `integration` marker, call real Docker, and run only on `uv run pytest -m integration`. Tests never read `.env` (settings are built with the env file disabled) and never touch `DATABASE_URL`.

| Test File | Test Type | Target | Coverage Goal |
|-----------|-----------|--------|---------------|
| `backend/tests/unit/test_smoke.py` | Unit | Package import | n/a |
| `backend/tests/unit/test_config.py` | Unit | `bugflow.config` | 95% |
| `backend/tests/unit/test_logging.py` | Unit | `bugflow.logging_config` | 95% |
| `backend/tests/unit/test_cli.py` | Unit | `bugflow.cli` | 100% |
| `backend/tests/unit/test_resolve_env.py` | Unit (subprocess, temporary git repository and linked worktree) | `scripts/resolve-env.sh` | all branches |
| `backend/tests/unit/test_repo_hygiene.py` | Unit (file inspection, `git check-ignore`) | `.env.example`, `.gitignore`, source tree | n/a |
| `backend/tests/integration/test_compose_db.py` | Integration (Docker) | `docker-compose.yml` | n/a |

**`test_smoke.py`**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_package_imports` | Import `bugflow` | no exception |
| `test_version_matches_metadata` | `bugflow.__version__` equals installed metadata version | equal, non-empty |

**`test_config.py`**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_defaults_applied` | Only `DATABASE_URL` set | every default of the §6 table |
| `test_env_overrides_defaults` | Set model, port, retries | values reflected |
| `test_env_beats_env_file` | Temporary `.env` and process env disagree | process env wins |
| `test_missing_openai_key_does_not_crash` | No key | loads; `require_openai_key()` raises with exact message |
| `test_missing_database_url_fails_fast` | Unset | `ConfigError` with exact message |
| `test_empty_database_url_fails_fast` | Empty string | same message |
| `test_malformed_database_url_message_has_no_value` | Wrong scheme with canary password | message exact, no canary, no URL |
| `test_invalid_numeric_names_variable_only` | `LLM_TIMEOUT_SECONDS=abc` | message names the variable, not `abc` |
| `test_numeric_bounds` | `SIMILAR_BUGS_K=21`, `API_PORT=0` | rejected |
| `test_log_level_case_insensitive` | `warning` | normalized to `WARNING` |
| `test_cors_origins_comma_separated` | two origins | list of two |
| `test_unrelated_variables_ignored` | `POSTGRES_PASSWORD`, `NEXT_PUBLIC_API_BASE_URL` set | loads |
| `test_repr_masks_secrets` | canary key and password | `***` present, canaries absent |
| `test_str_masks_secrets` | same | same |

**`test_logging.py`**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_line_format` | Plain info message | timestamp, level, message, no run segment |
| `test_run_id_segment` | Message via `bind_run` | `[run=42]` present |
| `test_masks_key_in_message` | Canary key in message | `***`, no canary |
| `test_masks_key_in_args` | Canary key as `%s` argument | masked |
| `test_masks_db_password_in_url` | URL with canary password | password masked, host and database visible |
| `test_masks_secret_in_exception_text` | `logger.exception` with canary in the error | masked in traceback |
| `test_masks_unconfigured_sk_token` | `sk-` shaped token not in settings | masked |
| `test_empty_secret_does_not_mask_everything` | Empty key | message unchanged |
| `test_level_filtering` | `WARNING` level | info suppressed |
| `test_configure_logging_idempotent` | Call twice | one handler |

**`test_cli.py`**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_version_flag` | Typer `CliRunner` with empty environment | exit 0, `bugflow <version>` |
| `test_version_does_not_load_settings` | `get_settings` patched to raise | still exit 0 |
| `test_help_is_english` | `--help` | exit 0, lists `--version` |

**`test_resolve_env.py`** (builds a temporary repository with `git init` and `git worktree add`)

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_main_checkout_values` | Run in main checkout | offset 0 and the five base values |
| `test_linked_worktree_values` | Run in linked worktree | offset 1–99, ports offset, suffixed names |
| `test_deterministic` | Run twice | identical output |
| `test_offset_override` | `APP_OFFSET=7` | `5439`, `8007`, `3007`, `_w7` |
| `test_invalid_override_rejected` | `APP_OFFSET=100`, `abc` | non-zero exit, stderr message, empty stdout |
| `test_export_flag` | `--export` | every line prefixed `export ` |
| `test_outside_git_repository` | Run in a plain temp directory | non-zero exit, English message |

**`test_repo_hygiene.py`**

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_env_example_lists_all_variables` | Parse `.env.example` | names equal the 17 PRD variables |
| `test_env_example_has_no_secret` | Inspect values | empty API key, no `sk-` token, placeholder passwords only |
| `test_env_is_git_ignored` | `git check-ignore .env` | ignored; `.env.example` not ignored |
| `test_env_example_matches_settings_fields` | Compare backend variables with `Settings` fields | every backend variable maps to a field |
| `test_only_config_reads_environment` | AST scan of `backend/src` | env access only in `config.py` |

**`test_compose_db.py`** (marker `integration`; uses a unique `COMPOSE_PROJECT_NAME` and free `POSTGRES_PORT`, tears down with `-v`)

| Test Function | Description | Assertions |
|---------------|-------------|------------|
| `test_db_becomes_healthy` | `up -d --wait` | service `db` healthy; image `pgvector/pgvector:pg17` |
| `test_port_bound_to_loopback` | `docker compose port db 5432` | host `127.0.0.1` |
| `test_port_follows_postgres_port` | `POSTGRES_PORT` override | published on that port |
| `test_data_survives_down_and_up` | Write a probe row, `down`, `up -d --wait` | row present, volume kept |
| `test_pgvector_available` | Query `pg_available_extensions` | `vector` listed |
