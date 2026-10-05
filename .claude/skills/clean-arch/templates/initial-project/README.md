# Clean Architecture starter

This project is scaffolded from the `clean-arch` skill at `~/.claude/skills/clean-arch/`. The architecture follows three layers (`domain/`, `usecase/`, `infra/`) plus `config/` and a single composition root in `main.ts`.

Read `~/.claude/skills/clean-arch/SKILL.md` for the full prescription. Read the project's `CLAUDE.md` for project-specific addenda.

## Quick start

```bash
npm install
npm run audit-arch     # all 6 self-audit gates
npm run dev            # boot the app
```

## Layout

```
src/
  config/env.ts         # the only place that reads process.env
  domain/_shared/       # whitelist: id.vo, errors, unit-of-work, pagination
  domain/<feature>/     # entities, VOs, interfaces, errors per feature
  usecase/<feature>/    # use case classes + DTOs
  infra/http/           # handlers, routes, middleware, error mapping
  infra/repository/<feature>/
  infra/queries/<feature>/
  infra/gateway/        # external API adapters
  infra/persistence/    # transaction context, UoW (opt-in)
  main.ts               # composition root — only place with `new` of infra
```

## Self-audit

Before any commit:

```bash
npm run audit-arch
```

Husky runs the fast gates on `pre-commit` and the heavy gates on `pre-push`. **Never use `--no-verify`.**

## Where to look

- `~/.claude/skills/clean-arch/SKILL.md` — manifesto + 19 inviolable rules.
- `~/.claude/skills/clean-arch/references/anti-patterns.md` — load before any non-trivial change.
- `~/.claude/skills/clean-arch/references/folder-structure.md` — adding a new feature, step by step.
- `~/.claude/skills/clean-arch/references/domain-modeling.md` — entities, VOs, aggregates.
- `~/.claude/skills/clean-arch/references/use-case-pattern.md` — class shape, DTOs, validation.
- `~/.claude/skills/clean-arch/references/repository-and-queries.md` — write-side / read-side split.
- `~/.claude/skills/clean-arch/references/composition-root.md` — `main.ts` and the framework adapter.
