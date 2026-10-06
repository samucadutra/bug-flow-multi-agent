# Implementation Plan: F03. Service Layer, Bug Management and CLI Skeleton

**Prerequisites:**
- F01 and F02 delivered: `bugflow.config`, `bugflow.logging_config`, the F02 models, enums, `init_db`, `seed_db`, `reset_db` and the engine helpers
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- One new runtime dependency approved for this feature: `openai`, latest stable version pinned in `uv.lock`. Verify its API against the installed package version before use, since the spec is a sketch
- No new environment variable; `OPENAI_API_KEY` is only needed for manual runs of `bugflow check` against the real API
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: Service-Layer Foundations

**1. Dependency and Engine Timeout** - Add the `openai` dependency, refresh the lock file, and give the engine helper the connect timeout described in spec assumption 10. No other F02 code changes.

**2. Errors and Conventions** - Create the typed service errors and the conventions docstring of spec section 5.1. Messages must be fixed English text that never contains secrets or URLs.

**3. Input and Output Models** - Define the bug and run models and the payload validation helper so that every rejection produces per-field messages exactly as in spec assumption 3. The offending value must never appear in a message.

**4. Bug Services** - Implement create, get, update and list with the semantics of spec section 5.2 and assumptions 4 to 6, plus the status transition table and its guard. Services flush but never commit, and the edit guard must be atomic.

### Stage 2: Run Recording and Health

**5. Run Recorder** - Implement the recorder, the scoped helper and the deferred recorder of spec section 5.4. Every recorder call commits on its own, and all stored text is redacted first.

**6. Recorded Operations** - Wrap the F02 services in `run_init`, `run_seed` and `run_reset` following spec assumption 8, including the schema-initialized check before seeding and the failure recording rules.

**7. Health Check and LLM Probe** - Implement the three independent checks, the injectable probe protocol and the default OpenAI-backed probe with fixed error messages, as described in spec assumption 9.

### Stage 3: CLI

**8. CLI Package Restructure** - Replace the single CLI module with a package that keeps the version flag free of configuration, exposes the same console entry point, and registers command modules from an explicit ordered tuple. See spec assumption 13.

**9. Output and Context Helpers** - Add the helpers for printing, typed confirmation and error-to-exit-code mapping, and the bootstrap that loads settings, configures logging and builds the engine only when a command runs. See spec assumptions 11 and 12.

**10. Commands** - Add `check` and the `db` group with `init`, `seed` and `reset [--yes]`. Commands only parse arguments, call one service and print, with English one-line help texts, per spec section 5.6.

### Stage 4: Readiness

**11. Offline LLM Stand-ins** - Provide the fake OpenAI client and fake probe under the mocks folder so the health check can run without network access or a real key.

**12. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, then run the four commands against the compose database (init, seed, reset, check) and confirm run records exist for the first three. Record any deviation from the spec so it can be reported.
