# AGENTS.md — Operating Rules for AI Coding Assistants

This repository is built with **Spec-Driven Development (SDD)**. The documents in `docs/` are the source of truth. Code exists to satisfy them.

## 1. Read before you act

At the start of every session, before writing or changing anything, read:

1. The PRD and the target feature definition: locate `docs/prd.md`, `docs/PRD.md`, `PRD.md`, or the project's accepted PRD file. Resolve the feature by ID or name, and confirm the choice if the input is ambiguous. The PRD is mandatory; if no PRD is found, stop and ask the user to generate one first with the `prd-writer` skill.
2. The codebase patterns that inform the implementation: runtime/framework/database/auth/testing conventions, project layout, fixture and seed conventions, and any existing specs or contracts relevant to the target feature.
3. The active feature folder `docs/<feature-id>-<kebab-name>/`:
   - `spec.md` covers WHAT and WHY: technical specification and scope.
   - `plan.md` covers HOW: implementation phases and steps.
   - `contract.md` covers the behavior contract and verification surfaces.

If the user does not name the active feature, resolve it from the PRD before starting, or ask the user to confirm the feature when the reference is ambiguous.

## 2. Precedence when documents disagree

PRD / approved feature definition > active `spec.md` > `plan.md` > `contract.md` > observed codebase patterns > ad hoc assumptions

If you find a conflict, an ambiguity, or a requirement that cannot be implemented as written, **stop, explain the problem, and propose a concrete change to the PRD, spec, or plan**. Do not silently pick an interpretation. If the issue affects the project contract or feature definition, do not edit the source-of-truth docs without the user's approval.

## 3. How to implement tasks

- Implement **only** the tasks the user asked for (e.g. "T001–T004"). Do not jump ahead or "improve" unrelated code.
- For each task:
  1. Re-read the requirement IDs it references (`FR-###`, `NFR-###`).
  2. For deterministic logic, write or update the tests first.
  3. Make the smallest change that satisfies the task.
  4. Run the task's **Verify** step and the quality gate (section 4).
  5. Mark the task done in `tasks.md`: `- [ ]` → `- [x]`.
- When the batch is finished, stop and report:
  - the tasks completed,
  - the files changed,
  - the verification output (commands and results),
  - any deviation from the plan and why.
- Third-party library APIs (CrewAI, Pinecone, OpenAI, psycopg, pydantic-settings) change over time. The code in `plan.md` is a **sketch**. Check it against the installed package version (read the installed source or official docs) and follow the real API. If a difference affects the design, report it so the plan can be updated.

## 4. Quality gate

Every task must pass these before it is marked done:

```bash
uv run ruff format .
uv run ruff check .
uv run pytest
```

Integration tests call real services and run only when the user explicitly asks:

```bash
uv run pytest -m integration
```

## 5. Hard rules

- **English only**: identifiers, comments, docstrings, log messages, CLI output, SQL, file and folder names, commit messages, documentation.
- **Secrets**: never print, log, or commit API keys, passwords, or full connection strings. Read configuration only through `bugflow.config`.
- **SQL**: parameterized queries only. Dynamic identifiers (table names) only from hard-coded allowlists via `psycopg.sql.Identifier`.
- **LLM output**: always a validated Pydantic model. Never scrape free text with regex or substring search. Never replace invalid LLM output with invented defaults.
- **Integration tests** use `TEST_DATABASE_URL`, never `DATABASE_URL`.
- **Dependencies**: never add a dependency that the active `plan.md` does not list without asking first.
- **Constitution**: never edit `docs/constitution.md` unless the user explicitly asks.
- **Scope**: never implement anything listed under *Out of Scope* in the active spec.

## 6. Commands reference

| Purpose | Command |
|---|---|
| Install / sync dependencies | `uv sync` |
| Run the CLI | `uv run bugflow --help` |
| Unit tests | `uv run pytest` |
| Integration tests | `uv run pytest -m integration` |
| Lint | `uv run ruff check .` |
| Format | `uv run ruff format .` |

## 7. Commits

Commit only when the user asks. Use Conventional Commits and reference the feature and tasks:

```
feat(001): add settings loader and db init command (T004-T008)
```
