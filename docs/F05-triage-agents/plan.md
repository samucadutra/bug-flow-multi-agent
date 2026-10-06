# Implementation Plan: F05. Triage Agents

**Prerequisites:**
- F01 to F04 delivered: settings, logging, the F02 models, the F03 services, run recorder and CLI registry, the F04 shared client, embeddings and similarity services, and the OpenAI stand-in
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- New dependency approved for this feature: `crewai`, with `openai` pinned to the 2.x line it supports (spec assumption 1). The install is large; verify each CrewAI and `openai` API against the installed versions before use, since the spec is a sketch
- No new environment variable. `OPENAI_API_KEY` is only needed for manual runs against the real API; verification uses the local stand-in
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: Dependencies and Shared Plumbing

**1. Dependency Change** - Add `crewai`, pin `openai` to 2.x, regenerate the lock file, and adapt the existing mocks and tests that import `httpx2` so the whole F01 to F04 suite passes again before any F05 code is written. Record the resolved versions for the report.

**2. Third-Party Runtime Flags** - Add the settings-module helper that turns off CrewAI telemetry, tracing and the version check, keeping all environment access inside the settings module (spec assumption 3).

**3. JSON Mode on the Shared Client** - Add the optional JSON response mode to the chat call without changing its default behavior or the F04 contract (spec assumption 5).

**4. Step Recording** - Extend the run recorder with the step methods of spec section 5.2: create all steps pending, start, finish, skip the rest and read, each committed on its own and redacted.

### Stage 2: Agents

**5. Output Models** - Define the five strict output models and the agent table (key, label, role, goal, backstory) following spec assumptions 6 and 10, including the rule that unknown fields are rejected.

**6. Prompt Templates and Renderer** - Write the five English templates with the bug placeholders, previous-output placeholders and the generated output schema, plus the single-pass renderer that wraps bug data in explicit delimiters and neutralizes marker lines (spec assumption 9).

**7. CrewAI Adapter** - Implement the custom LLM that delegates to the shared client in JSON mode at temperature 0.0, with the neutral error type described in spec assumption 4 so CrewAI never adds its own retries.

**8. Agent Runner** - Implement the lazy-importing runner that executes one agent as a one-agent sequential crew with no tools, no memory and no retries of its own, and returns the raw reply text (spec assumption 2).

### Stage 3: Triage Services

**9. Claim Operation** - Implement the atomic claim with the rejection messages of spec assumption 15.

**10. Validation and Failure Text** - Implement parsing of raw replies into the output models, the single re-ask with the validation error, the cross-check of similar-bug ids and the failure texts of spec assumption 11.

**11. Similar-Bug Retrieval** - Implement the Technical Analyst's input preparation: ensure the bug's embedding, fetch the similar bugs with the configured count, and enrich triaged hits (spec assumption 14).

**12. Pipeline Execution** - Implement `execute_triage` and `triage_bug` end to end: step creation, live recording, outcome objects, the failure path that marks the bug failed and skips later steps, and the missing-key behavior (spec assumptions 12, 13, 15 and 16).

**13. Atomic Result Write and Hooks** - Implement the final transaction that inserts the five result rows, runs registered hooks and sets `processed`, with rollback and failure handling as in spec assumption 17.

**14. Triage All** - Implement the sequential batch that continues after failures and lost claims (spec assumption 18).

### Stage 4: CLI and Stand-in

**15. Triage Command** - Add `bugflow triage` with the option rules, live step lines, result lines, summary and exit codes of spec assumption 19, and register it so `--help` lists it.

**16. Stand-in Extension** - Extend the OpenAI stand-in with role-based canned agent replies, chat scripting by role and message text, and the richer chat record described in spec assumption 21, without changing its embedding behavior.

### Stage 5: Readiness

**17. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, then run `triage` for one seeded bug and for `--all` through the CLI against the compose database and the stand-in, confirming run steps, run logs and that no key appears in any output. Also confirm that nothing is written outside the repository by CrewAI. Record any deviation from the spec so it can be reported.
