# Composition root

Deep dive on `main.ts`, the wiring order, the framework-agnostic HTTP adapter, and the opt-in Unit of Work mechanism. Read alongside `SKILL.md` rules 4 (no barrels except `infra/http/index.ts`), 11 (DI by constructor), 16 (handler shape), and `anti-patterns.md` A12, A27.

The composition root is **the only place** in the codebase where concrete classes from `infra/` are instantiated with `new`. Everywhere else, dependencies arrive through constructors. There is no DI container, no service locator, no decorator magic. The dependency graph is explicit code in one file.

---

## 1. The HTTP adapter

The skill's HTTP layer is **framework-agnostic by contract**. Handlers and routes do not import Express, Fastify, or any other server library. They speak in terms of two own types — `HttpRequest` and `HttpResponse` — and a `Handler` interface.

### Types

```ts
// infra/http/types.ts
export type HttpRequest = {
  method: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  path: string;
  params: Record<string, string>;
  query: Record<string, string | string[] | undefined>;
  body: unknown;
  headers: Record<string, string | string[] | undefined>;
  user?: { id: string; isAdmin: boolean };  // populated by auth middleware
};

export type HttpResponse = {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
};

export type HttpRoute = {
  method: HttpRequest['method'];
  path: string;
  handler: Handler;
};
```

### Handler interface

```ts
// infra/http/handler.ts
import type { HttpRequest, HttpResponse } from './types';

export interface Handler {
  handle(req: HttpRequest): Promise<HttpResponse>;
}
```

Every handler implements this interface. One class, one method, no other shape.

### Routes export

Each feature folder under `infra/http/` exports a function that takes its handler dependencies and returns `HttpRoute[]`:

```ts
// infra/http/user/user.routes.ts
import type { HttpRoute } from '@/infra/http/types';
import type { CreateUserHandler } from './create-user.handler';
import type { AuthenticateUserHandler } from './authenticate-user.handler';
import type { ListUsersHandler } from './list-users.handler';

export type UserRoutesDeps = {
  createUserHandler: CreateUserHandler;
  authenticateUserHandler: AuthenticateUserHandler;
  listUsersHandler: ListUsersHandler;
};

export const userRoutes = (deps: UserRoutesDeps): HttpRoute[] => [
  { method: 'POST', path: '/users',          handler: deps.createUserHandler },
  { method: 'POST', path: '/users/login',    handler: deps.authenticateUserHandler },
  { method: 'GET',  path: '/users',          handler: deps.listUsersHandler },
];
```

### Aggregator (`infra/http/index.ts`)

This is the **single allowed `index.ts`**. It composes per-feature route arrays into a single list:

```ts
// infra/http/index.ts
import type { HttpRoute } from './types';
import { userRoutes, type UserRoutesDeps } from './user/user.routes';
import { videoRoutes, type VideoRoutesDeps } from './video/video.routes';
// ... other features

export type HttpDeps = UserRoutesDeps & VideoRoutesDeps /* & ... */;

export const buildHttpRoutes = (deps: HttpDeps): HttpRoute[] => [
  ...userRoutes(deps),
  ...videoRoutes(deps),
  // ...
];
```

`buildHttpRoutes` is the boundary between the application's structured layers and the framework adapter that follows.

### The framework adapter (in `main.ts` only)

Express, Fastify, Hono, raw `node:http` — all work. The bridge is a small piece of code in `main.ts` that translates between the framework's request/response types and the skill's `HttpRequest` / `HttpResponse`.

Example with Express:

