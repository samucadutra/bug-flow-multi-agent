# BugFlow v2

## 1. Executive Summary

BugFlow v2 is a local demo that shows how a team of AI agents can collaborate to triage a software bug. A user opens a bug, clicks **Triage**, and watches five specialist agents work in sequence: a Component Classifier, a Severity Classifier, a Technical Analyst, a Resolution Manager and a Bug Documenter. Each agent's real input, structured output, status and duration are visible live in the UI. When the run ends, the bug has a classified component and severity, a technical analysis, a resolution plan and a rendered Markdown/HTML report with a Mermaid diagram.

The product is for three audiences: a **demo presenter** who needs a reliable, visual demonstration, a **developer** who wants to learn how a multi-agent system is built and validated, and a **tech lead** who wants to judge whether the concept is credible. It is a rebuild from scratch of an earlier Portuguese CLI pipeline ("BugFlow Multi Agents") whose agents never received the bug text, so every report it produced was fiction. v2 fixes this and every other known defect (section 2), and adds a web UI, a local database and a CLI with full UI parity.

The system is a monorepo: a **FastAPI** backend (CrewAI agents, SQLAlchemy, background jobs, report rendering, a Typer CLI), a **Next.js** frontend (App Router, TypeScript), and **PostgreSQL with pgvector** in Docker Compose. Only an OpenAI API key is needed from outside. CLI and API are thin surfaces over one shared service layer, so behavior never diverges. This is a **local single-user demo, not a production system**: no authentication, no SLAs, no cloud deployment.

**Project-wide rules (apply to every feature):**
- **Language:** everything is in English: identifiers, comments, docstrings, database names, enum codes (English `snake_case`), API paths, UI copy, LLM prompts, log messages, CLI output, SQL, file names, commit messages and documentation. Seed data is in English.
- **Secrets:** `OPENAI_API_KEY` and database credentials live only in backend environment configuration. They are never printed, logged, returned by the API or exposed to the browser.
- **Python project root:** `backend/` is the uv project. All Python commands (`uv run ruff format .`, `uv run ruff check .`, `uv run pytest`, `uv run bugflow ...`) run from `backend/`.
- **Spec folders:** the spec-writer skill writes feature folders to `docs/F<ID>-<name>/`. This differs from `AGENTS.md`, which refers to `specs/NNN-feature-name/`. This is an open conflict to resolve before specs are generated (see `docs/execution-guide.md`).

## 2. Problem and Opportunity

### The Problem

**The original agents invented their input**
- Task text had no `{placeholder}`, so no agent ever saw the bug. All reports described invented bugs (defect C1).
- Results were scraped from only the last task's free text with string matching, and matched common words as labels (C2).
- Unknown components silently became "Backend" and unknown severities "Minor"; a failed insert was retried with a default (C3).

**Results were lost or wrong**
- The technical analysis was computed and never stored; justifications and impact were dropped (H3).
- Every report was marked "resolved" regardless of the plan (H5).
- Markdown extraction had an off-by-one error, and LLM-written HTML and Mermaid were never validated (H1, M4).
- Each bug used many independent connections and transactions, so partial writes were possible (M1).

**The design was inconsistent and fragile**
- The SQL schema and the seed script drifted apart (H2). Vocabulary differed between SQL, seed and prompts (M2).
- Vector search was never used during triage, only open bugs were indexed, and a deprecated OpenAI API was used (H4).
- Classification ran at temperature 0.7 (M5). Fictional developer names were assigned (M3).

**It was hard to run, show and trust**
- It required a cloud Postgres (Neon) and a cloud vector index (Pinecone): two extra accounts for a local demo.
- It was a CLI only, so a viewer could not watch the agents work.
- A test script printed the full database URL including the password (L2).

### The Opportunity

| Problem | v2 solution |
|---|---|
| Agents never saw the bug (C1) | Every agent task includes the real bug fields; a test fails if a template lacks them (F05). The Agent trace shows each agent's actual input (F12). |
| Free-text scraping (C2), silent fallbacks (C3) | Each agent returns a Pydantic-validated structured output; invalid output fails the bug visibly with a stored error and one re-ask at most (F05). |
| Lost results (H3), fake "resolved" (H5), template bugs (H1, M4) | Everything is persisted; reports and Mermaid are rendered from templates and stored data; status comes only from the resolution plan (F05, F07). |
| Partial writes (M1) | One transaction per bug for all results (F05). |
| Schema drift (H2), vocabulary drift (M2) | One migration source and one canonical enum module used by DB, API, prompts, seed and UI (F02, F09, F10). |
| Unused vector search (H4) | All bugs are indexed in pgvector with `text-embedding-3-small`; similar past bugs feed the Technical Analyst (F04, F05). |
| Temperature (M5), names (M3), secrets (L2) | Temperature ≤ 0.2; team plus assignee profile; secret-safe logging and responses (F01, F05). |
| No UI, cloud accounts | Next.js UI with live Agent trace, local Postgres in Docker, only an OpenAI key needed (F01, F10–F14). |

**Differentiator:** the demo makes the *process* visible and trustworthy: real inputs, validated outputs, visible failures, and an identical CLI and UI for every operation.

## 3. Target Audience

### Primary Users

**Demo presenter**
- Needs a reliable demo that starts in about 5 minutes and does not break on stage.
- Wants to narrate each agent's work live and re-run the same bug (reopen).
- Needs a clear reset between sessions.

**Learner / developer**
- Wants to read the code and understand how agents, prompts, validation and persistence fit together.
- Wants to learn the CLI while using the UI (Console view shows the equivalent command).
- Wants a small, well-tested codebase with a clear service layer.

**Tech lead evaluating the concept**
- Wants evidence that reports match the bug (inspect real agent inputs and outputs).
- Wants to force a failure and see it surface rather than be hidden.
- Wants to see similar past bugs influence the analysis.

### Behavioral Profile

All three run everything on one developer machine, as a single user, with Docker and an OpenAI key. They are technical, comfortable with a terminal and a browser, and value transparency over polish. Nobody needs login, roles or concurrency across users.

## 4. Objectives

**Product Objectives**
1. **Deliver** a working local demo from a fresh clone in 5 minutes.
2. **Prove** that agents see and use the real bug content.
3. **Show** the agents' work live and make failures visible.
4. **Guarantee** that every CLI operation is also available in the UI with identical effect.
5. **Protect** credibility with a small, enforced quality bar (tests, lint, no secret leaks).

**Success Metrics**

| Objective | Metric | Measurement condition |
|---|---|---|
| 1 | Quickstart takes ≤ 5 minutes and ≤ 8 commands | Fresh clone with Docker and a valid key, following the README; time from clone to seeded UI. |
| 2 | 100% of triage runs store AG1 input containing the exact bug description, steps, version and environment; 0 task templates without bug placeholders | Automated test over all templates plus an end-to-end test with a mocked LLM. |
| 3 | Each of the 5 agent steps appears in the Agent trace with input, output, status and duration; trace updates within 2 s of a step finishing | Manual run on a seeded bug; automated check of persisted step rows. |
| 3 | An invalid agent output yields status `failed`, 0 result rows and an error visible in the Errors tab | Mocked LLM returning an invalid enum value. |
| 4 | 9 of 9 rows of the parity table work from CLI, API and UI; parity test passes | Automated parity test plus manual walkthrough. |
| 5 | 0 secrets in logs, API responses or CLI output; tests green; Ruff and ESLint clean | Automated tests and lint run on the full repo. |

## 5. User Stories

### F01. Project Foundation
- As a developer, I want to run `docker compose up -d` and get a healthy Postgres with pgvector so that I need no cloud database
- As a developer, I want one `.env.example` listing every variable so that I know what to configure
- As a developer, I want Ruff, pytest and a config module in place so that every later feature starts from a clean base
- As the system, I want secrets redacted from logs so that no credential is ever printed
- As a developer working in a parallel git worktree, I want an environment script that gives each worktree its own ports and database so that parallel runs do not collide

### F02. Schema, Migrations and Seed
- As a developer, I want `db init` to create the whole schema from one migration source so that schema and seed cannot drift
- As a presenter, I want `db seed` to load 20 realistic bugs so that I can demo immediately
- As a presenter, I want `db reset` to wipe everything so that I can start a clean demo
- As the system, I want database-level constraints on every enum so that invalid values cannot be stored

