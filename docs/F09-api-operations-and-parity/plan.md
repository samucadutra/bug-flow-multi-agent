# Implementation Plan: F09. API, Operations and Parity

**Prerequisites:**
- F01 to F08 delivered: settings and logging with redaction, the F02 models, enums and admin services, the F03 bug services, health check, run recorder and CLI registry, the F04 search services and OpenAI stand-in, the F05 triage service, the F06 `BackgroundRunner`, event source and recovery, the F07 report services and hook, the F08 reopen service
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- **New dependencies, to be approved by the user before the first step (AGENTS.md section 5):** `fastapi` and `uvicorn` as runtime dependencies and `httpx` as a development dependency (needed by `fastapi.testclient.TestClient`). They are not listed in `backend/pyproject.toml` or `backend/uv.lock` today (only `starlette`, `uvicorn` and `httpx` appear transitively through CrewAI). No other dependency is added; SSE is hand-written and `sse-starlette` is not used
- No new environment variable. `API_HOST`, `API_PORT` and `CORS_ORIGINS` already exist in `bugflow.config`; `OPENAI_API_KEY` is not needed by the tests because they use the local stand-in
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step
- Verify the FastAPI, Starlette, uvicorn and Typer APIs used here against the installed versions; the spec is a sketch. In particular confirm how `StreamingResponse` iterates a blocking generator and how exception handlers are registered in the installed Starlette

### Stage 1: Foundation of the API Package

**1. Dependencies** - After approval, add the three dependencies listed in the prerequisites with `uv add`, commit the lockfile change with the code, and confirm `uv sync` reproduces the environment (spec section 3, decision 1).

**2. Read Services** - Add the three read-only service modules for dashboard counts, run listing and run detail, and bug detail with stored results, returning frozen Pydantic models and using parameterized queries (spec sections 4 and 6, assumptions 7, 8, 10, 11).

**3. Error Model and Handlers** - Build the error envelope and the exception handlers that map service, validation, HTTP and unexpected errors to the statuses of the spec, with fixed messages and redaction (spec assumptions 16 and 17, section 5.1).

**4. Request and Response Models** - Define the request bodies with the confirm guard and the triage body rules, and the response models for health, enums, stats, bug detail, run ids and run detail (spec section 4, assumptions 6 to 14).

**5. App Factory and Lifespan** - Implement `create_app` with the `/api/v1` router prefix, CORS for the configured origin only, the report hook, the lazily built runner and startup recovery that tolerates an unreachable database, plus the request dependencies and the test-only injection points (spec assumptions 4, 18, 19 and 24).

### Stage 2: Endpoints

**6. System Endpoints** - Add health (three checks side by side, always `200`), canonical enums from the enum module and dashboard stats (spec assumptions 6 and 7, section 5.2).

**7. Bug Endpoints** - Add create, list, detail, edit, similar bugs, bug runs, reopen with confirmation and the report endpoint with its three formats, committing where the underlying service only flushes (spec assumptions 8, 9, 10, section 5.4).

**8. Search Endpoint** - Add semantic search with the shared limit rules and the fixed `503` behavior when the key is missing (spec assumption 15).

**9. Administrative Endpoints** - Add init and reset as synchronous operations, with the confirm guard on reset, and seed and index as background runs answered with `202` and a run id (spec assumptions 13, 14, 15, section 5.3).

**10. Triage and Run Endpoints** - Add `POST /triage-runs`, recent runs with filters, run detail for polling and the run event stream with resume support and framing (spec assumptions 11, 12, 13, section 5.4).

### Stage 3: Command, Parity and Hardening

**11. Serve Command** - Add `bugflow serve` with host and port defaults from settings, the banner, the loopback warning and registration in the command registry (spec assumption 20, section 5.5).

**12. Parity Map and Checker** - Add the machine-checked CLI to API map, the exclusion of `serve` and the gap-finding function that walks the CLI command tree and the registered routes (spec assumption 21).

**13. Secret and Error Hardening** - Review every endpoint for fixed messages, confirm no response, header, log line or OpenAPI field can carry the key, a password or a connection string, and confirm unexpected failures return the generic `500` (spec assumption 17).

### Stage 4: Readiness

**14. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`. Then start `uv run bugflow serve` against the compose database and the stand-in, open `/docs`, and walk the nine parity rows through the API (seed, index, triage a seeded bug while streaming its events, read the report, reopen, search, check, reset), confirming each has the same effect as its CLI command and no secret appears in any output. Record any deviation from the spec so it can be reported.
