# Config and environment

Deep dive on `src/config/env.ts`, the typed `config` object, and why `process.env` is restricted to that single file. Read alongside `SKILL.md` rule 2 and `anti-patterns.md` A3.

`config/` is the only top-level folder in `src/` besides the three layers (`domain/`, `usecase/`, `infra/`). It is small (one file by default), but its discipline matters: it is the seam where the outside world (environment variables) becomes typed, validated, in-process state.

---

## 1. The shape

```ts
// src/config/env.ts
import { z } from 'zod';

const schema = z.object({
  port:           z.coerce.number().int().min(1).max(65535).default(3000),
  databaseUrl:    z.string().url(),
  sessionSecret:  z.string().min(32),
  openaiApiKey:   z.string().min(1),
  storageRoot:    z.string().default('/var/lib/videomax'),
  logLevel:       z.enum(['debug', 'info', 'warn', 'error']).default('info'),
});

const parsed = schema.safeParse({
  port:           process.env['PORT'],
  databaseUrl:    process.env['DATABASE_URL'],
  sessionSecret:  process.env['SESSION_SECRET'],
  openaiApiKey:   process.env['OPENAI_API_KEY'],
  storageRoot:    process.env['STORAGE_ROOT'],
  logLevel:       process.env['LOG_LEVEL'],
});

if (!parsed.success) {
  console.error('Invalid environment configuration:', parsed.error.flatten());
  process.exit(1);
}

export const config = Object.freeze(parsed.data);
export type Config = typeof config;
```

The pieces:

- **The schema** validates and coerces. `z.coerce.number()` turns the env-string into a number; `.url()` and `.min(32)` enforce shape. Required values omit `.default(...)`; optional values have one.
- **The parse** runs once at module load. Failure logs a flat list of issues and exits with code 1 — the process refuses to start with bad config. This is the right behavior: a misconfigured deploy fails immediately, not 30 minutes later when a code path first reads an undefined env var.
- **`config` is frozen.** No code can mutate `config.port` at runtime. Anyone who needs a different value gets it via dependency injection, not by reassigning the global.
- **`Config` type** is the single source of truth for the shape; consumers can type-import it.

---

## 2. Who reads `config`

Only **`main.ts`**. Every other file receives whatever it needs through constructor injection.

```ts
// main.ts
import { config } from './config/env';
import { PrismaClient } from '@prisma/client';
import OpenAI from 'openai';
import { OpenAITranscriptionEngine } from './infra/gateway/openai-transcription.gateway';
import { LocalDiskStorageGateway } from './infra/gateway/local-disk-storage.gateway';

const prisma = new PrismaClient({ datasourceUrl: config.databaseUrl });
const openai = new OpenAI({ apiKey: config.openaiApiKey });

const transcriptionEngine = new OpenAITranscriptionEngine(openai);
const storage = new LocalDiskStorageGateway(config.storageRoot);

const app = express();
// ...
app.listen(config.port);
```

Consumers (gateways, repos, handlers, use cases) never see `config`. They see the values they need:

```ts
// infra/gateway/local-disk-storage.gateway.ts
export class LocalDiskStorageGateway implements StorageGateway {
  constructor(private readonly root: string) {}    // ← receives the path, not the config object
  async store(file: Buffer, key: string) { /* uses this.root */ }
}
```

This makes each component self-contained: `LocalDiskStorageGateway` does not know what env var holds the root path, only that it has one. Tests can pass any path; the production composition reads from `config.storageRoot`. Same component, no environment coupling.

---

## 3. Why `process.env` is restricted

Three reasons:

### Single source of truth for what the app needs

Reading the schema in `env.ts` tells you exactly what environment variables the app expects. No grep, no surprise on first request. Operations teams have a complete checklist.

### Type safety at the boundary

`config.port` is `number`. `config.databaseUrl` is a non-empty URL string. `config.logLevel` is `'debug' | 'info' | 'warn' | 'error'`. The rest of the codebase consumes typed values; it does not also need to coerce or validate. Boundary parsing once, typed everywhere.