### F03. Service Layer, Bug Management and CLI Skeleton
- As a developer, I want a `bugflow` CLI with `check` and `db` commands so that I can operate the demo from a terminal
- As a user, I want to create, view, edit (while open), list, filter, sort and search bugs through services so that every surface behaves the same
- As the system, I want every operation to create a run record with log lines so that progress is persisted and visible later
- As a presenter, I want `check` to tell me whether the database, vector search and LLM are reachable so that I know the demo will work

### F04. Embeddings Index and Similar Search
- As a presenter, I want `index` to embed all bugs with progress so that similar-bug search works
- As a user, I want `search "<text>"` to return ranked similar bugs so that I can find related issues
- As the system, I want a bug's own embedding refreshed when its text changed so that similar-bug results are never stale

### F05. Triage Agents
- As a presenter, I want `triage --bug ID` to run five agents on a real bug so that all result sets are produced
- As a tech lead, I want each agent's input and structured output stored so that I can verify what the agent saw
- As a tech lead, I want an invalid agent output to fail the bug visibly with no partial results so that I can trust successes
- As the system, I want to reject a triage on a bug already being processed so that results are never corrupted
- As the system, I want similar past bugs passed to the Technical Analyst so that analysis uses history

### F06. Background Runs and Progress
- As a presenter, I want triage, index and seed to run in the background and return a run ID immediately so that the UI never freezes
- As a user, I want "triage all" to process every open bug one at a time and continue after a failure so that one bad bug does not block the rest
- As the system, I want runs interrupted by a crash marked failed at startup so that no bug stays stuck in `processing`
- As the system, I want an event stream of steps and logs for any run so that a run started in the CLI is also visible in the UI

### F07. Report Rendering
- As a user, I want a Markdown and an HTML report for each triaged bug so that I can share the outcome
- As a tech lead, I want reports built only from stored data so that no report mentions content absent from the bug
- As a user, I want a Mermaid flow diagram generated from structured data so that the diagram is always valid
- As a developer, I want `report <id>` in the CLI so that I can print or export the report

### F08. Reopen
- As a presenter, I want to reopen a processed or failed bug so that I can run the demo again on the same bug
- As the system, I want reopen to delete results and report in one transaction while keeping run history so that audit data remains
- As a user, I want reopen to ask for confirmation so that I do not delete results by accident

### F09. API, Operations and Parity
- As a UI developer, I want a documented REST API under `/api/v1` so that the frontend never touches the database, the LLM or secrets
- As a user, I want operations to return `202` with a run ID and stream progress so that I can watch long jobs
- As a maintainer, I want an automated parity test so that no CLI command can exist without an API route
- As a presenter, I want `bugflow serve` to start the API on localhost so that setup is one command

### F10. Frontend Shell and Dashboard
- As a user, I want a Next.js app with navigation and a Dashboard so that I see counts by status, component and severity and the latest runs
- As a user, I want loading, empty and error states and a responsive layout so that the app is usable on a small screen
- As the system, I want enum codes and labels loaded from the API so that the UI never duplicates vocabulary

### F11. Bug List, Create and Detail
- As a user, I want to filter, sort and text-search the bug list so that I find bugs quickly
- As a user, I want to create a bug with a form and edit it while open so that I can demo my own example
- As a presenter, I want a bug detail page with Overview, Analysis and plan, Similar bugs, Report and Errors tabs so that I see everything about a bug
- As a presenter, I want Triage, Reopen and Download report actions on the detail page so that I can run the full flow from one place

### F12. Agent Trace View
- As a presenter, I want a step-by-step view of the five agents so that the audience sees who does what
- As a presenter, I want each step to show role, input, structured output, status and duration, updating live, so that I can narrate the run
- As a tech lead, I want to open the trace of past runs so that I can compare runs after a reopen

### F13. Operations Console
- As a presenter, I want an Operations page with check, init, seed, reset and index so that I can prepare the demo without a terminal
- As a developer, I want a Console view showing the equivalent CLI command and streaming the log so that I learn the CLI while using the UI
- As a presenter, I want reset to ask for confirmation so that I do not wipe data by accident

### F14. Search Page
- As a user, I want a search page where I type a text and get ranked similar bugs so that I can explore the index
- As a user, I want each result to link to its bug and show its similarity score so that I understand the ranking

### F15. End-to-End Smoke Test and Quickstart
- As a new user, I want a README quickstart with at most 8 commands so that I can run the demo in 5 minutes
- As a maintainer, I want an API smoke test and an end-to-end checklist so that the demo's main path is verified before presenting
- As a maintainer, I want the parity table and quickstart verified against the finished system so that documentation matches reality

## 6. Functionalities

### F01. Project Foundation

**Provides:**
- Settings loaded only through `bugflow.config`: database URL, OpenAI key, model names, timeouts, retry count, similar-bug count, API host/port, CORS origins, log level (used by F02)
- Structured logger with secret redaction (used by F02)
- Running Postgres with pgvector reachable at the configured URL (used by F02)

**Capabilities:**
- **Monorepo layout:** `backend/` (FastAPI, CrewAI, CLI, migrations, tests), `frontend/` (created in F10), `docs/` (PRD, feature folders, execution guide), `docker-compose.yml`, `.env.example`, `scripts/`, root `README.md` (stub, completed in F15).
- **Backend project:** uv project in `backend/` with Python 3.12, package `bugflow`, console script `bugflow`, Ruff (format and lint), pytest with an `integration` marker (integration tests run only on request and use `TEST_DATABASE_URL`, never `DATABASE_URL`). Dependencies limited to those listed in the active plan.
- **Config module:** `bugflow.config` using pydantic-settings is the only code that reads environment variables. It validates values, never echoes secret values (repr shows `***`), and fails fast with an English message naming the missing variable (not its value).
- **Environment variables:**

  | Variable | Service | Purpose | Default |
  |---|---|---|---|
  | `DATABASE_URL` | backend | Postgres connection | `postgresql+psycopg://bugflow:bugflow@localhost:5432/bugflow` |
  | `TEST_DATABASE_URL` | backend tests | Separate DB for integration tests | `.../bugflow_test` |
  | `OPENAI_API_KEY` | backend | LLM and embeddings key | empty in `.env.example` |
  | `OPENAI_MODEL` | backend | Chat model for agents | `gpt-4o-mini` |
  | `OPENAI_EMBEDDING_MODEL` | backend | Embedding model | `text-embedding-3-small` |
  | `LLM_TIMEOUT_SECONDS` | backend | Per-call timeout | `60` |
  | `LLM_MAX_RETRIES` | backend | Transient-error retries | `2` |
  | `SIMILAR_BUGS_K` | backend | Similar bugs passed to AG3 | `5` |
  | `API_HOST`, `API_PORT` | backend | Bind address | `127.0.0.1`, `8000` |
  | `CORS_ORIGINS` | backend | Allowed frontend origin | `http://localhost:3000` |
  | `LOG_LEVEL` | backend | Verbosity | `INFO` |
  | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`, `POSTGRES_PORT` | compose | Container DB setup | `bugflow` ×3, `5432` |
  | `NEXT_PUBLIC_API_BASE_URL` | frontend | Backend base URL (public by design, never a secret) | `http://localhost:8000/api/v1` |

- **`.env.example` policy:** contains every variable with placeholders and no real secrets. `.env` is git-ignored. The frontend never reads backend secrets.
- **Docker Compose:** one service `db` using `pgvector/pgvector:pg17`, port bound to `127.0.0.1`, named volume `bugflow_pgdata`, health check with `pg_isready`. Apps run on the host (decision: simplest and most reliable for a demo).
- **Parallel-worktree isolation:** `scripts/resolve-env.sh` derives a numeric `APP_OFFSET` (0–99) from the current worktree path (0 for the main checkout) and exports/prints per-worktree values: Postgres host port (`5432 + offset`), database name suffix, compose project name, API port (`8000 + offset`) and frontend port (`3000 + offset`). This is required by `/implement-and-evaluate-tmux` so parallel teams do not collide.
- **Logging:** one line per event with timestamp, level, run ID when relevant, and message, in English. A redaction filter masks the API key and any password in connection strings.
- **Quality gate:** `uv run ruff format .`, `uv run ruff check .`, `uv run pytest` pass on the empty skeleton, with one smoke test that imports the package.

