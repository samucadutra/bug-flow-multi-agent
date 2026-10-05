/**
 * ESLint config for Clean Architecture projects.
 *
 * Combines TS strict rules with `no-restricted-syntax` selectors that enforce
 * the structural prescriptions in `~/.claude/skills/clean-arch/SKILL.md` —
 * specifically the rules that depend on AST shape (a `set` keyword in domain,
 * `try/catch` in handlers, instantiation of infra outside main.ts, etc.).
 *
 * Pair with .dependency-cruiser.cjs (cross-layer imports) and
 * scripts/check-architecture.ts (semantic structural checks).
 */

/** @type {import('eslint').Linter.Config} */
module.exports = {
  root: true,
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 2023,
    sourceType: 'module',
    project: './tsconfig.json',
  },
  plugins: ['@typescript-eslint'],
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:@typescript-eslint/recommended-requiring-type-checking',
  ],
  rules: {
    // ── Structural: SRP — one class per file ────────────────────────────────
    'max-classes-per-file': ['error', 1],

    // ── Visibility — entity invariants depend on private/public clarity ────
    // Members are public-by-default in TS. We forbid the redundant `public`
    // modifier and require `private`/`protected` to be explicit.
    '@typescript-eslint/explicit-member-accessibility': [
      'error',
      { accessibility: 'no-public' },
    ],

    // ── Unused vars — allow `_`-prefixed for intentionally unused ──────────
    '@typescript-eslint/no-unused-vars': [
      'error',
      { argsIgnorePattern: '^_', varsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' },
    ],

    // ── No `any` shortcut ───────────────────────────────────────────────────
    '@typescript-eslint/no-explicit-any': 'error',
    '@typescript-eslint/no-unsafe-assignment': 'warn',
    '@typescript-eslint/no-unsafe-member-access': 'warn',
    '@typescript-eslint/no-unsafe-call': 'warn',

    // ── Imports ─────────────────────────────────────────────────────────────
    '@typescript-eslint/consistent-type-imports': ['error', { prefer: 'type-imports' }],
    'no-restricted-imports': [
      'error',
      {
        patterns: [
          { group: ['../*'], message: 'Use absolute imports (@/...) instead of deep relative imports.' },
        ],
      },
    ],
  },
  overrides: [
    // ────────────────────────────────────────────────────────────────────────
    // src/config/env.ts — the ONLY file that may read process.env (rule 2)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/config/env.ts'],
      rules: {
        // process.env is allowed here; no further restrictions.
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // Everywhere else — process.env is forbidden (rule 2 / anti-pattern A3)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/**/*.ts'],
      excludedFiles: ['src/config/env.ts'],
      rules: {
        'no-restricted-syntax': [
          'error',
          {
            selector: "MemberExpression[object.name='process'][property.name='env']",
            message: 'process.env is forbidden outside src/config/env.ts. Read config there and inject values via constructor.',
          },
        ],
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // domain/ — no `set` keyword (rule 6 / A6)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/domain/**/*.ts'],
      excludedFiles: ['**/*.spec.ts'],
      rules: {
        'no-restricted-syntax': [
          'error',
          {
            selector: 'MethodDefinition[kind="set"]',
            message: 'Setters (`set foo(v)`) are forbidden in domain/. Use a domain-named method instead (e.g., changeEmail(), suspend()).',
          },
        ],
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // infra/http/**/*.handler.ts — no try/catch (rule 16 / A20)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/infra/http/**/*.handler.ts'],
      rules: {
        'no-restricted-syntax': [
          'error',
          {
            selector: 'TryStatement',
            message: 'try/catch is forbidden in handlers. Let exceptions propagate; main.ts catches once and routes via toHttpResponse(err).',
          },
        ],
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // usecase/ — no `new` of imported infra concrete classes (rule 11 / A12, A27)
    // Note: this rule covers the most common pattern (named imports). It is
    // complemented by check-architecture.ts which performs deeper checks.
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/usecase/**/*.ts'],
      excludedFiles: ['**/*.spec.ts'],
      rules: {
        'no-restricted-imports': [
          'error',
          {
            patterns: [
              {
                group: ['@/infra/*', '../infra/*', '../../infra/*'],
                message:
                  'usecase/ may not import from infra/. Depend on interfaces from domain/. Composition root in main.ts wires implementations.',
              },
            ],
          },
        ],
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // infra/http/**/*.handler.ts — no `new` of repositories/queries/gateways
    // (handlers receive use cases via constructor; never instantiate)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['src/infra/http/**/*.handler.ts'],
      rules: {
        'no-restricted-imports': [
          'error',
          {
            patterns: [
              {
                group: ['@/infra/repository/*', '@/infra/queries/*', '@/infra/gateway/*'],
                message:
                  'Handlers may not import repositories, queries, or gateways. They receive use cases via constructor.',
              },
            ],
          },
        ],
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // errors.ts — multi-class file is allowed (and required) (rule 6 / domain-modeling)
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['**/errors.ts'],
      rules: {
        'max-classes-per-file': 'off',
      },
    },

    // ────────────────────────────────────────────────────────────────────────
    // Tests — relax some rules
    // ────────────────────────────────────────────────────────────────────────
    {
      files: ['**/*.spec.ts'],
      rules: {
        '@typescript-eslint/no-explicit-any': 'off',
        '@typescript-eslint/no-unsafe-assignment': 'off',
        '@typescript-eslint/no-unsafe-member-access': 'off',
        '@typescript-eslint/no-unsafe-call': 'off',
        'max-classes-per-file': 'off',
        'no-restricted-imports': 'off',
      },
    },
  ],
};
