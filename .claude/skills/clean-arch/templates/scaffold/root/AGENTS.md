## Environment

- Use `./scripts/init.sh` to start the project.
- Use `./scripts/stop.sh` to stop dev processes.
- Use `./scripts/stop.sh --clean` to stop processes and reset generated local state. __AGENTS_CLEAN_TEXT__
- Do not run app dev servers directly.

## Backend

- Before backend work, ask the user to load/use the `clean-arch` skill.
- Follow clean architecture: `domain/` <- `usecase/` <- `infra/`.
- `src/main.ts` is the composition root and the only place that wires concrete infra classes.
- `process.env` is only allowed in `src/config/env.ts`.
- Handlers validate input and call use cases; handlers do not catch errors.
- Run `./scripts/run-gates.mjs` before declaring backend work done.
- Use the provided gates and linters. Do not create replacement gates.

## Code Style

- Keep functions small, focused, and explicitly typed.
- Prefer small modules over large files; split by responsibility.
- Use specific names. Avoid vague names like `data`, `handler`, or `Manager`.
- Avoid `any`, duplicated logic, and deep nesting.
- Error messages must include the offending value and expected shape.
- Comments explain why, not what.

## Tests And Logs

- Every new backend function gets a test; bug fixes get a regression test.
- Mock external I/O with named fake classes, not inline stubs.
- Use structured JSON for observability logs and plain text for CLI output.