**Experience:** A developer copies `.env.example` to `.env`, sets `OPENAI_API_KEY`, runs `docker compose up -d`, waits until `docker compose ps` shows `db` as healthy (within about 15 seconds on a warm image), then runs `uv run bugflow --version` from `backend/`. Messages are in English.

**Error Handling:**
- Missing `OPENAI_API_KEY`: the app still starts; operations that need it fail with "OPENAI_API_KEY is not set"; the value is never printed.
- Missing or malformed `DATABASE_URL`: fail fast with "DATABASE_URL is missing or invalid" without echoing the value.
- Host port already in use: compose fails; README explains setting `POSTGRES_PORT` or using `resolve-env.sh`.
- A log call receives a string containing the key: the redaction filter masks it (`***`).

### F02. Schema, Migrations and Seed

**Consumes:**
- F01: settings (database URL), logger, running Postgres with pgvector

**Provides:**
- Schema (tables below) created from one migration source (used by F03)
- Canonical enum module: codes, English labels, definitions (used by F03)
- Packaged 20-bug dataset and the service functions `init_db`, `seed_db`, `reset_db` (used by F03)

**Capabilities:**
- **Migrations:** Alembic migrations in `backend/`. The first migration runs `CREATE EXTENSION IF NOT EXISTS vector`. `init_db` applies migrations and is idempotent. The seed script uses the same models; no second schema definition exists (H2).
- **Canonical enums (codes stored, labels displayed; each protected by a database constraint):**

  | Enum | Codes |
  |---|---|
  | `BugStatus` | `open`, `processing`, `processed`, `failed` |
  | `Environment` | `production`, `staging`, `development`, `testing` |
  | `Team` | `frontend`, `backend`, `data`, `devops`, `security`, `qa`, `support`, `product` |
  | `Component` | `frontend` (browser-side logic, rendering, state), `backend` (server-side business logic and APIs), `database` (queries, schema, integrity, data-store performance), `devops` (build, release, deployment, configuration), `security` (authentication, authorization, data exposure, vulnerabilities), `integration` (communication with external systems), `ui_ux` (layout, visual design, usability, wording), `infrastructure` (servers, networking, containers, capacity) |
  | `Severity` | `critical` (data loss, security breach, or complete failure of a core function with no workaround), `major` (a significant function broken or degraded for many users, or costly workaround), `minor` (cosmetic or low-impact; core functions work) |
  | `ResolutionStatus` | `planned`, `needs_info`, `deferred`, `wont_fix` |
  | `Priority` | `urgent`, `high`, `medium`, `low` |
  | `Seniority` | `junior`, `mid`, `senior`, `lead` |
  | `RunType` | `triage`, `index`, `seed`, `init`, `reset` |
  | `RunStatus` | `queued`, `running`, `succeeded`, `failed` |
  | `StepStatus` | `pending`, `running`, `succeeded`, `failed`, `skipped` |

- **Tables:**
  - `bugs`: id, title (≤120), description (≤5,000), reproduction_steps (≤5,000), system_version (≤50), environment, reporting_team, status, opened_at, updated_at.
  - `bug_embeddings`: bug_id (PK), embedding `vector(1536)`, text_hash, embedded_at.
  - `component_classifications`, `severity_classifications`, `technical_analyses`, `resolution_plans`, `bug_reports`: one current row per bug (bug_id PK), each with `run_id`. `technical_analyses` stores root_cause, technical_impact, debugging_approach, proposed_solution, side_effects and referenced_similar_bug_ids. `resolution_plans` stores resolution_status, assigned_team, assignee_profile (role, seniority, skills), target_days, priority, notes. `bug_reports` stores AG5 prose plus nullable `markdown` and `html` (filled by F07).
  - `runs` (id, type, bug_id nullable, status, progress_done, progress_total, error, started_at, finished_at), `run_steps` (id, run_id, position, agent_key, status, input JSON, output JSON, error, started_at, duration_ms), `run_logs` (id, run_id, logged_at, level, message).
- **Seed dataset:** 20 realistic bugs written in English, all `open`, fixed `opened_at` dates over a 90-day window. Distribution (design intent only; labels are not stored and never asserted against LLM output):

  | Dimension | Distribution |
  |---|---|
  | Intended component | frontend 3, backend 4, database 3, devops 2, security 2, integration 2, ui_ux 2, infrastructure 2 |
  | Environment | production 8, staging 5, development 4, testing 3 |
  | Reporting team | qa 5, support 5, product 2, frontend 2, backend 2, devops 2, data 1, security 1 |
  | Intended severity | critical 4, major 9, minor 7 |

  Examples (3 of 20):
  1. *Checkout button does nothing on Safari 17* — clicking "Place order" shows no response and no network call. Steps: add an item, go to checkout in Safari 17, click the button. Version web 3.8.2. Environment production. Reported by support.
  2. *Nightly sales report times out after index change* — the report query now takes over 10 minutes and the job is killed. Steps: run the nightly job after migration 0042. Version api 2.14.0. Environment staging. Reported by data.
  3. *API token visible in browser network logs* — the access token appears in the query string of the export URL. Steps: open the export page and inspect the network tab. Version web 3.8.0. Environment production. Reported by security.
- **`seed_db`** is idempotent: if the 20 seed bugs already exist (matched by title), none are duplicated. **`reset_db`** drops all application tables and recreates the schema; it does not seed.

**Experience:** After `docker compose up -d`, a developer runs the service functions (exposed in F03 as `bugflow db init`, `db seed`, `db reset`). `init` prints applied migrations; `seed` prints `Seeded 20 bugs` (or `20 bugs already present, nothing to do`); `reset` requires confirmation (F03).

**Error Handling:**
- Database unreachable: error "Cannot connect to the database" without the URL.
- pgvector extension not available in the image: `init` fails with "pgvector extension is not available; use the pgvector/pgvector image".
- Migration fails halfway: the migration runs in a transaction and is rolled back; the error is shown.
- Seed run twice: no duplicates and exit code 0.
- Insert with an enum value outside the allowed list: rejected by the database constraint.

### F03. Service Layer, Bug Management and CLI Skeleton

**Consumes:**
- F02: schema, canonical enums, `init_db`, `seed_db`, `reset_db`, run tables

**Provides:**
- Service-layer conventions: services take a session and typed inputs, return Pydantic models, and write progress through a run recorder (used by F04, F05)
- Run recorder: create run, update progress, append log line, finish with status or error (used by F04, F05)
- Bug services: create, get, update (while open), list with filters/sort/search/pagination (used by F04, F05, F09)
- Health check service (database, pgvector, LLM) (used by F09)
- `bugflow` CLI app with command registration and output helpers (used by F04, F05, F07, F08)

**Capabilities:**
- **Bug fields and limits:** title 1–120, description 1–5,000, reproduction steps 1–5,000, system version 1–50 characters; environment and reporting team from the enums. New bugs start `open`; `opened_at` defaults to now.
- **Rules:** invalid input is rejected with per-field messages. Editing is allowed only while `open`, otherwise a state-conflict error. Allowed status transitions: `open → processing → processed | failed`; `processed | failed → open` (reopen only).
- **List:** filters `status`, `component`, `severity`, `environment`, `reporting_team`; text search over title and description (case-insensitive substring); sort by `opened_at`, `status`, `severity`; pagination `page` (default 1) and `page_size` (default 20, max 100) with `total`.
- **`check`:** reports separately database reachable, pgvector available, and LLM reachable (one minimal call). A missing key is a failed check with a clear message, not a crash. Never prints secrets.
- **Run recorder:** every operation (`init`, `seed`, `reset`, later `index` and `triage`) creates a run record with status, timestamps, progress counters and log lines. `reset` writes its own run record after recreating the schema.
- **CLI:** Typer app `bugflow` with `check`, `db init`, `db seed`, `db reset [--yes]`. Commands only parse arguments, call a service and print; no business logic. Exit code 0 on success, non-zero on failure. `--help` lists all commands with English one-line descriptions.
- **Architecture rule:** business logic lives only in the service layer; the CLI and the API (F09) are thin surfaces.

**Experience:** `uv run bugflow check` prints three lines (`database: ok`, `vector search: ok`, `llm: ok` or `failed: <reason>`). `uv run bugflow db reset` asks `This deletes all data. Type 'yes' to continue:`; `--yes` skips the prompt.

