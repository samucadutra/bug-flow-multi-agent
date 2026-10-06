# Implementation Plan: F06. Background Runs and Progress

**Prerequisites:**
- F01 to F05 delivered: settings, logging, the F02 models and run tables, the F03 services, run recorder, recorded operations and CLI registry, the F04 shared client and index service, the F05 triage service (claim, `execute_triage`, result hooks), the CLI `triage` command and the OpenAI stand-in with role-based replies and scripting
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- No new dependency and no new environment variable. Only the Python standard library is added to the imports; verify the F03 to F05 APIs against the installed code before use, since the spec is a sketch. In particular confirm that a one-agent CrewAI crew runs correctly from a non-main thread
- `OPENAI_API_KEY` is only needed for manual runs against the real API; verification uses the local stand-in
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: Reuse of Recorded Operations

**1. Recorded Run With an Existing Run** - Let the run-recorder context manager start and finish a run that was already created, and pass the optional run id through the recorded seed and index operations, leaving every default call unchanged (spec assumption 12).

### Stage 2: Event Source and Recovery

**2. Cursor and Event Models** - Define the event models, the cursor format with its parsing and formatting rules, and the pure derivation of events from a run row, its steps and its new logs (spec assumptions 14 to 16).

**3. Event Reading and Iteration** - Implement the non-blocking page read and the blocking generator with the 500 ms interval, eager validation and termination on a finished run (spec assumptions 16 and 17).

**4. Startup Recovery** - Implement the single-transaction recovery of interrupted runs, the closing of their open steps, the return of stuck bugs to `failed` and the shared step-closing helper (spec assumption 18).

### Stage 3: Background Runner

**5. Parameters and Start Results** - Define the run kinds, the strict parameter validation with field errors and the start result model (spec assumptions 4 and 5).

**6. Lanes** - Implement the single-thread FIFO lane with lazy start, one-at-a-time execution, survival after a failing task, idle waiting and shutdown (spec assumption 9).

**7. Triage Start** - Implement the single and the all-open-bugs triage start: validation, claim before any run, run creation, queueing in id order and the all-or-nothing preparation (spec assumptions 6 and 7).

**8. Seed and Index Start** - Implement the schema check, the queued run creation and the queueing on the operations lane, with the recorded operations as the task bodies (spec assumptions 8, 10 and 12).

**9. Safety Net** - Wrap every lane task so that an unexpected error finishes an unfinished run as failed, closes its open steps, returns a stuck bug to `failed`, is logged redacted and never stops the lane (spec assumption 11).

### Stage 4: Verification Support and Readiness

**10. Test Fixtures and Helpers** - Add the runner fixture with orderly shutdown, the state fixtures for a streaming run and for the interrupted-state set, the failing client factories and the waiting helpers used by the integration tests.

**11. Cross-Process Checks** - Provide the integration checks that run the CLI triage as a child process, stream its run from the test process, resume after a cursor, and recover after killing the child (spec section 7).

**12. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, then start a triage, a triage-all, a seed and an index through the runner against the compose database and the stand-in, stream their events, and confirm run records, logs, that no key appears in any stored text, and that nothing is left `queued`, `running` or `processing` after recovery. Record any deviation from the spec so it can be reported.
