#!/usr/bin/env tsx
/**
 * Architecture fitness function — Gate 4 of the self-audit.
 *
 * Runs structural checks that dependency-cruiser and ESLint cannot express:
 * SRP on use case classes, factory shape on entities, in-memory implementation
 * presence, naming-suffix enforcement, _shared whitelist, etc.
 *
 * Run with:  npx tsx scripts/check-architecture.ts
 *
 * Exits with non-zero status if any violation is found.
 *
 * The checks below mirror prescriptions in `~/.claude/skills/clean-arch/SKILL.md`
 * and `~/.claude/skills/clean-arch/references/anti-patterns.md`. When changing
 * the architecture, update both this script and those documents in lock-step.
 */

import { readdirSync, statSync, readFileSync, existsSync } from 'node:fs';
import { join, relative, basename, dirname } from 'node:path';

const SRC = 'src';

type Violation = { file: string; rule: string; message: string };
const violations: Violation[] = [];

const report = (file: string, rule: string, message: string) =>
  violations.push({ file, rule, message });

// ── Walk helpers ────────────────────────────────────────────────────────────

const walk = (dir: string): string[] => {
  if (!existsSync(dir)) return [];
  const entries: string[] = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    const st = statSync(full);
    if (st.isDirectory()) entries.push(...walk(full));
    else entries.push(full);
  }
  return entries;
};

const allTsFiles = walk(SRC).filter((f) => f.endsWith('.ts') && !f.endsWith('.spec.ts'));
const allFiles = walk(SRC);

// ── Rule: domain/_shared whitelist ──────────────────────────────────────────
{
  const SHARED = join(SRC, 'domain', '_shared');
  const ALLOWED = new Set([
    'id.vo.ts',
    'errors.ts',
    'unit-of-work.ts',
    'pagination.ts',
    'event.ts',          // opt-in, when domain events are adopted
  ]);
  if (existsSync(SHARED)) {
    for (const file of readdirSync(SHARED)) {
      if (file.endsWith('.spec.ts')) continue;
      if (!ALLOWED.has(file)) {
        report(
          join(SHARED, file),
          'shared-whitelist',
          `domain/_shared/ accepts only ${[...ALLOWED].join(', ')}. Move "${file}" to a feature folder.`,
        );
      }
    }
  }
}

// ── Rule: naming suffix per location ────────────────────────────────────────
{
  type SuffixRule = { dirPattern: RegExp; allowedSuffixes: RegExp[]; description: string };
  // Note: _shared/ has its own whitelist rule above; middleware/ is structural, not a feature folder.
  const RULES: SuffixRule[] = [
    {
      dirPattern: /^src\/domain\/(?!_shared\/)[^/]+\/$/,
      allowedSuffixes: [
        /\.entity\.ts$/, /\.vo\.ts$/, /\.repository\.ts$/, /\.queries\.ts$/,
        /\.gateway\.ts$/, /^errors\.ts$/, /^events\.ts$/, /\.spec\.ts$/,
      ],
      description: 'domain feature files: *.entity.ts, *.vo.ts, *.repository.ts, *.queries.ts, *.gateway.ts, errors.ts, events.ts',
    },
    {
      dirPattern: /^src\/usecase\/[^/]+\/$/,
      allowedSuffixes: [/\.usecase\.ts$/, /\.dto\.ts$/, /\.spec\.ts$/],
      description: 'usecase feature files: *.usecase.ts, *.dto.ts',
    },
    {
      dirPattern: /^src\/infra\/repository\/[^/]+\/$/,
      allowedSuffixes: [/\.[a-z-]+-repository\.ts$/, /\.in-memory-repository\.ts$/, /\.mapper\.ts$/, /\.spec\.ts$/],
      description: 'infra/repository feature files: *.<provider>-repository.ts, *.in-memory-repository.ts, *.mapper.ts',
    },
    {
      dirPattern: /^src\/infra\/queries\/[^/]+\/$/,
      allowedSuffixes: [/\.[a-z-]+-queries\.ts$/, /\.in-memory-queries\.ts$/, /\.spec\.ts$/],
      description: 'infra/queries feature files: *.<provider>-queries.ts, *.in-memory-queries.ts',
    },
    {
      dirPattern: /^src\/infra\/http\/(?!middleware\/)[^/]+\/$/,
      allowedSuffixes: [/\.handler\.ts$/, /\.routes\.ts$/, /\.spec\.ts$/],
      description: 'infra/http feature files: *.handler.ts, *.routes.ts',
    },
  ];

  for (const file of allFiles) {
    const dir = dirname(file) + '/';
    const name = basename(file);
    const dirRel = dir.startsWith('./') ? dir.slice(2) : dir;
    for (const rule of RULES) {
      if (rule.dirPattern.test(dirRel)) {
        if (!rule.allowedSuffixes.some((rx) => rx.test(name))) {
          report(file, 'naming-suffix', `Unexpected file in ${dirRel}. Allowed: ${rule.description}`);
        }
        break;
      }
    }
  }
}