**Error Handling:**
- `db reset` without confirmation: aborts with exit code 1 and deletes nothing.
- Edit of a non-open bug: state-conflict error "Bug 7 is not open and cannot be edited".
- `check` with unreachable database: reports the failure, still checks the other items.
- A service raises an unexpected error mid-run: the run is marked `failed` with the error text (no secrets) and the CLI exits non-zero.

### F04. Embeddings Index and Similar Search

**Consumes:**
- F03: bug services, run recorder, service-layer conventions, CLI app

**Provides:**
- Index service `index_all_bugs` with progress and `ensure_embedding(bug)` (used by F05)
- Similar-bug search `search_similar(text, k)` and `similar_to_bug(bug_id, k)` (used by F05, F09)
- Shared LLM client wrapper with timeout and bounded retry (used by F05)

**Capabilities:**
- **Embedded text:** built from title, description, reproduction steps, system version and environment (enriched text), same builder for indexing and queries. A `text_hash` detects stale vectors.
- **Embeddings:** current OpenAI Python SDK, `text-embedding-3-small`, 1,536 dimensions, stored in pgvector; cosine similarity.
- **`index`:** embeds **all** bugs regardless of status; re-runnable (rebuild replaces vectors); batches of up to 20 texts per API call; progress `done / total` and a log line per batch.
- **`search`:** top K (default 5, maximum 20) with bug id, title, status and similarity score in descending order. `similar_to_bug` excludes the bug itself and returns an empty list (not an error) if no other bug is indexed.
- **`ensure_embedding(bug)`:** re-embeds when the embedding is missing or its hash differs from the current text.
- **CLI:** `bugflow index` and `bugflow search "<text>" [--limit N]`.
- **Shared LLM client wrapper:** one wrapper around the OpenAI SDK for chat and embeddings with timeout 60 s and up to 2 retries with backoff for transient errors (network, 429, 5xx). F05 reuses it for the agents.

**Experience:** `bugflow index` prints `Indexed 20/20 bugs`. `bugflow search "button does nothing"` prints a table of up to 5 rows: score, id, title, status.

**Error Handling:**
- Missing/invalid API key: run fails with "OpenAI authentication failed" (key never shown), no partial vectors for the failed batch.
- Rate limit or network error: retried up to 2 times with backoff, then the run fails with the reason.
- Empty search text: rejected with "Search text must not be empty".
- Search before indexing: returns an empty result with a hint "No bugs are indexed; run index".

### F05. Triage Agents

**Consumes:**
- F03: bug services, run recorder, service-layer conventions, CLI app
- F04: `ensure_embedding`, `similar_to_bug`, shared LLM client wrapper

**Provides:**
- Triage service `triage_bug(bug_id)` and the bug-claim operation (used by F06)
- Stored result rows per bug: component, severity, analysis, plan, report prose (used by F07, F08)
- Run steps with persisted input and output per agent (used by F06)
- Pipeline hook where report rendering runs inside the same transaction (used by F07)

**Capabilities:**
- **Pipeline:** five CrewAI agents run **sequentially**: AG1 Component Classifier → AG2 Severity Classifier → AG3 Technical Analyst → AG4 Resolution Manager → AG5 Bug Documenter. Model from `OPENAI_MODEL`, **temperature ≤ 0.2**, agents have **no tools** (no web, file or shell access).
- **Claim:** triage atomically claims the bug with a conditional update (`open` or `failed` → `processing`). A bug in `processing` or `processed` is rejected with a state-conflict error, regardless of whether the CLI or the API started it.
- **Before AG3:** `ensure_embedding` for the bug, then retrieve up to `SIMILAR_BUGS_K` (default 5) similar bugs excluding itself, with id, title, similarity score and, if already triaged, their component, severity, root cause and proposed solution. If none exist, the prompt says "no similar bugs found".
- **Real input (C1):** every task template contains placeholders for title, description, reproduction steps, system version, environment, reporting team and opened date. The bug text is wrapped in explicit delimiters and declared as data, never instructions (prompt-injection awareness). A unit test fails if any template lacks the bug placeholders.
- **Structured output (C2):** each agent returns a Pydantic model; no regex or substring scraping. Enum values must match exactly; there is **no normalization to the closest value and no defaults** (C3).
- **Invalid output:** one re-ask with the validation error; if still invalid, the step fails, remaining steps are `skipped`, the run fails, the bug becomes `failed`, no result rows are written, and the failing agent and error are stored.
- **Cross-field validation:** AG3 `referenced_similar_bug_ids` must be a subset of the ids supplied; AG4 `target_days` in 1–90; required lists non-empty.
- **LLM calls:** timeout 60 s; up to 2 retries for transient errors (network, 429, 5xx) with backoff.
- **Persistence (M1, H3):** run steps and logs are written incrementally so the trace is live. All results (component, severity, analysis, plan, report prose) and the status change to `processed` are written in **one transaction** at the end; everything each agent produced is stored.
- **Agent specification** (bug input = id, title, description, reproduction steps, system version, environment, reporting team, opened date):

  **AG1 Component Classifier** — input: bug.

  | Field | Type | Rules |
  |---|---|---|
  | `component` | enum Component | exact code |
  | `justification` | text | 1–600 chars, cites the bug text |

  **AG2 Severity Classifier** — input: bug, AG1 output.

  | Field | Type | Rules |
  |---|---|---|
  | `severity` | enum Severity | exact code |
  | `justification` | text | 1–600 chars |
  | `user_impact` | text | 1–400 chars, only impact implied by the bug text |

  **AG3 Technical Analyst** — input: bug, AG1, AG2 outputs, similar bugs.

  | Field | Type | Rules |
  |---|---|---|
  | `root_cause` | text | 1–800 chars, a hypothesis grounded in the bug text |
  | `technical_impact` | text | 1–600 chars |
  | `debugging_approach` | list of text | 1–6 items |
  | `proposed_solution` | text | 1–800 chars |
  | `side_effects` | list of text | 0–5 items |
  | `referenced_similar_bug_ids` | list of int | subset of supplied ids |

  **AG4 Resolution Manager** — input: bug, AG1–AG3 outputs. Never outputs a person's name (M3).

  | Field | Type | Rules |
  |---|---|---|
  | `resolution_status` | enum ResolutionStatus | exact code |
  | `assigned_team` | enum Team | exact code |
  | `assignee_profile` | object | `role` text, `seniority` enum Seniority, `skills` list of 1–6 text |
  | `target_days` | int | 1–90; the report template computes the date |
  | `priority` | enum Priority | exact code |
  | `notes` | text | 0–600 chars |

  **AG5 Bug Documenter** — input: bug, AG1–AG4 outputs. Produces **prose only** (no Markdown, HTML or Mermaid), and may only restate facts present in its input.

  | Field | Type | Rules |
  |---|---|---|
  | `executive_summary` | text | 1–600 chars, plain text |
  | `key_takeaways` | list of text | 1–5 items |
  | `next_steps` | list of text | 1–5 items |

  *Why AG5 stays an LLM agent:* it keeps the five-agent story and gives the report readable prose, while templates (F07) remove the original markup defects (H1, M4).
- **CLI:** `bugflow triage --bug ID` and `bugflow triage --all` (all `open` bugs, one at a time, continue after a failure).
- **Tests:** the C1 placeholder test; enum validation including rejection of near-miss values; one end-to-end triage with a mocked LLM asserting all result rows, five run steps and AG1's stored input containing the exact bug fields.

**Experience:** `bugflow triage --bug 3` prints one line per step (`AG1 Component Classifier: backend`, …) and ends with `Bug 3 processed` or `Bug 3 failed: AG2 returned invalid severity 'high'`.

**Error Handling:**
- Agent returns an invalid enum or malformed JSON: one re-ask, then the bug is `failed`, nothing is stored except steps, logs and the error.
- LLM timeout or repeated 5xx: step fails after 2 retries; run and bug `failed` with the reason.
- Triage on a `processing` bug: rejected immediately, bug state unchanged.
- Process killed mid-run: the bug stays `processing` until F06 recovery marks it `failed`; no result rows exist because they are written only at the end.
- Missing API key: run fails at AG1 with "OpenAI authentication failed"; bug becomes `failed`.

### F06. Background Runs and Progress

**Consumes:**
- F05: triage service, bug claim, run steps and logs

