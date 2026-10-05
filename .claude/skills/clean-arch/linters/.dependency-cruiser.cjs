/**
 * Dependency-cruiser config — enforces the Clean Architecture dependency rule.
 *
 * Run with:  npx depcruise src --config .dependency-cruiser.cjs
 *
 * The rules below mirror the architectural prescriptions in `~/.claude/skills/clean-arch/SKILL.md`.
 * They forbid imports that violate layer boundaries, ban I/O libraries from `domain/`,
 * and limit `process.env` to `src/config/env.ts`.
 */

/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    // ── Layer boundaries (rule 1) ────────────────────────────────────────────
    {
      name: 'domain-no-deps',
      severity: 'error',
      comment:
        'domain/ must not import from usecase/, infra/, or config/. ' +
        'Pure business; arrows point inward.',
      from: { path: '^src/domain/' },
      to:   { path: '^src/(usecase|infra|config)/' },
    },
    {
      name: 'usecase-no-infra',
      severity: 'error',
      comment:
        'usecase/ must not import from infra/. Use cases depend on interfaces from domain/. ' +
        'Implementations are wired in main.ts.',
      from: { path: '^src/usecase/' },
      to:   { path: '^src/infra/' },
    },
    {
      name: 'usecase-no-config',
      severity: 'error',
      comment: 'usecase/ must not import from config/. Receive values via constructor.',
      from: { path: '^src/usecase/' },
      to:   { path: '^src/config/' },
    },

    // ── Domain may not import I/O libraries (rule 9) ─────────────────────────
    {
      name: 'no-prisma-outside-infra',
      severity: 'error',
      comment: 'Prisma is a persistence detail; domain/ and usecase/ may not import it.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^node_modules/(@prisma/client|prisma)/' },
    },
    {
      name: 'no-orm-outside-infra',
      severity: 'error',
      comment: 'Other ORMs (TypeORM, Mongoose, Kysely, Drizzle) are persistence; domain/ and usecase/ may not import them.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^node_modules/(typeorm|mongoose|kysely|drizzle-orm)/' },
    },
    {
      name: 'no-axios-outside-infra',
      severity: 'error',
      comment: 'HTTP clients are network I/O; domain/ and usecase/ may not import them.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^node_modules/(axios|got|node-fetch|undici)/' },
    },
    {
      name: 'no-node-http-outside-infra',
      severity: 'error',
      comment: 'Node http/https are network I/O; domain/ and usecase/ may not import them.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^(node:)?(http|https)$' },
    },
    {
      name: 'no-node-fs-outside-infra',
      severity: 'error',
      comment: 'Filesystem is I/O; domain/ and usecase/ may not import fs.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^(node:)?(fs|fs/promises)$' },
    },
    {
      name: 'no-node-child-process-outside-infra',
      severity: 'error',
      comment: 'Process spawning is I/O; domain/ and usecase/ may not import child_process.',
      from: { path: '^src/(domain|usecase)/' },
      to:   { path: '^(node:)?child_process$' },
    },

    // ── Tests do not bleed into production code (rule 1, structural) ─────────
    {
      name: 'no-tests-in-src',
      severity: 'error',
      comment:
        'Production code (anything in src/ that is not a *.spec.ts file) ' +
        'must not import from tests/.',
      from: { path: '^src/', pathNot: '\\.spec\\.ts$' },
      to:   { path: '^tests/' },
    },

    // ── No barrel files outside the single allowed exception (rule 4) ────────
    {
      name: 'no-barrel-imports',
      severity: 'error',
      comment:
        'Barrel files are forbidden. Import from the specific file. ' +
        'Single allowed exception: src/infra/http/index.ts (the routes builder).',
      from: { path: '^src/' },
      to:   {
        path: '^src/.*/index\\.ts$',
        pathNot: '^src/infra/http/index\\.ts$',
      },
    },

    // ── Circular dependencies (defensive; madge also catches these) ──────────
    {
      name: 'no-circular',
      severity: 'error',
      comment: 'Circular dependencies usually indicate a misplaced module or a missing aggregate boundary.',
      from: {},
      to:   { circular: true },
    },

    // ── Orphan modules (defensive; knip also catches these) ──────────────────
    {
      name: 'no-orphans',
      severity: 'warn',
      comment: 'Orphan modules are unused; consider deleting them.',
      from: {
        orphan: true,
        pathNot: [
          '\\.(spec|test)\\.ts$',
          '^src/main\\.ts$',
          '^src/config/env\\.ts$',
          '^\\.[^/]+\\.(js|cjs|mjs|ts)$',  // root config files
        ],
      },
      to: {},
    },

    // ── Composition root is the only place that may instantiate infra ──────
    // Note: `dependency-cruiser` cannot detect `new ClassName()` directly.
    // ESLint's `no-restricted-syntax` (NewExpression) covers this — see .eslintrc.cjs.
  ],

  options: {
    doNotFollow: { path: 'node_modules' },
    tsConfig: { fileName: 'tsconfig.json' },
    enhancedResolveOptions: {
      exportsFields: ['exports'],
      conditionNames: ['import', 'require', 'node', 'default'],
      mainFields: ['main', 'types'],
    },
    reporterOptions: {
      dot:    { theme: { graph: { rankdir: 'TD' } } },
      archi:  { collapsePattern: '^src/(domain|usecase|infra|config)(/[^/]+)?' },
    },
  },
};