// ── Rule: kebab-case file names ────────────────────────────────────────────
{
  // Each dot-separated segment: lowercase alphanumeric, optional internal hyphens.
  const KEBAB = /^[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)*$/;
  for (const file of allFiles) {
    const name = basename(file);
    if (name.startsWith('.')) continue;
    if (name === 'README.md') continue;
    if (!KEBAB.test(name)) {
      report(file, 'kebab-case', `File name "${name}" must be kebab-case (lowercase, hyphen-separated).`);
    }
  }
}

// ── Rule: use case class has exactly one public method `execute` (SRP) ─────
{
  const useCaseFiles = allTsFiles.filter((f) => f.endsWith('.usecase.ts'));
  for (const file of useCaseFiles) {
    const src = readFileSync(file, 'utf8');
    // Naive: count `public` method declarations + non-prefixed methods inside `class ... UseCase`.
    const classMatch = src.match(/class\s+\w*UseCase\s*{([\s\S]*?)\n}/);
    if (!classMatch) {
      report(file, 'usecase-class-shape', 'Could not locate `class ... UseCase { ... }` in a *.usecase.ts file.');
      continue;
    }
    const body = classMatch[1] ?? '';
    // Strip nested braces' bodies to avoid counting inner functions.
    let depth = 0;
    let stripped = '';
    for (const ch of body) {
      if (ch === '{') depth++;
      else if (ch === '}') depth--;
      else if (depth === 0) stripped += ch;
    }
    // Public methods: lines starting with `async ` or `public ` or method-like signatures
    // (excluding constructor and private/protected).
    const lines = stripped.split('\n').map((l) => l.trim()).filter(Boolean);
    const publicMethods: string[] = [];
    for (const line of lines) {
      if (/^constructor\s*\(/.test(line)) continue;
      if (/^(private|protected)\s/.test(line)) continue;
      const m = line.match(/^(?:public\s+)?(?:async\s+)?(\w+)\s*[<(]/);
      if (m && m[1]) publicMethods.push(m[1]);
    }
    if (publicMethods.length !== 1 || publicMethods[0] !== 'execute') {
      report(
        file,
        'usecase-single-execute',
        `Use case must have exactly one public method named "execute". Found: [${publicMethods.join(', ') || 'none'}].`,
      );
    }
  }
}

// ── Rule: every <feature>.<provider>-repository.ts has a sibling <feature>.in-memory-repository.ts (LSP)
{
  const repoFiles = allTsFiles.filter(
    (f) => /infra\/repository\/[^/]+\/[^/]+\.[a-z-]+-repository\.ts$/.test(f.replace(/\\/g, '/')) &&
           !f.endsWith('in-memory-repository.ts'),
  );
  for (const file of repoFiles) {
    const dir = dirname(file);
    const featurePrefix = basename(file).split('.')[0];
    const expected = join(dir, `${featurePrefix}.in-memory-repository.ts`);
    if (!existsSync(expected)) {
      report(file, 'missing-in-memory-repo', `Missing fake: ${relative('.', expected)}. Every Repository implementation needs an in-memory counterpart (LSP).`);
    }
  }
}

// ── Rule: every <feature>.<provider>-queries.ts has a sibling in-memory queries
{
  const queryFiles = allTsFiles.filter(
    (f) => /infra\/queries\/[^/]+\/[^/]+\.[a-z-]+-queries\.ts$/.test(f.replace(/\\/g, '/')) &&
           !f.endsWith('in-memory-queries.ts'),
  );
  for (const file of queryFiles) {
    const dir = dirname(file);
    const featurePrefix = basename(file).split('.')[0];
    const expected = join(dir, `${featurePrefix}.in-memory-queries.ts`);
    if (!existsSync(expected)) {
      report(file, 'missing-in-memory-queries', `Missing fake: ${relative('.', expected)}. Every Queries implementation needs an in-memory counterpart (LSP).`);
    }
  }
}

// ── Rule: every <action>-<feature>.usecase.ts has a sibling <action>-<feature>.dto.ts
{
  const useCases = allTsFiles.filter((f) => f.endsWith('.usecase.ts'));
  for (const file of useCases) {
    const expected = file.replace(/\.usecase\.ts$/, '.dto.ts');
    if (!existsSync(expected)) {
      report(file, 'missing-dto', `Missing companion DTO: ${relative('.', expected)}.`);
    }
  }
}

// ── Rule: ListX / SearchX use cases include PageInput in their input
{
  const useCases = allTsFiles.filter((f) => /\/(list|search)-[^/]+\.usecase\.ts$/.test(f.replace(/\\/g, '/')));
  for (const file of useCases) {
    const dtoFile = file.replace(/\.usecase\.ts$/, '.dto.ts');
    if (!existsSync(dtoFile)) continue; // missing-dto rule already flags it
    const src = readFileSync(dtoFile, 'utf8');
    if (!/PageInput/.test(src)) {
      report(dtoFile, 'list-page-input', 'List/Search use case input must include `PageInput` (intersection or extension).');
    }
  }
}

// ── Rule: entity has a private constructor and `static create` / `static restore`
{
  const entityFiles = allTsFiles.filter((f) => f.endsWith('.entity.ts'));
  for (const file of entityFiles) {
    const src = readFileSync(file, 'utf8');
    if (!/private\s+constructor\s*\(/.test(src)) {
      report(file, 'entity-private-constructor', 'Entity must have a `private constructor(...)`.');
    }
    if (!/static\s+create\s*\(/.test(src)) {
      report(file, 'entity-create-factory', 'Entity must define `static create(...)`.');
    }
    if (!/static\s+restore\s*\(/.test(src)) {
      report(file, 'entity-restore-factory', 'Entity must define `static restore(...)` for repository rehydration.');
    }
  }
}

// ── Rule: VO has a private constructor and `static create`
{
  const voFiles = allTsFiles.filter((f) => f.endsWith('.vo.ts') && !f.endsWith('id.vo.ts'));
  for (const file of voFiles) {
    const src = readFileSync(file, 'utf8');
    if (!/(private|protected)\s+constructor\s*\(/.test(src)) {
      report(file, 'vo-private-constructor', 'VO must have a `private constructor(...)` (or protected when extended).');
    }
    if (!/static\s+create\s*\(/.test(src)) {
      report(file, 'vo-create-factory', 'VO must define `static create(...)` that validates input.');
    }
  }
}

// ── Rule: handler has a `handle` method (no try/catch — covered by ESLint)
{
  const handlerFiles = allTsFiles.filter((f) => f.endsWith('.handler.ts'));
  for (const file of handlerFiles) {
    const src = readFileSync(file, 'utf8');
    if (!/\bhandle\s*\(/.test(src)) {
      report(file, 'handler-method', 'Handler must define `handle(req)` method.');
    }
  }
}

// ── Rule: no `set` keyword in domain (belt-and-suspenders with ESLint)
{
  const SETTER_RE = /^\s*(public\s+|private\s+|protected\s+)?set\s+\w+\s*\(/m;
  for (const file of allTsFiles) {
    if (!file.includes(`${SRC}/domain/`)) continue;
    const src = readFileSync(file, 'utf8');
    if (SETTER_RE.test(src)) {
      report(file, 'no-set-in-domain', 'domain/ files may not declare setters (`set foo(v)`). Use a domain-named method.');
    }
  }
}

// ── Rule: forbidden folder names inside usecase/ (no _shared/cross/multi/common)
{
  const USECASE = join(SRC, 'usecase');
  const FORBIDDEN = new Set(['_shared', 'cross', 'multi', 'common', 'shared']);
  if (existsSync(USECASE)) {
    for (const name of readdirSync(USECASE)) {
      const full = join(USECASE, name);
      if (statSync(full).isDirectory() && FORBIDDEN.has(name)) {
        report(full, 'usecase-forbidden-folder', `usecase/${name}/ is forbidden. Place use cases in the primary aggregate's folder, or create a named composite-flow folder (e.g., user-onboarding/).`);
      }
    }
  }
}

// ── Rule: tests are co-located (no orphan tests in folders without a sibling source)
{
  const specFiles = allFiles.filter((f) => f.endsWith('.spec.ts'));
  for (const spec of specFiles) {
    const sourceFile = spec.replace(/\.spec\.ts$/, '.ts');
    if (!existsSync(sourceFile)) {
      report(spec, 'orphan-test', `Test file has no sibling source. Expected: ${relative('.', sourceFile)}.`);
    }
  }
}

// ── Report ──────────────────────────────────────────────────────────────────

if (violations.length === 0) {
  console.log('✓ check-architecture: no violations');
  process.exit(0);
}

console.error(`✗ check-architecture: ${violations.length} violation(s)\n`);
for (const v of violations) {
  console.error(`  [${v.rule}] ${v.file}`);
  console.error(`    → ${v.message}`);
}
process.exit(1);