```ts
// main.ts (excerpt)
import express, { type Request, type Response } from 'express';
import type { HttpRoute } from './infra/http/types';
import { toHttpResponse } from './infra/http/error-handler';

const adapt = (route: HttpRoute) => async (req: Request, res: Response) => {
  const httpReq = {
    method: route.method,
    path: route.path,
    params: req.params,
    query: req.query as Record<string, string | string[] | undefined>,
    body: req.body,
    headers: req.headers as Record<string, string | string[] | undefined>,
    user: (req as any).user,
  };
  let httpRes;
  try {
    httpRes = await route.handler.handle(httpReq);
  } catch (err) {
    httpRes = toHttpResponse(err);
  }
  if (httpRes.headers) for (const [k, v] of Object.entries(httpRes.headers)) res.setHeader(k, v);
  res.status(httpRes.status);
  if (httpRes.body !== undefined) res.json(httpRes.body);
  else res.end();
};

const app = express();
app.use(express.json());
app.use(authMiddleware);   // populates req.user
for (const r of routes) {
  app[r.method.toLowerCase() as 'get'](r.path, adapt(r));
}
app.listen(config.port);
```

Switching to Fastify means rewriting `adapt` and the `app.use` / `app.listen` calls. The handlers, use cases, repos — none of them change. The skill's framework-agnosticism lives entirely in this 30-line bridge.

### Why `try/catch` around `route.handler.handle` lives in `main.ts`

Rule 16 forbids `try/catch` in handlers. Errors propagate up. The adapter (in `main.ts`, framework-specific) catches them once at the boundary and feeds them into `toHttpResponse(err)`, which maps every `AppError` subclass to a status/code response. See `error-handling.md` for the mapping.

---

## 2. The composition root

`main.ts` instantiates the dependency graph in topological order, then starts the server. Read top to bottom; every `new` happens here.

```ts
// main.ts
import express from 'express';
import { PrismaClient } from '@prisma/client';
import OpenAI from 'openai';

import { config } from './config/env';

import { PrismaUnitOfWork } from './infra/persistence/prisma-unit-of-work';

import { UserPrismaRepository }  from './infra/repository/user/user.prisma-repository';
import { VideoPrismaRepository } from './infra/repository/video/video.prisma-repository';
import { UserPrismaQueries }     from './infra/queries/user/user.prisma-queries';
import { VideoPrismaQueries }    from './infra/queries/video/video.prisma-queries';

import { OpenAITranscriptionEngine } from './infra/gateway/openai-transcription.gateway';

import { CreateUserUseCase }       from './usecase/user/create-user.usecase';
import { AuthenticateUserUseCase } from './usecase/user/authenticate-user.usecase';
import { ListUsersUseCase }        from './usecase/user/list-users.usecase';
import { UploadVideoUseCase }      from './usecase/video/upload-video.usecase';

import { CreateUserHandler }       from './infra/http/user/create-user.handler';
import { AuthenticateUserHandler } from './infra/http/user/authenticate-user.handler';
import { ListUsersHandler }        from './infra/http/user/list-users.handler';
import { UploadVideoHandler }      from './infra/http/video/upload-video.handler';

import { buildHttpRoutes } from './infra/http';
import { authMiddleware } from './infra/http/middleware/auth';
import { toHttpResponse } from './infra/http/error-handler';

// 1. Singletons (clients, connections)
const prisma = new PrismaClient({ datasourceUrl: config.databaseUrl });
const openai = new OpenAI({ apiKey: config.openaiApiKey });

// 2. Cross-cutting infra (UoW)
const uow = new PrismaUnitOfWork(prisma);

// 3. Repositories, queries, gateways
const userRepo  = new UserPrismaRepository(prisma);
const videoRepo = new VideoPrismaRepository(prisma);

const userQueries  = new UserPrismaQueries(prisma);
const videoQueries = new VideoPrismaQueries(prisma);

const transcriptionEngine = new OpenAITranscriptionEngine(openai);

// 4. Use cases
const createUser       = new CreateUserUseCase(userRepo);
const authenticateUser = new AuthenticateUserUseCase(userRepo);
const listUsers        = new ListUsersUseCase(userRepo, userQueries);
const uploadVideo      = new UploadVideoUseCase(videoRepo, transcriptionEngine);

// 5. Handlers
const createUserHandler       = new CreateUserHandler(createUser);
const authenticateUserHandler = new AuthenticateUserHandler(authenticateUser);
const listUsersHandler        = new ListUsersHandler(listUsers);
const uploadVideoHandler      = new UploadVideoHandler(uploadVideo);

// 6. Routes
const routes = buildHttpRoutes({
  createUserHandler,
  authenticateUserHandler,
  listUsersHandler,
  uploadVideoHandler,
});

// 7. Server
const app = express();
app.use(express.json());
app.use(authMiddleware);
for (const r of routes) {
  app[r.method.toLowerCase() as 'get'](r.path, async (req, res) => {
    let httpRes;
    try {
      httpRes = await r.handler.handle({
        method: r.method, path: r.path,
        params: req.params,
        query: req.query as Record<string, string | string[] | undefined>,
        body: req.body,
        headers: req.headers as Record<string, string | string[] | undefined>,
        user: (req as any).user,
      });
    } catch (err) {
      httpRes = toHttpResponse(err);
    }
    if (httpRes.headers) for (const [k, v] of Object.entries(httpRes.headers)) res.setHeader(k, v);
    res.status(httpRes.status);
    if (httpRes.body !== undefined) res.json(httpRes.body); else res.end();
  });
}
app.listen(config.port, () => console.log(`listening on :${config.port}`));
```

