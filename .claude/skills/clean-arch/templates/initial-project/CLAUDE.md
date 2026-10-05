# CLAUDE.md

This project follows the Clean Architecture + tactical DDD philosophy defined in the global skill `clean-arch` (`~/.claude/skills/clean-arch/`).

**Before any structural change** (creating, moving, renaming, or modifying an entity, VO, use case, repository, query, handler, route, DTO, error, mapper, gateway, middleware, or composition root), invoke the skill via the Skill tool. The skill is also triggered automatically when the user asks for a new endpoint / feature / CRUD or mentions clean architecture, DDD, or layers.

## Project stack

- **Runtime**: Node.js 20+ + TypeScript 5
- **HTTP framework**: <fill in>
- **ORM**: <fill in>
- **Schema validation**: zod
- **Testing**: Vitest

## Structural rules

The 19 inviolable rules and the canonical folder structure are defined in `~/.claude/skills/clean-arch/SKILL.md`. The references in `~/.claude/skills/clean-arch/references/` cover deep dives.

## Self-audit gates

Before declaring any structural change complete:

```bash
npm run audit-arch
```

Husky enforces 1–2 on `pre-commit` and 3–6 on `pre-push`. **`git commit/push --no-verify` is forbidden.**

## Project-specific addenda

<!-- Add project-specific glossary, deployment notes, or convention overrides here. -->