**Provides:**
- Background runner `start_run(kind, params)` returning a run ID immediately (used by F09)
- Event source `iter_run_events(run_id, after)` returning steps, logs and run status changes from persisted rows (used by F09)
- Startup recovery of interrupted runs (used by F09)

**Capabilities:**
- **Background execution:** triage, index and seed run in-process background tasks (no external queue); the run record is created before returning. Multiple triage requests are queued and executed one at a time.
- **Concurrency rule:** a second triage for a bug that is `processing` or `processed` is rejected before any run is created. This holds across processes (CLI and API) because the claim is a conditional database update.
- **"Triage all":** one run per `open` bug, executed sequentially; a failed bug does not stop the batch; returns the list of run IDs.
- **Recovery:** at backend start, any run left `queued` or `running` is marked `failed` with reason `interrupted`, and its bug returns from `processing` to `failed`.
- **Event source:** reads persisted `run_steps` and `run_logs` after a cursor, so a run started in the CLI can be streamed by the API. Poll interval inside the stream: 500 ms.

**Experience:** a caller receives a run ID within 1 s; polling the run shows status moving `queued → running → succeeded | failed` with progress counters.

**Error Handling:**
- Backend restarts during a run: recovery marks it `failed` (`interrupted`); the user can triage again.
- Two simultaneous triage requests for one bug: exactly one succeeds, the other gets a state-conflict error.
- Background task raises an unexpected exception: the run is marked `failed` with the error text; the bug is returned to `failed`; the process keeps serving.

### F07. Report Rendering

**Consumes:**
- F05: bug fields, stored results (component, severity, analysis, plan), AG5 prose, pipeline hook

**Provides:**
- Rendered Markdown and HTML report strings per bug, stored in `bug_reports` (used by F09)
- `render_report(bug_id)` and `get_report(bug_id, format)` services (used by F09)

**Capabilities:**
- **Templates:** Markdown and HTML are rendered from templates using stored data only (H1, M4). LLM text never contains markup. The renderer runs inside the F05 transaction, so a report exists if and only if the other results exist.
- **Content:** bug fields; component, severity and justifications; root cause, impact, debugging approach, proposed solution, side effects; similar bugs referenced; resolution plan (status, team, assignee profile, priority, notes, deadline); AG5 summary, takeaways and next steps. The resolution status is displayed from the plan (H5); there is no "resolved" flag.
- **Deadline:** computed by the template as run completion date + `target_days`; the LLM never outputs a calendar date.
- **Mermaid:** a flow diagram generated from structured data: bug → component → severity → assigned team → resolution status. Labels come from canonical enum labels; text is escaped; the diagram is valid for any enum combination.
- **HTML:** standalone file; Mermaid is loaded from a pinned CDN script (open question: offline mode is out of scope).
- **CLI:** `bugflow report <id> [--format md|html] [--output PATH]` prints to stdout or writes a file.
- **Tests:** rendering with a fixture for every enum combination of component × severity yields valid Mermaid text; report contains the bug title and description verbatim; report does not contain the word "resolved" unless the plan status says so.

**Experience:** `bugflow report 3 --format md` prints the Markdown; the report starts with the bug title (no stray characters).

**Error Handling:**
- Report requested for an unprocessed bug: "Bug 3 has no report; triage it first" (not-found).
- Rendering fails (template error): the triage transaction rolls back and the bug becomes `failed` with the error.
- Special characters (backticks, `<`, `|`, quotes) in bug text or agent prose: escaped in HTML, safe in Markdown tables and Mermaid labels.

### F08. Reopen

**Consumes:**
- F05: result tables (component, severity, analysis, plan, report prose in `bug_reports`), bug status lifecycle

**Provides:**
- `reopen_bug(bug_id)` service (used by F09)

**Capabilities:**
- Reopen deletes the bug's component, severity, analysis, plan and report rows and sets the status to `open` in **one transaction**. Embeddings and run history (runs, steps, logs) are kept.
- Allowed from `processed` and `failed`; rejected with a state-conflict error when `processing` or already `open`.
- Reopen does not create a run record; the existing run history is left unchanged.
- **CLI:** `bugflow reopen <id> [--yes]`; without `--yes` it asks for confirmation naming what will be deleted.

**Experience:** `bugflow reopen 3` prints `This deletes the results and report of bug 3. Type 'yes' to continue:` then `Bug 3 reopened`.

**Error Handling:**
- Unconfirmed reopen: nothing is deleted, exit code 1.
- Reopen of a `processing` bug: rejected; data untouched.
- Failure during deletion: transaction rolls back; results and status remain as before.
- Unknown bug id: not-found error.

### F09. API, Operations and Parity

**Consumes:**
- F03: bug services, health check, init/seed/reset services, run recorder
- F04: index and search services
- F06: background runner, event source, startup recovery
- F07: report services
- F08: reopen service

**Provides:**
- REST API under `/api/v1` with OpenAPI at `/docs` (used by F10)
- SSE and polling progress endpoints (used by F10)
- Canonical enums endpoint and dashboard stats endpoint (used by F10)
- `bugflow serve` command that starts the API (used by F15)

**Capabilities:**
- **Server:** FastAPI binding to `127.0.0.1:8000` by default; CORS only for the configured frontend origin; no authentication (explicit non-goal, local single user). Recovery from F06 runs at startup.
- **Endpoints** (all under `/api/v1`):

  | Method | Path | Purpose |
  |---|---|---|
  | GET | `/health` | Connectivity check (database, pgvector, LLM) |
  | GET | `/meta/enums` | Canonical enums: codes, labels, definitions |
  | GET | `/stats` | Dashboard counts by status, component, severity |
  | POST | `/admin/db/init` | Create or migrate schema |
  | POST | `/admin/db/seed` | Load the 20 sample bugs (202, run id) |
  | POST | `/admin/db/reset` | Wipe and recreate data; body `{"confirm": true}` |
  | POST | `/admin/index` | Build or rebuild embeddings (202, run id) |
  | GET | `/bugs` | List with filters, sort, search, pagination |
  | POST | `/bugs` | Create a bug |
  | GET | `/bugs/{id}` | Bug detail with results |
  | PATCH | `/bugs/{id}` | Edit while `open` |
  | GET | `/bugs/{id}/similar` | Similar bugs |
  | GET | `/bugs/{id}/runs` | Runs for a bug |
  | POST | `/bugs/{id}/reopen` | Reopen; body `{"confirm": true}` |
  | GET | `/bugs/{id}/report` | Report, `format=json|md|html` |
  | GET | `/search` | Semantic search, `q`, `limit` |
  | POST | `/triage-runs` | Start triage, `{"bug_id": 1}` or `{"all": true}` (202, run ids) |
  | GET | `/runs` | Recent runs, filter by type and status |
  | GET | `/runs/{id}` | Run with steps (polling) |
  | GET | `/runs/{id}/events` | SSE stream of steps and logs |

- **Error model:** `{"error": {"code": "...", "message": "...", "details": []}}` with HTTP 400, 404, 409 (state conflict), 422 (validation, per-field details), 500, 503 (database or LLM unavailable). Messages never include secrets or stack traces.
- **Progress:** SSE at `/runs/{id}/events` emits `step`, `log` and `run` events and closes on a terminal status; clients may poll `/runs/{id}` every 1 s instead.
- **Secrets:** no response contains the API key, connection strings or raw environment values.
- **CLI–UI parity contract:**

  | CLI command | Purpose | Frontend location | API resource |
  |---|---|---|---|
  | `check` | Verify DB, vector search and LLM connectivity | Operations page (Health panel) | `GET /health` |
  | `db init` | Create or migrate the schema | Operations page (button) | `POST /admin/db/init` |
  | `db seed` | Load the 20 sample bugs | Operations page (button, live log) | `POST /admin/db/seed` |
  | `db reset` | Wipe and recreate data (confirm) | Operations page (button, confirm dialog) | `POST /admin/db/reset` |
  | `index` | Build or rebuild embeddings for all bugs | Operations page (button, live log) | `POST /admin/index` |
  | `search "<text>"` | Semantic search for similar bugs | Search page and bug detail Similar bugs tab | `GET /search` |
  | `triage [--bug ID \| --all]` | Run the agent crew on one or all open bugs | Bug detail (Triage) and Bugs list ("Triage all") | `POST /triage-runs` |
  | `reopen <id>` | Delete results and reopen a bug | Bug detail (button, confirm dialog) | `POST /bugs/{id}/reopen` |
  | `report <id>` | View or export the Markdown/HTML report | Bug detail, Report tab and download | `GET /bugs/{id}/report` |

  `bugflow serve` is excluded from parity because it starts a surface rather than performing an operation. The CLI calls a service in the foreground; the API schedules the same service as a background task and returns the run ID; progress is read from persisted run logs.
