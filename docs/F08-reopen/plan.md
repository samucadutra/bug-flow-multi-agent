# Implementation Plan: F08. Reopen

**Prerequisites:**
- F01 to F05 delivered: settings and logging, the F02 models and enums, the F03 services (`ensure_transition_allowed`, `get_bug`, typed errors), the F03 CLI registry, output helpers and typed confirmation, the F04 shared client and the OpenAI stand-in, and the F05 `claim_bug`, `triage_bug` and result tables
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- No new dependency and no new environment variable. `OPENAI_API_KEY` is not needed: the only test that triages uses the local stand-in
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step
- Verify the SQLAlchemy and Typer APIs used here against the installed versions; the spec is a sketch

### Stage 1: Reopen Service

**1. Test Fixtures and Helpers** - Add the shared test helpers and integration fixtures that build triaged, failed, processing and open bugs with run history, embedding and result rows through the F02 models, plus the reopen hook fixtures and the autouse hook cleanup described in spec section 4 and assumptions 14 and 17.

**2. Reopen Transaction** - Implement `reopen_bug` in the new service module: the conditional status update that doubles as the race guard, the deletion of the five result tables from the hard-coded allowlist, commit, and the returned bug read, following spec assumptions 4, 5, 7 and 13.

**3. Rejections and Failure Handling** - Add the rejection messages, the unknown-id error, the unreachable-database mapping and the rollback path with the fixed failure error, following spec assumptions 5 and 9.

**4. Reopen Hooks** - Add the in-transaction hook registry used to observe and break the transaction in tests, run after the deletions and before the commit (spec assumption 8).

### Stage 2: CLI

**5. Reopen Command** - Add `bugflow reopen` with the required id argument, the `--yes` flag, the exact confirmation prompt, the abort path with exit code 1 and the result line, reusing the F03 helpers (spec assumptions 11 and 12).

**6. Command Registration** - Register the module in the F03 command registry so `--help` lists `reopen` with a one-line English description.

### Stage 3: Readiness

**7. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, then use the CLI against the compose database and the stand-in: triage a seeded bug, reopen it, confirm the result tables are empty while runs, steps, logs and the embedding remain, and triage it again. Confirm no secret appears in any output. Record any deviation from the spec so it can be reported.
