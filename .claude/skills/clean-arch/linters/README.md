# Linters and self-audit gates

This folder contains the configuration files that enforce the architectural rules in `~/.claude/skills/clean-arch/SKILL.md`. Copy them into the root of any project that follows the skill, install the listed dependencies, and run the gates before committing or pushing.

## Files

| File                          | Tool                | Purpose                                                              |
|-------------------------------|---------------------|----------------------------------------------------------------------|
| `.dependency-cruiser.cjs`     | dependency-cruiser  | Cross-layer imports, banned I/O libs in domain, no barrel files.     |
| `.eslintrc.cjs`               | ESLint              | AST-level checks: no `set` in domain, no `try/catch` in handlers, no `process.env` outside `config/`, etc. |
| `tsconfig.architecture.json`  | TypeScript          | Strict compiler options template — extend or copy to project's `tsconfig.json`. |
| `husky/pre-commit`            | husky               | Runs the fast gates (tsc + eslint) via lint-staged on staged files.  |
| `husky/pre-push`              | husky               | Runs the heavy gates (depcruise + check-architecture + madge + knip + vitest). |
| `lint-staged.config.cjs`      | lint-staged         | Specifies how the pre-commit hook runs on staged files.              |

## Installation

In the target project:

```bash
npm i -D dependency-cruiser eslint @typescript-eslint/parser @typescript-eslint/eslint-plugin \
        typescript tsx madge knip vitest \
        husky lint-staged
npx husky init
cp ~/.claude/skills/clean-arch/linters/.dependency-cruiser.cjs .
cp ~/.claude/skills/clean-arch/linters/.eslintrc.cjs .
cp ~/.claude/skills/clean-arch/linters/lint-staged.config.cjs .
cp ~/.claude/skills/clean-arch/linters/husky/pre-commit .husky/
cp ~/.claude/skills/clean-arch/linters/husky/pre-push   .husky/
chmod +x .husky/pre-commit .husky/pre-push
mkdir -p scripts
cp ~/.claude/skills/clean-arch/scripts/check-architecture.ts scripts/
```

(For new projects, prefer copying the `templates/initial-project/` scaffold, which has all of the above pre-wired.)

Make sure `package.json` has `"type": "module"` (or adjust imports in `tsconfig.architecture.json`) and add scripts:

```json
{
  "scripts": {
    "prepare": "husky",
    "lint": "eslint . --max-warnings=0",
    "typecheck": "tsc --noEmit -p tsconfig.json",
    "depcruise": "depcruise src --config .dependency-cruiser.cjs",
    "check-arch": "tsx scripts/check-architecture.ts",
    "circular": "madge --circular --extensions ts src",
    "orphans": "knip",
    "test": "vitest run",
    "audit-arch": "npm run typecheck && npm run lint && npm run depcruise && npm run check-arch && npm run circular && npm run orphans && npm run test"
  }
}
```

## The 6 self-audit gates

Run before declaring any structural change done. Husky automates these on commit/push.

```bash
npx tsc --noEmit -p tsconfig.json                       # Gate 1 — typecheck
npx eslint . --max-warnings=0                           # Gate 2 — lint
npx depcruise src --config .dependency-cruiser.cjs      # Gate 3 — cross-layer
npx tsx scripts/check-architecture.ts                   # Gate 4 — structural
npx madge --circular --extensions ts src                # Gate 5 — circular deps
npx knip                                                # Gate 6 — orphans
```

(`vitest run` is a 7th gate run on pre-push; tests are out of scope for this skill but the gate stays for safety.)

## Forbidden: `--no-verify`

`git commit --no-verify` and `git push --no-verify` are forbidden by the skill (rule 19). If a gate fails, fix the code. If you genuinely believe the gate is wrong, stop and ask the user — never bypass.

## Customization

The `.cjs` files are templates. Adjust them when:

- The project uses a different ORM — extend the `no-prisma-outside-infra` rule with the corresponding package name.
- The project uses a different schema validator — adjust the `no-restricted-syntax` rules in `.eslintrc.cjs` if they reference zod-specific patterns (currently they do not).
- The project has a non-standard root path — update the `from`/`to` regexes in `.dependency-cruiser.cjs`.

When modifying these configs, update `references/anti-patterns.md` and `SKILL.md` accordingly. The configs and the skill must say the same thing.
