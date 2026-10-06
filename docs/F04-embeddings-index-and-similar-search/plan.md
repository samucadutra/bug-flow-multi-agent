# Implementation Plan: F04. Embeddings Index and Similar Search

**Prerequisites:**
- F01 to F03 delivered: settings, logging, the F02 models and `bug_embeddings` table, the F03 services, run recorder, recorded operations, health check and CLI registry
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- No new dependency and no new environment variable. The installed `openai` SDK must honor its own base-URL environment variable (spec assumption 1); verify its API against the installed version before use, since the spec is a sketch
- `OPENAI_API_KEY` is only needed for manual runs against the real API; verification uses the local stand-in
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step

### Stage 1: LLM Client and Offline Stand-in

**1. LLM Client Wrapper** - Implement the shared client with embeddings, chat, timeout, bounded retry with backoff, the fixed error messages and the size and temperature guards of spec sections 5.1 and 5.2. Keep it independent of the database so F05 can reuse it unchanged.

**2. Health Constants Move** - Move the OpenAI message constants from the F03 health module into the new client module and re-export them so existing imports keep working. Behavior of the F03 health check must not change.

**3. OpenAI Stand-in Server** - Provide the local stand-in described in spec assumption 14 under the mocks folder, with deterministic embeddings, key checking, scripted failures and a request record, so the client and the CLI can be exercised without network access or a real key.

### Stage 2: Embeddings and Search

**4. Embedding Text and Hash** - Implement the enriched text builder, the query text builder and the model-aware hash so staleness depends on exactly the fields listed in spec assumptions 4 and 5.

**5. Ensure Embedding** - Implement `ensure_embedding` with the create, refresh and leave-untouched rules of spec assumption 11. It flushes and never commits.

**6. Index Service** - Implement `index_all_bugs` with batches of 20, per-batch committed upserts, the progress callback and the failure behavior of spec assumption 6.

**7. Similarity Search** - Add the search error type, the query validation and the two search functions, including the empty-index hint and the freshness step of `similar_to_bug`. Ordering and score follow spec assumption 10 and section 6.

### Stage 3: Operation and CLI

**8. Recorded Index Operation** - Add `run_index` and its summary message to the F03 operations module, with the missing-key and uninitialized-schema behavior of spec assumptions 7 and 8.

**9. CLI Output and Context Updates** - Make the CLI print the field messages of validation errors and expose a lazy client factory in the bootstrap context, per spec assumption 13.

**10. Index and Search Commands** - Add the two commands with English one-line help texts, the output formats of spec assumption 12 and the error table of spec section 5.6. Commands only parse arguments, call one service and print.

**11. Command Registration** - Register the two modules in the F03 command registry so `--help` lists them.

### Stage 4: Readiness

**12. Quality Gate and Handoff Check** - Run the full quality gate and the integration suite from `backend/`, then run `index` twice and a few searches through the CLI against the compose database and the stand-in, confirming run records and that no key appears in any output. Record any deviation from the spec so it can be reported.
