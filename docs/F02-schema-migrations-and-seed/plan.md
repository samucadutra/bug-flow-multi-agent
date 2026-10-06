# Implementation Plan: F02. Schema, Migrations and Seed

**Prerequisites:**
- F01 delivered: `bugflow.config`, `bugflow.logging_config`, the `backend/` uv project and the compose `db` service (`pgvector/pgvector:pg17`)
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2, `git` and `bash`
- New runtime dependencies approved for this feature: `sqlalchemy`, `alembic`, `psycopg[binary]` and `pgvector`, latest stable versions pinned in `uv.lock`. Verify each API against the installed package version before use, since the spec is a sketch
- `DATABASE_URL` and `TEST_DATABASE_URL` set in `.env` (copied from `.env.example`); no new environment variable is introduced
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: Data Layer Foundations

**1. Dependencies and Alembic Tooling** - Add the four approved dependencies to the backend project, refresh the lock file, and add the thin `alembic.ini` used only by developers. See spec sections 3 and 4.

**2. Canonical Enum Module** - Create `bugflow.enums` with the eleven enums, their English labels, the Component and Severity definitions and the descriptor helper that lists every enum. Follow spec section 5.1 exactly, since every later layer derives its codes from this module.

**3. Database Base and Errors** - Create the declarative base with the constraint naming convention and the helper that builds enum CHECK constraints, plus the database error classes. Error messages must never contain the connection URL (spec section 5.3).

**4. ORM Models** - Define the ten application tables with their columns, constraints and indexes as described in spec section 6, including the 1,536-dimension vector column and the JSON column guards. The models are the only definition the application and the seed use.

**5. Engine Helpers** - Add the engine and session factory helpers that receive the URL as an argument. They must not read the environment or log the URL.

### Stage 2: Migration and Services

**6. Alembic Environment** - Set up the in-package migration environment so it works from any working directory, uses a connection supplied by the caller, runs DDL transactionally and takes its metadata from the models. It must not read environment variables.

**7. Initial Migration** - Write the frozen base revision with explicit DDL: the vector extension first, then the tables, constraints and indexes of spec section 6, with literal enum codes. A downgrade removes the tables and keeps the extension.

**8. Seed Dataset** - Write the 20 English bugs with the exact distributions, fixed dates and unique titles from spec assumption 7, keeping the design-intent fields outside the stored columns.

**9. Admin Services** - Implement `init_db`, `seed_db` and `reset_db` with the typed results, ordering, atomicity and error behavior of spec section 5.3. The seed must go through the same models as the application, and logging must follow spec assumption 11.

### Stage 3: Local Infrastructure and Readiness

**10. Plain Postgres Compose Profile** - Add the `db_plain` service under the `nopgvector` profile as described in spec section 5.4, leaving the existing `db` service and the default `docker compose up -d` behavior unchanged.

**11. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, and confirm that `init_db`, `seed_db` and `reset_db` work against the compose database and that the `db_plain` profile starts and tears down cleanly. Record any deviation from the spec so it can be reported.
