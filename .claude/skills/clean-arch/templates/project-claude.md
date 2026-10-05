# CLAUDE.md

This project follows the Clean Architecture + tactical DDD philosophy defined in the global skill `clean-arch` (`~/.claude/skills/clean-arch/`).

**Before any structural change** (creating, moving, renaming, or modifying an entity, VO, use case, repository, query, handler, route, DTO, error, mapper, gateway, middleware, or composition root), invoke the skill via the Skill tool. The skill is also triggered automatically when the user asks for a new endpoint / feature / CRUD or mentions clean architecture, DDD, or layers.

## Project stack

<!-- Replace these with the actual stack of this project. -->

- **Runtime**: Node.js 20+ + TypeScript 5
- **HTTP framework**: Express
- **ORM**: Prisma
- **Schema validation**: zod
- **Testing**: Vitest

## Structural rules

The 19 inviolable rules and the canonical folder structure are defined in `~/.claude/skills/clean-arch/SKILL.md`. The references in `~/.claude/skills/clean-arch/references/` cover deep dives (domain modeling, error handling, authorization, etc.).

## Self-audit gates

Before declaring any structural change complete, run all 6 gates:

```bash
npx tsc --noEmit -p tsconfig.json
npx eslint . --max-warnings=0
npx depcruise src --config .dependency-cruiser.cjs
npx tsx scripts/check-architecture.ts
npx madge --circular --extensions ts src
npx knip
```

Husky enforces 1–2 on `pre-commit` and 3–6 on `pre-push`. **`git commit/push --no-verify` is forbidden.** If a gate fails, fix the code; never bypass.

## Project-specific addenda

<!-- Add anything specific to this project: business glossary, special endpoints,
     conventions that override the skill, deployment notes, etc.
     Keep skill-level prescriptions in the skill; keep project specifics here. -->