### Wiring order — strictly top-down

The order matters: each step depends only on previous steps.

1. **Singletons**: `PrismaClient`, `OpenAI` client, anything stateful tied to a connection. One per process.
2. **Cross-cutting infra**: `UnitOfWork`, central caches.
3. **Repositories, Queries, Gateways**: take singletons, expose domain interfaces.
4. **Use cases**: take repositories/queries/gateways/UoW, expose `execute(input): output`.
5. **Handlers**: take use cases, implement `Handler.handle(req)`.
6. **Routes**: collect handlers into the `HttpRoute[]` aggregator.
7. **Server**: bind routes to the chosen framework, start listening.

Each layer depends only on the layers above. `usecase` knows nothing about `Handler`; `Handler` knows nothing about `express`. The composition is the only file that violates this (it has to — it is the wiring).

### `process.env` lives only in `config/env.ts`

The `config` import provides typed values (`config.port`, `config.databaseUrl`, `config.openaiApiKey`). Nowhere else in the codebase reads from `process.env`. See `config-and-env.md`.

---

## 3. Unit of Work — opt-in mechanism

`UnitOfWork` is **not used by every use case**. Single-write use cases ignore it. It is opt-in for use cases that write to multiple aggregates atomically.

### The interface

```ts
// domain/_shared/unit-of-work.ts
export interface UnitOfWork {
  run<T>(work: () => Promise<T>): Promise<T>;
}
```

The contract is small: pass a function, the UoW runs it inside a transaction, returns the result.

### The transaction context

The implementation uses `AsyncLocalStorage` to carry the current transaction client across async calls without threading it through every function signature.

```ts
// infra/persistence/transaction-context.ts
import { AsyncLocalStorage } from 'node:async_hooks';
import type { PrismaClient, Prisma } from '@prisma/client';

type TxClient = Prisma.TransactionClient | PrismaClient;

const storage = new AsyncLocalStorage<TxClient>();

export const withTransaction = async <T>(client: Prisma.TransactionClient, fn: () => Promise<T>): Promise<T> =>
  storage.run(client, fn);

export const currentClient = (fallback: PrismaClient): TxClient => storage.getStore() ?? fallback;
```

### The Prisma implementation

```ts
// infra/persistence/prisma-unit-of-work.ts
import type { PrismaClient } from '@prisma/client';
import type { UnitOfWork } from '@/domain/_shared/unit-of-work';
import { withTransaction } from './transaction-context';

export class PrismaUnitOfWork implements UnitOfWork {
  constructor(private readonly prisma: PrismaClient) {}

  run<T>(work: () => Promise<T>): Promise<T> {
    return this.prisma.$transaction((tx) => withTransaction(tx, work));
  }
}
```