- **Parity test:** an automated test fails when a CLI command in the table has no registered API route.
- **API smoke test:** health, create bug, list bugs.

**Experience:** a developer runs `uv run bugflow serve`, opens `http://127.0.0.1:8000/docs` and calls any endpoint; long operations return `202` and a run ID immediately.

**Error Handling:**
- Triage for a bug in `processing`: `409` with code `bug_not_claimable`.
- Reset or reopen without `"confirm": true`: `422` and nothing deleted.
- Invalid body or query: `422` with per-field details.
- Database or LLM unavailable: `503` with a safe message.
- Browser origin not allowed: blocked by CORS.

### F10. Frontend Shell and Dashboard

**Consumes:**
- F09: REST API, enums endpoint, stats endpoint, SSE and polling endpoints

**Provides:**
- Next.js app shell with navigation and layout (used by F11, F13, F14)
- Typed API client for all F09 endpoints and run-progress hook (SSE with polling fallback) (used by F11, F12, F13, F14)
- Enum provider (codes, labels, definitions) (used by F11, F13, F14)
- Shared loading, empty and error state components (used by F11, F12, F13, F14)

**Capabilities:**
- **Scaffold:** `frontend/` with Next.js (latest stable major at implementation time, pinned), App Router, TypeScript, ESLint. Runs on the host (`npm run dev`, port 3000). `NEXT_PUBLIC_API_BASE_URL` points to the backend; the browser holds no secrets and calls no LLM.
- **Navigation:** Dashboard, Bugs, Search, Operations.
- **Enums:** loaded once from `/meta/enums`; the UI hard-codes no codes or labels.
- **Dashboard:** counts by status, component and severity (from `/stats`) and the 10 most recent runs with type, status, duration and a link; refreshes on load.
- **Basic UX:** every screen has loading, empty and error states; responsive down to 375 px width. No accessibility audit and no theming requirement.

**Experience:** opening `http://localhost:3000` shows the Dashboard. With an empty database it shows an empty state "No bugs yet. Go to Operations to initialize and seed the database." If the API is down it shows an error banner with a Retry button.

### F11. Bug List, Create and Detail

**Consumes:**
- F10: app shell, API client, enum provider, shared state components

**Provides:**
- Bug detail page with a tab slot "Agent trace" and the latest run ID of the bug (used by F12)

**Capabilities:**
- **Bugs list:** table with title, status, component, severity, environment, team, opened date; filters for status, component, severity, environment, team; sort by opened date, status or severity; text search (debounced 300 ms); pagination (20 per page); "New bug" button; "Triage all" button (confirmation dialog stating the number of open bugs).
- **Bug form:** create, and edit while `open`, with inline field validation using the limits from F03; submit disabled while invalid; edit disabled for non-open bugs.
- **Bug detail tabs:** Overview (all bug fields, status, latest run), Agent trace (slot filled by F12), Analysis and plan (component, severity, analysis, plan with assignee profile), Similar bugs (live search before a run, the list AG3 used after a run), Report (rendered Markdown plus rendered Mermaid diagram), Errors (failed agent, field and message from run steps; empty state when none).
- **Actions:** Triage (disabled unless `open` or `failed`; starts a run and navigates to the Agent trace tab), Reopen (confirmation dialog naming what will be deleted), Download report (`.md` and `.html`).

**Experience:** from the list the user opens a bug, clicks Triage, sees the status change to `processing`, and returns to Overview when `processed`. A failed bug shows a red status and the Errors tab explains why.

**Error Handling:**
- Triage rejected with `409`: toast "This bug is already being processed".
- Edit rejected for a non-open bug: form shows "Only open bugs can be edited".
- Reopen confirmation cancelled: no request is sent.
- API error on any action: error banner with the API message; no silent failure.

### F12. Agent Trace View

**Consumes:**
- F10: API client, run-progress hook, shared state components
- F11: bug detail page tab slot, latest run ID of the bug

**Provides:**
- Agent trace component and standalone route for any run ID (used by F15)

**Capabilities:**
- **Content:** five steps in order (AG1…AG5). Each shows role name, status (`pending`, `running` with spinner, `succeeded`, `failed`, `skipped`), duration in seconds, the **input the agent received** (formatted, expandable) and its **structured output** (field/value view, expandable). AG3's input shows the similar bugs it received.
- **Live updates:** while a run executes the view updates through SSE from `/runs/{id}/events`, falling back to polling every 1 s; each step appears within 2 s of its status change; no reload needed.
- **Past runs:** a run selector lists earlier runs of the bug (for example before and after a reopen); finished runs render from persisted data.
- **Failure:** a failed step is highlighted with its error; later steps show `skipped`.
- **Layout:** vertical timeline on small screens, same content.

**Experience:** the presenter starts a triage and the page shows AG1 spinning, then its output appearing, then AG2, and so on, with a final "Run succeeded in 41 s" banner.

### F13. Operations Console

**Consumes:**
- F10: API client, run-progress hook, enum provider, shared state components

**Capabilities:**
- **Operations page:** panels for check (Health panel showing database, vector search, LLM), db init, db seed, db reset, index. Each shows last status, a button, and live log output for long jobs (seed and index show `done / total` progress).
- **Confirmation:** reset opens a dialog stating that all data will be deleted and requires an explicit confirm.
- **Console view:** for every action, shows the equivalent CLI command (for example `uv run bugflow db seed`) and streams the run's log lines in a terminal-style panel, so users learn the CLI while using the UI. The same panel is available for triage and reopen from the bug detail page via a "Show console" toggle.
- Every parity-table row that is not bug-specific is covered: `check`, `db init`, `db seed`, `db reset`, `index`.

**Experience:** clicking Seed shows `uv run bugflow db seed` in the console header and log lines `Seeded 20 bugs`; clicking Reset shows the dialog first.

**Error Handling:**
- Reset or other action fails: panel shows status `failed` and the error message; logs remain visible.
- Index started with no API key: the Health panel and the log show "OPENAI_API_KEY is not set".
- Reset cancelled: no request is sent.

### F14. Search Page

**Consumes:**
- F10: API client, enum provider, shared state components

**Capabilities:**
- Text box (1–500 characters), result limit selector (5, 10, 20; default 5) and results list showing rank, title, status, environment, similarity score (0–1, two decimals) with a link to the bug.
- Empty state when nothing is indexed ("No bugs are indexed; run Index in Operations") and when there are no matches; loading and error states.
- Search is submitted on Enter or button; requests are not sent for an empty text.

**Experience:** typing "login token leaked" and pressing Enter shows up to 5 ranked bugs within a few seconds; each row opens the bug detail.

### F15. End-to-End Smoke Test and Quickstart

**Consumes:**
- F12: Agent trace view
- F13: Operations page and Console view
- F14: Search page

**Capabilities:**
- **README quickstart** (root `README.md`): prerequisites, then at most 8 commands, for example: `cp .env.example .env` (set the key), `docker compose up -d`, `cd backend && uv sync`, `uv run bugflow db init`, `uv run bugflow db seed`, `uv run bugflow index`, `uv run bugflow serve`, and in another terminal `cd frontend && npm install && npm run dev`. States the 5-minute target, the CLI reference (parity table), how to run tests and lint, and troubleshooting for missing key and port conflicts.
- **API smoke test:** health, create bug, list bugs (automated, runs without real LLM).
- **End-to-end check:** documented manual script covering the full demo path: seed → index → triage a seeded bug → watch the Agent trace → read the report → reopen → search.
- **Verification:** the parity table matches the implemented CLI, API and UI; quality gate (`ruff`, `pytest`, ESLint) passes on the whole repo.
- **Definition of Done per feature (applies to all features):** acceptance criteria met, tests green, lint clean, README section updated, works from both CLI and UI where the parity table requires it, no secret printed or logged.

**Experience:** a new user follows only the README and ends with a seeded database, a running UI, and a first triage run watched live.

## 7. Out of Scope