### Fail-fast on misconfiguration

The schema runs at module load. A missing or malformed env var crashes the process at startup, before the first request, before any work happens. Compared to `process.env.X` reads scattered across the codebase — where misconfiguration surfaces as a runtime exception in a specific code path, hours later under load — this is dramatically safer.

### Detection

`anti-patterns.md` A3 codifies this: ESLint `no-restricted-properties` (or `no-restricted-syntax` with selector `MemberExpression[object.name="process"][property.name="env"]`) bans `process.env` access in any file outside `src/config/env.ts`.

---

## 4. Required vs optional, defaults

The schema distinguishes:

| Pattern                            | Effect                                                             |
|------------------------------------|--------------------------------------------------------------------|
| `z.string().url()`                 | **Required**. Process exits if missing.                            |
| `z.string().url().default('...')`  | **Optional with default**. Falls back if missing.                  |
| `z.string().optional()`            | **Optional**. May be `undefined` (consumer must handle).            |
| `z.coerce.number().int().min(...)` | Required, with type coercion from string env value.                |

Pick required-by-default for anything the app cannot run without (`databaseUrl`, `sessionSecret`, `openaiApiKey`). Pick optional-with-default for things that have a sensible fallback (`port`, `logLevel`, `storageRoot`). Reserve `optional()` for genuinely optional features (a webhook URL that is only sent when present).

---

## 5. Multiple environments

The skill does **not** prescribe a `.env` file format or a loader (`dotenv`, `dotenv-flow`, etc.). The composition root may load a `.env` file before importing `config` if the project chooses:

```ts
// main.ts
import 'dotenv/config';   // optional — loads .env into process.env
import { config } from './config/env';
// ...
```

In production deployments, environment variables are typically injected by the platform (Docker, Kubernetes, the cloud provider). No `.env` file is needed; the schema validates whatever `process.env` holds at startup.

For tests that need to override config: do not mutate `process.env` and reload the module. Instead, design test entry points (or test-only `main.ts` variants) that bypass `config` entirely and pass values directly to constructors. This is consistent with the "consumers receive values, not config" principle.

---

## 6. What `config/` may NOT contain

Just `env.ts`. If the project grows further config-like concerns (feature flags loaded from a remote service, A/B test assignments), they do **not** go in `config/`:

- **Feature flags** are dynamic state; they belong to a `FeatureFlags` gateway in `infra/gateway/` with an interface in the consumer feature.
- **Per-request settings** are passed through the request, not read from a global.
- **Static constants** that are not environment-dependent live next to the consumer (`domain/<feature>/<feature>.constants.ts` if shared inside one feature).

`config/` is exclusively for parsing/validating the process's environment at startup. Nothing else.

---

## 7. Common pitfalls

| Pitfall                                                           | Fix                                                          | See   |
|-------------------------------------------------------------------|--------------------------------------------------------------|-------|
| `process.env.X` read inside a use case, repository, gateway, etc. | Move to `config/env.ts`; pass via constructor                | A3    |
| Default values scattered across the codebase (`x ?? 'default'`)   | Encode the default in the schema; consumers receive the resolved value | section 4 |
| Reading `process.env` after startup ("dynamic" config)            | Read once at startup; restart the process to change config   | section 3 |
| Mutating `config` at runtime                                      | `config` is frozen; create a new gateway / inject explicitly | rule 2 |
| Tests setting `process.env.X` and importing modules               | Pass values directly to constructors; bypass `config`         | section 5 |
| Adding non-env config (feature flags, constants) to `config/env.ts` | Use a gateway or constants file in the relevant feature      | section 6 |
| Validating env vars only when they are first used                 | Validate at startup; fail-fast with `process.exit(1)`         | section 3 |

---

## Cross-references

- **`SKILL.md` rules**: 2 (`process.env` only in `config/env.ts`).
- **`anti-patterns.md`**: A3 (process.env outside config).
- **`composition-root.md`**: how `main.ts` consumes `config` and forwards values to constructors.
- **`folder-structure.md`**: `config/` as the fourth top-level folder alongside the three layers.