### How repositories pick up the transaction

Every repository implementation routes its DB calls through `currentClient(this.prisma)` (see `repository-and-queries.md`). When the call is inside `uow.run`, the AsyncLocalStorage returns the active `tx`. Outside, it returns the fallback (the regular `PrismaClient`). The repository code is identical in both cases — no parameter to thread.

### Use case usage

```ts
// usecase/user/register-user.usecase.ts (cross-feature: User + Profile)
async execute(input) {
  return this.uow.run(async () => {
    const user = User.create({ email: input.email, password: input.password });
    const profile = Profile.createDefault(user.id);
    await this.userRepo.save(user);
    await this.profileRepo.save(profile);
    return toOutput(user);
  });
}
```

If `profileRepo.save` throws, the entire transaction rolls back. `userRepo.save` did its work inside the same `tx` and is rolled back as well.

### Why not always use UoW

Most use cases write to a single aggregate. Wrapping every save in `uow.run` is overhead with no benefit. The `UnitOfWork` is a deliberate marker: "this operation crosses aggregate boundaries; here is the atomicity boundary."

If you find yourself wanting to use `UnitOfWork` frequently, you may have aggregates that should be merged. See `domain-modeling.md` (aggregates) and `domain-events.md` (eventual consistency for cross-aggregate side effects).

### Other ORMs

The pattern transfers:
- **TypeORM**: `dataSource.transaction((entityManager) => withTransaction(entityManager, work))` — the manager replaces the Prisma `tx`.
- **Kysely**: `kysely.transaction().execute((trx) => withTransaction(trx, work))` — same shape.
- **Mongoose**: sessions instead of transaction clients; same `AsyncLocalStorage` approach.
- **node-postgres pool**: acquire a client, `BEGIN`, run work, `COMMIT` / `ROLLBACK`.

Each implementation provides `<Provider>UnitOfWork` and a `transaction-context.ts` adapter that knows the provider's transaction object type. The interface in `domain/_shared/unit-of-work.ts` does not change.

---

## 4. Common pitfalls

| Pitfall                                                          | Fix                                              | See      |
|------------------------------------------------------------------|--------------------------------------------------|----------|
| `new` of an `infra/` class outside `main.ts`                     | Inject via constructor; instantiate only here    | A12, A27 |
| Adding a DI container (Inversify, tsyringe)                      | Stay with manual composition; the file is small  | rule 11  |
| `process.env.X` inside the composition root                      | Read it via `config.x` from `config/env.ts`      | A3       |
| Reading env vars outside `config/env.ts`                         | Move all reads to `config/env.ts`                | A3       |
| `try/catch` inside a handler                                     | Let exceptions propagate; the adapter catches    | A20      |
| Wrapping every save in `UnitOfWork` reflexively                  | Use it only for cross-aggregate atomic writes    | section 3 |
| Repository accessing `this.prisma` directly (skipping context)   | Always use `currentClient(this.prisma)`          | section 3 |
| Adding a barrel `index.ts` outside `infra/http/index.ts`         | Import from specific files                       | rule 4   |

---

## Cross-references

- **`SKILL.md` rules**: 4 (single allowed `index.ts`), 11 (DI by constructor), 16 (handler shape), 17 (entity not serialized), 18 (auth in middleware).
- **`anti-patterns.md`**: A12 (`new` in use case), A20 (try/catch in handler), A27 (instantiation outside composition root).
- **`use-case-pattern.md`**: how use cases consume the contracts that the composition root wires.
- **`repository-and-queries.md`**: how `currentClient(this.prisma)` enables transaction awareness.
- **`config-and-env.md`**: env var loading and validation.
- **`error-handling.md`**: `toHttpResponse(err)` and the central error mapping.
- **`authorization.md`**: how auth middleware populates `req.user`.