**Production concerns**
- SLAs, latency or throughput targets, high availability, load or cost governance, compliance, accessibility audit.
- CI/CD pipelines and cloud deployment of any kind.

**Security and tenancy**
- Authentication, authorization, RBAC, multi-user or multi-tenant behavior. The app is local, single-user and bound to localhost.

**Infrastructure**
- Cloud databases (Neon), external vector stores (Pinecone), external job queues (Celery, Redis).
- Running the backend and frontend inside Docker Compose (only Postgres runs in compose in this version).
- Offline-capable HTML reports (Mermaid loads from a CDN).

**Product scope**
- Integrations with real issue trackers (Jira, GitHub Issues, etc.).
- Assigning real, named people to bugs (only a team plus an assignee profile).
- Auto-fixing code, opening pull requests or running code against a bug.
- Deleting bugs, bulk import/export of bugs, attachments, comments.
- LLM providers other than OpenAI.

**UX**
- Theming, internationalization or localization (English only), WCAG audit.

## 8. Dependency Graph

| # | Feature | Priority | Dependencies |
|---|---------|----------|--------------|
| F01 | Project Foundation | 1 | None |
| F02 | Schema, Migrations and Seed | 1 | F01 |
| F03 | Service Layer, Bug Management and CLI Skeleton | 1 | F02 |
| F04 | Embeddings Index and Similar Search | 1 | F03 |
| F05 | Triage Agents | 1 | F03, F04 |
| F06 | Background Runs and Progress | 1 | F05 |
| F07 | Report Rendering | 1 | F05 |
| F08 | Reopen | 2 | F05 |
| F09 | API, Operations and Parity | 1 | F03, F04, F06, F07, F08 |
| F10 | Frontend Shell and Dashboard | 1 | F09 |
| F11 | Bug List, Create and Detail | 1 | F10 |
| F12 | Agent Trace View | 1 | F10, F11 |
| F13 | Operations Console | 2 | F10 |
| F14 | Search Page | 2 | F10 |
| F15 | End-to-End Smoke Test and Quickstart | 2 | F12, F13, F14 |

### Foundation Features
These features set up shared project infrastructure. In a greenfield project they must be implemented sequentially before or alongside any feature that depends on them:
- **F01 Project Foundation** — monorepo layout, uv/Ruff/pytest setup, config module, logging, `.env.example`, Docker Compose with Postgres/pgvector, and the per-worktree environment script
- **F02 Schema, Migrations and Seed** — database models, migrations, canonical enums and the seed dataset that every later feature relies on
- **F03 Service Layer, Bug Management and CLI Skeleton** — service-layer conventions, run recorder and the `bugflow` CLI app that all later backend features extend
- **F10 Frontend Shell and Dashboard** — Next.js scaffolding, layout, API client and shared UI states that all later frontend features extend

### Execution Waves
Features within the same wave can be built in parallel. A wave starts only after every feature in earlier waves is complete.

**Note:** Foundation features (see "Foundation Features" above) cannot run in parallel in a greenfield project even if they appear together in a wave — they share scaffolding files and must be implemented sequentially until the base is in place.

- **Wave 1**: F01
- **Wave 2**: F02
- **Wave 3**: F03
- **Wave 4**: F04
- **Wave 5**: F05
- **Wave 6**: F06, F07, F08
- **Wave 7**: F09
- **Wave 8**: F10
- **Wave 9**: F11, F13, F14
- **Wave 10**: F12
- **Wave 11**: F15

Total: **11 waves**. Waves 1–5, 7, 8, 10 and 11 contain one feature each; parallel work happens only in waves 6 (3 features) and 9 (3 features). See `docs/execution-guide.md` for the exact `/spec-writer` and `/implement-and-evaluate-tmux` command to run for each wave.

### Priority levels
- **1** = Essential — product does not work without it
- **2** = Important — significant value addition
- **3** = Desirable — incremental improvement

```mermaid
graph TD
  F01[Foundation] --> F02[Schema]
  F02 --> F03[Services CLI]
  F03 --> F04[Search]
  F03 --> F05[Agents]
  F04 --> F05
  F05 --> F06[Runs]
  F05 --> F07[Reports]
  F05 --> F08[Reopen]
  F03 --> F09[API]
  F04 --> F09
  F06 --> F09
  F07 --> F09
  F08 --> F09
  F09 --> F10[Frontend]
  F10 --> F11[Bug UI]
  F10 --> F12[Trace]
  F11 --> F12
  F10 --> F13[Operations]
  F10 --> F14[Search UI]
  F12 --> F15[Smoke]
  F13 --> F15
  F14 --> F15
```

## 9. Acceptance Criteria

### F01. Project Foundation
- [ ] `docker compose up -d` starts `db` and `docker compose ps` shows it healthy; data survives `docker compose down` and `up` (named volume)
- [ ] `uv run ruff format .`, `uv run ruff check .` and `uv run pytest` pass from `backend/` on the skeleton
- [ ] `bugflow.config` is the only module reading environment variables; printing the settings object shows `***` for the API key and password
- [ ] A log call containing the API key or a database password emits masked text
- [ ] Starting without `OPENAI_API_KEY` does not crash; a missing `DATABASE_URL` fails fast with a message that does not contain the value
- [ ] `.env.example` lists every variable in section F01 and contains no real secret; `.env` is git-ignored
- [ ] `scripts/resolve-env.sh` returns offset 0 in the main checkout and a different offset (ports, database name, compose project) in another worktree
- [ ] All repository text, comments and log messages are in English

### F02. Schema, Migrations and Seed
- [ ] `init_db` on an empty database creates all tables and the `vector` extension; running it twice succeeds without changes
- [ ] Inserting a `bugs` row with an environment, team or status outside the enums is rejected by the database
- [ ] `seed_db` creates exactly 20 bugs, all `open`, matching the specified distribution by environment and reporting team; running it twice still leaves 20
- [ ] `reset_db` removes all data and leaves an empty, valid schema without seeding
- [ ] Seed code uses the same models as the application (no second schema definition)
- [ ] `init_db` against a database without pgvector fails with a clear message

### F03. Service Layer, Bug Management and CLI Skeleton
- [ ] `uv run bugflow --help` lists `check` and `db init|seed|reset` with English descriptions
- [ ] Creating a bug with valid fields returns a bug with status `open`; an over-length title or an invalid enum is rejected with per-field messages
- [ ] Editing an `open` bug succeeds; editing a `processed` bug fails with a state-conflict error
- [ ] Listing with filter `component`/`status`, sort and text search returns only matching bugs in order, with correct `total` and pagination (default 20, max 100)
- [ ] `bugflow check` reports database, vector search and LLM separately; with a missing API key the LLM line fails clearly and the others still run; no secret appears
- [ ] `bugflow db reset` without `--yes` and without typing `yes` deletes nothing and exits non-zero
- [ ] `init`, `seed` and `reset` each create a run record with status, timestamps and log lines
- [ ] CLI commands contain no business logic (they call services only)

### F04. Embeddings Index and Similar Search
- [ ] `bugflow index` embeds all 20 bugs (any status) and reports `20/20`; running it again rebuilds without duplicates
- [ ] Vectors have 1,536 dimensions and use `text-embedding-3-small`
- [ ] `bugflow search "<text>"` returns at most 5 bugs sorted by descending score; `--limit 20` is accepted and `--limit 21` is rejected
- [ ] `similar_to_bug` never includes the bug itself and returns an empty list when only one bug is indexed
- [ ] `ensure_embedding` re-embeds a bug whose text changed and leaves an unchanged bug untouched
- [ ] An invalid API key fails the index run with "OpenAI authentication failed" and no key in output; empty search text is rejected

### F05. Triage Agents
- [ ] A unit test fails if any of the five task templates lacks a bug placeholder (C1)
- [ ] End-to-end triage of a seeded bug with a mocked LLM produces one row each in component, severity, analysis, plan and report tables, five succeeded `run_steps`, and sets the bug `processed`
- [ ] AG1's stored `input` contains the exact title, description, reproduction steps, system version and environment of the bug
- [ ] AG3's stored `input` contains the similar bugs retrieved (excluding the bug itself), or "no similar bugs found"
- [ ] A mocked invalid enum value (for example severity `high`) triggers one re-ask; if still invalid the bug is `failed`, no result rows exist, the failing step and error are stored, later steps are `skipped`
- [ ] Near-miss enum values (different case, trailing space, synonym) are rejected, never normalized
- [ ] AG4 output with a person's name field, `target_days` of 0 or 91, or an AG3 reference to an unsupplied bug id fails validation
- [ ] Calls use temperature ≤ 0.2; transient errors are retried at most 2 times; a call exceeding 60 s times out
- [ ] Triage of a bug already `processing` or `processed` is rejected and changes nothing
- [ ] Results and the `processed` status are committed in one transaction; forcing an error at the last write leaves no result rows

### F06. Background Runs and Progress
- [ ] Starting a triage in the background returns a run ID within 1 s while the run continues
- [ ] Two concurrent triage starts for the same bug yield exactly one run and one state-conflict error
- [ ] "Triage all" creates one run per `open` bug, processes them sequentially, and a failure on one bug does not stop the others
- [ ] After a simulated crash, startup recovery marks `running`/`queued` runs `failed` (`interrupted`) and moves their bugs from `processing` to `failed`
- [ ] The event source returns steps and logs created after a cursor, including for a run started from the CLI

### F07. Report Rendering
- [ ] A processed bug has non-empty Markdown and HTML stored in the same transaction as its other results; if rendering fails, no result rows are stored and the bug is `failed`
- [ ] The Markdown report begins with the bug title (no stray first character) and contains the bug description and reproduction steps verbatim
- [ ] The report shows the resolution status of the plan as its label; with a plan status of `needs_info` the report text contains no hard-coded "resolved"
- [ ] The deadline equals completion date + `target_days`
- [ ] The Mermaid diagram is valid for every component × severity combination and escapes special characters
- [ ] Markdown, `<`, `|`, backticks and quotes in bug text do not break the HTML or the Mermaid
- [ ] `bugflow report <id> --format html --output file.html` writes the file; report for an unprocessed bug fails with "has no report"

### F08. Reopen
- [ ] Reopening a `processed` bug deletes its component, severity, analysis, plan and report rows and sets status `open`; its runs and run steps remain
- [ ] Reopening a `failed` bug sets it `open`
- [ ] Reopening a `processing` or already `open` bug is rejected and changes nothing
- [ ] An error during deletion rolls back everything
- [ ] `bugflow reopen <id>` without confirmation deletes nothing; with `--yes` it reopens
- [ ] After reopening, a new triage can run and produces a new run alongside the old one

### F09. API, Operations and Parity
- [ ] `/docs` serves OpenAPI for all endpoints in the F09 table; the server binds to `127.0.0.1` by default
- [ ] `POST /triage-runs`, `/admin/db/seed` and `/admin/index` return `202` with run id(s) in under 1 s
- [ ] `POST /triage-runs` for a `processing` bug returns `409`; a missing or invalid body returns `422` with per-field details
- [ ] `POST /admin/db/reset` and `POST /bugs/{id}/reopen` without `"confirm": true` return `422` and delete nothing
- [ ] `GET /runs/{id}/events` streams step and log events and closes on a terminal status; `GET /runs/{id}` returns the same data for polling
- [ ] `GET /meta/enums` returns every enum from F02 with codes and labels
- [ ] No response contains the API key or a connection string
- [ ] The parity test fails if any of the 9 CLI commands has no registered API route
- [ ] The API smoke test (health, create bug, list bugs) passes without a real LLM
- [ ] Requests from a non-configured origin are blocked by CORS

### F10. Frontend Shell and Dashboard
- [ ] `npm run dev` serves the app on port 3000 and ESLint passes
- [ ] Navigation shows Dashboard, Bugs, Search and Operations
- [ ] Dashboard shows counts by status, component and severity and the 10 most recent runs, matching `/stats` and `/runs`
- [ ] With an empty database the Dashboard shows the empty state; with the API down it shows an error with Retry
- [ ] Enum labels come from `/meta/enums` (no hard-coded duplicates in the source)
- [ ] The layout is usable at 375 px width

### F11. Bug List, Create and Detail
- [ ] The list filters, sorts and text-searches as specified and shows 20 rows per page
- [ ] Creating a bug with valid data adds it with status `open`; invalid data shows inline errors and does not submit
- [ ] Editing is available for `open` bugs only
- [ ] Bug detail shows the six tabs; Analysis and plan, Similar bugs, Report (rendered Markdown plus Mermaid) and Errors show real stored data for a processed or failed bug
- [ ] Triage is disabled for `processing` and `processed` bugs; clicking it on an `open` bug starts a run and opens the Agent trace tab
- [ ] Reopen asks for confirmation naming what will be deleted; cancelling sends no request
- [ ] Download report provides `.md` and `.html` files

### F12. Agent Trace View
- [ ] During a live run each of the five steps updates its status within 2 s without reloading
- [ ] Each step shows role, input, structured output, status and duration; the displayed AG1 input equals the stored input
- [ ] AG3's step shows the similar bugs it received
- [ ] A failed step is highlighted with its error and later steps show `skipped`
- [ ] A finished run, and runs before and after a reopen, can be viewed afterward
- [ ] If SSE is unavailable the view still updates by polling every 1 s

### F13. Operations Console
- [ ] Operations page has check, init, seed, reset and index, each with status
- [ ] Seed and index show live log lines and `done / total` progress
- [ ] Reset requires a confirmation dialog; cancelling sends no request
- [ ] The Console view shows the equivalent CLI command for each action and streams its log lines
- [ ] A failing operation shows status `failed` with its error; a missing API key appears in the Health panel
- [ ] Each action has the same effect as its CLI command (for example, seeding from the UI leaves 20 bugs)

### F14. Search Page
- [ ] Searching a text returns up to the selected limit of results with rank, title, status, environment and score, sorted by descending score
- [ ] Each result links to its bug detail
- [ ] Empty text sends no request; an empty index and no-match cases show specific empty states
- [ ] API errors show an error state

### F15. End-to-End Smoke Test and Quickstart
- [ ] Following only the README, a new user reaches a seeded, running UI in at most 8 commands and about 5 minutes
- [ ] The manual end-to-end script completes: seed, index, triage a seeded bug, watch the trace, read the report, reopen, search
- [ ] After a real triage, the report contains no content absent from the bug record or the stored agent outputs
- [ ] The README parity table matches the implemented CLI, API and UI
- [ ] `uv run ruff format .`, `uv run ruff check .`, `uv run pytest` and ESLint pass on the whole repo; no secret appears in logs, API responses or CLI output

### Cross-Feature Integration
- [ ] Settings, logger and the running database from F01 are used by `init_db` in F02 (migrations apply against the compose database)
- [ ] Schema, enums, seed and init/seed/reset services from F02 are what the F03 CLI and bug services use (seeding then listing bugs returns 20 `open` bugs)
- [ ] Bug services, run recorder and CLI app from F03 are used by `index` and `search` in F04 (an index run appears in `runs` with progress)
- [ ] The shared LLM client wrapper from F04 is the client used by the F05 agents (timeout and retry behavior is identical)
- [ ] `ensure_embedding` and `similar_to_bug` from F04 supply the similar bugs that F05 passes to AG3 and records in its step input
- [ ] Bug services, run recorder and CLI app from F03 are used by F05 (triage creates a run, steps and logs, and changes bug status through the bug services)
- [ ] The triage service and run steps from F05 are executed by the F06 background runner, and `iter_run_events` returns the same steps persisted by F05
- [ ] The stored results and AG5 prose from F05 are rendered by F07 inside the same transaction (a processed bug has all result rows and a report)
- [ ] Result rows (including the report row) written by F05 are deleted by F08 reopen, after which the bug can be triaged again
- [ ] F09 endpoints invoke the F03 bug and health services, F04 index/search, F06 background runner and event source, F07 report services and F08 reopen (each parity row works through the API with the same effect as the CLI)
- [ ] The F09 API, enums and stats are consumed by the F10 Dashboard and API client (dashboard counts equal `/stats`; labels equal `/meta/enums`)
- [ ] The F10 shell, API client and states host the F11 pages (list and detail load real bugs)
- [ ] The F11 bug detail tab slot and latest run ID show the F12 Agent trace for the run just started
- [ ] The F10 API client and run-progress hook drive F12 live updates and F13 live logs
- [ ] The F10 API client and enum provider drive the F14 search results
- [ ] The F12 trace, F13 Operations page and F14 search page are exercised by the F15 end-to-end script
