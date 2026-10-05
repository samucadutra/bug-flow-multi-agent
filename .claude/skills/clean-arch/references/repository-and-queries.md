# Repository, Queries, and Gateways

Deep dive on the contracts that the domain defines and `infra/` implements: write-side `Repository`, read-side `Queries`, and external-API `Gateway`. Read alongside `SKILL.md` rules 13–15 and `anti-patterns.md` A16–A19.

CQRS-lite is the rule: writes go through `Repository` (returns Entity); reads go through `Queries` (returns DTO). Same feature, two contracts, both interfaces in `domain/<feature>/`, both implementations in `infra/`.

---

## 1. Repository (write side)

A repository persists and retrieves **aggregates** as entities. One repository per aggregate root. Child entities and VOs inside the aggregate are not exposed via their own repository — they are part of the root.

### Canonical contract

Every `Repository<T, Id>` provides at minimum:

```ts
// domain/<feature>/<feature>.repository.ts
export interface FeatureRepository {
  findById(id: string): Promise<Feature | null>;
  save(aggregate: Feature): Promise<void>;     // upsert
  delete(id: string): Promise<void>;            // idempotent
}
```

`save` is upsert: it creates if the aggregate is new and updates if it exists. The use case never asks "is this new or existing?" — that decision is the repository's, based on `id`.

`delete` is idempotent: deleting a non-existent id is a no-op, not an error. This avoids ordering issues with retries and concurrent operations.

### Adding `findByX` methods

Repositories may add `findByX` methods **only for uniqueness checks needed by writes**. Examples:

- `findByEmail(email)` — needed by `CreateUserUseCase` to reject duplicate emails.
- `findByUsername(username)` — same logic, different field.

Listing methods (`findActive`, `findRecent`, `findByTag`) are **not** repository concerns — they belong in `Queries`. See section 2 and `anti-patterns.md` A17.

### Full example: `UserRepository`

```ts
// domain/user/user.repository.ts
import type { User } from './user.entity';

export interface UserRepository {
  findById(id: string): Promise<User | null>;
  findByEmail(email: string): Promise<User | null>;
  save(user: User): Promise<void>;
  delete(id: string): Promise<void>;
}
```

### Implementation

```ts
// infra/repository/user/user.prisma-repository.ts
import type { PrismaClient } from '@prisma/client';
import type { UserRepository } from '@/domain/user/user.repository';
import { UserMapper } from './user.mapper';
import { currentClient } from '@/infra/persistence/transaction-context';

export class UserPrismaRepository implements UserRepository {
  constructor(private readonly prisma: PrismaClient) {}

  async findById(id: string) {
    const row = await currentClient(this.prisma).user.findUnique({ where: { id } });
    return row ? UserMapper.toDomain(row) : null;
  }

  async findByEmail(email: string) {
    const row = await currentClient(this.prisma).user.findUnique({ where: { email } });
    return row ? UserMapper.toDomain(row) : null;
  }

  async save(user: User) {
    const data = UserMapper.toPersistence(user);
    await currentClient(this.prisma).user.upsert({
      where: { id: data.id },
      create: data,
      update: data,
    });
  }

  async delete(id: string) {
    await currentClient(this.prisma).user.delete({ where: { id } }).catch(() => {});
  }
}
```

Notes:
- The implementation file is named `<feature>.<provider>-repository.ts`. The class adds the provider qualifier: `UserPrismaRepository`.
- All methods route through `currentClient(this.prisma)` so the repository is **transaction-aware**: when the call sits inside `unitOfWork.run()`, the AsyncLocalStorage delivers the active transaction client. See `composition-root.md` for the mechanism.
- `delete` swallows the "not found" Prisma error to remain idempotent.

### Mapper

The mapper translates between the domain entity and the persistence row. It lives next to the implementation.

```ts
// infra/repository/user/user.mapper.ts
import type { User as PrismaUser } from '@prisma/client';
import { User } from '@/domain/user/user.entity';

export class UserMapper {
  static toDomain(row: PrismaUser): User {
    return User.restore({
      id: row.id,
      email: row.email,
      hashedPassword: row.hashedPassword,
      isSuspended: row.isSuspended,
      isAdmin: row.isAdmin,
      createdAt: row.createdAt,
    });
  }

  static toPersistence(user: User): PrismaUser {
    return {
      id: user.id,
      email: user.email,
      hashedPassword: user.hashedPassword,
      isSuspended: user.isSuspended,
      isAdmin: user.isAdmin,
      createdAt: user.createdAt,
    };
  }
}
```

Critical rules for mappers:

1. **`toDomain` always calls `User.restore`, never `User.create`.** This is the most common bug: calling `create` regenerates IDs, re-hashes passwords, re-validates fields. The entity is born new every read.
2. **Mappers are static methods, not instances.** They have no state and no dependencies.
3. **Mappers are owned by `infra/`**, not `domain/`. They translate between the persistence shape (which the ORM defines) and the domain shape. The domain does not know mappers exist.
4. **One mapper per repository implementation.** If the project has both `UserPrismaRepository` and `UserMongoRepository`, each has its own mapper file in its own folder.

### In-memory implementation (fake)

For local development and tests, every repository has an in-memory counterpart that satisfies the same contract. Lives next to the real implementation.

```ts
// infra/repository/user/user.in-memory-repository.ts
import type { UserRepository } from '@/domain/user/user.repository';
import type { User } from '@/domain/user/user.entity';

export class UserInMemoryRepository implements UserRepository {
  private readonly store = new Map<string, User>();

  async findById(id: string) {
    return this.store.get(id) ?? null;
  }

  async findByEmail(email: string) {
    for (const u of this.store.values()) if (u.email === email) return u;
    return null;
  }

  async save(user: User) {
    this.store.set(user.id, user);
  }

  async delete(id: string) {
    this.store.delete(id);
  }
}
```

The in-memory implementation:
- Uses the **real domain entity** — no separate "test entity" or anything contrived.
- Implements **every method** of the contract, fully. LSP requires substitutability.
- Is treated as a peer of the production implementation. The same suite of contract tests should pass against both.
- May be wired in `main.ts` (e.g., for a no-DB demo mode) and is the default for use case unit tests.

---

## 2. Queries (read side)

Queries fetch data shaped for the consumer (UI / API), not the domain. They return DTOs directly, not entities, because the consumer does not need entity behavior — it needs data, often joined or aggregated, often paginated.

### Contract

```ts
// domain/user/user.queries.ts
import type { PageInput, PageOutput } from '@/domain/_shared/pagination';

export type UserListItem = {
  id: string;
  email: string;
  isSuspended: boolean;
  videoCount: number;
  registeredAt: string;
};

export type UserDetail = {
  id: string;
  email: string;
  isSuspended: boolean;
  isAdmin: boolean;
  createdAt: string;
  totalVideoDuration: number;
  lastUploadAt: string | null;
};

export interface UserQueries {
  listAll(input: PageInput): Promise<PageOutput<UserListItem>>;
  searchByEmail(query: string, input: PageInput): Promise<PageOutput<UserListItem>>;
  detailById(id: string): Promise<UserDetail | null>;
}
```

Notes:
- Read DTOs (`UserListItem`, `UserDetail`) live in the same file as the interface, in `domain/<feature>/<feature>.queries.ts`. They are domain-defined contracts (the domain knows what shape the UI needs), but they are not entities.
- Method names describe the read intent: `listAll`, `searchByEmail`, `detailById`. Not `find*` (that suffix belongs to the repository's uniqueness checks).
- Pagination uses `PageInput` / `PageOutput<T>` — see `use-case-pattern.md` section 5.

### Implementation

```ts
// infra/queries/user/user.prisma-queries.ts
import type { PrismaClient } from '@prisma/client';
import type { UserQueries, UserListItem, UserDetail } from '@/domain/user/user.queries';
import type { PageInput, PageOutput } from '@/domain/_shared/pagination';

export class UserPrismaQueries implements UserQueries {
  constructor(private readonly prisma: PrismaClient) {}

  async listAll(input: PageInput): Promise<PageOutput<UserListItem>> {
    const skip = (input.page - 1) * input.pageSize;
    const [rows, total] = await Promise.all([
      this.prisma.user.findMany({
        skip,
        take: input.pageSize,
        orderBy: { createdAt: 'desc' },
        select: {
          id: true,
          email: true,
          isSuspended: true,
          createdAt: true,
          _count: { select: { videos: true } },
        },
      }),
      this.prisma.user.count(),
    ]);

    return {
      items: rows.map((r) => ({
        id: r.id,
        email: r.email,
        isSuspended: r.isSuspended,
        videoCount: r._count.videos,
        registeredAt: r.createdAt.toISOString(),
      })),
      page: input.page,
      pageSize: input.pageSize,
      total,
    };
  }

  // ... searchByEmail, detailById
}
```

Notes:
- `Queries` implementations may use **anything Prisma offers**: `select`, `include`, `_count`, raw SQL via `$queryRaw`, joins. They are not constrained to "load full aggregate".
- They never go through the domain entity — there is no mapper, no `restore`. The query returns the DTO directly.
- They do **not** need transaction awareness in most cases. Reads are one-shot. (Exception: when a use case does write-then-read in the same request and needs read-your-write consistency. Rare; handle case-by-case.)

### In-memory queries

```ts
// infra/queries/user/user.in-memory-queries.ts
import type { UserQueries, UserListItem, UserDetail } from '@/domain/user/user.queries';
import type { UserInMemoryRepository } from '@/infra/repository/user/user.in-memory-repository';

export class UserInMemoryQueries implements UserQueries {
  constructor(private readonly repo: UserInMemoryRepository) {}

  async listAll(input) {
    // implement against the same in-memory store
  }
  // ...
}
```

In-memory queries often share state with the in-memory repository (passing the same `Map` reference, or the repo itself). This keeps reads consistent with writes during tests and demos.

### When the same data is needed for both write and read

If `CreateUserUseCase` needs to check uniqueness (`findByEmail`) and `ListUsersUseCase` lists users by email match (`searchByEmail`), the data overlap is fine — they live on different contracts:
- `userRepo.findByEmail(email)` → `User | null` (entity).
- `userQueries.searchByEmail(query, page)` → `PageOutput<UserListItem>` (DTOs).

Different shapes, different contracts, no contradiction.

---

## 3. Gateway (external systems)

A gateway adapts an external system (a third-party API, an object storage, a mailer) into a domain-defined interface. Same pattern as repository: interface in `domain/`, implementation in `infra/gateway/`.

### Feature-specific gateway

```ts
// domain/transcription/transcription-engine.gateway.ts
export type TranscriptionSegment = {
  start: number;
  end: number;
  text: string;
};

export type TranscriptionResult = {
  language: string;
  segments: TranscriptionSegment[];
};

export interface TranscriptionEngine {
  transcribe(audio: Buffer, hints?: { language?: string }): Promise<TranscriptionResult>;
}
```

```ts
// infra/gateway/openai-transcription.gateway.ts
import OpenAI from 'openai';
import type { TranscriptionEngine, TranscriptionResult } from '@/domain/transcription/transcription-engine.gateway';

export class OpenAITranscriptionEngine implements TranscriptionEngine {
  constructor(private readonly client: OpenAI) {}

  async transcribe(audio: Buffer, hints?): Promise<TranscriptionResult> {
    const response = await this.client.audio.transcriptions.create({ /* ... */ });
    return {
      language: response.language ?? 'unknown',
      segments: response.segments?.map((s) => ({ start: s.start, end: s.end, text: s.text })) ?? [],
    };
  }
}
```

The use case depends on `TranscriptionEngine`. `main.ts` instantiates `OpenAITranscriptionEngine(new OpenAI({ apiKey: config.openaiApiKey }))` and injects it. Switching providers means writing a new implementation; the use case never changes.

### Cross-cutting gateway

Some adapters are not specific to a feature: a logger, a clock-like service, an outbound mailer, a file storage. Their interfaces live in `domain/_shared/` (only when whitelisted — see rule 5) or in a feature folder if conceptually owned by one feature.

For most projects, the whitelist is enough: `Logger` and `Mailer` rarely need to live in `_shared` — they can live in the closest feature folder, or be inferred locally. Resist creating new `_shared` artifacts.

### Gateway naming

| Artifact          | File                                                | Class / Interface                  |
|-------------------|-----------------------------------------------------|------------------------------------|
| Gateway interface | `domain/<feature>/<concept>.gateway.ts`             | `interface ConceptGateway`         |
| Gateway impl      | `infra/gateway/<provider>-<concept>.gateway.ts`     | `class ProviderConceptGateway`     |

Interfaces use `Gateway` suffix in the filename (`transcription-engine.gateway.ts`); the type name itself often does not need the suffix when the noun is unambiguous (`TranscriptionEngine`).

---

## 4. Provider qualifier in implementation names

When the implementation name embeds the provider, the codebase remains readable at a glance:

- `UserPrismaRepository` — Prisma is the persistence engine.
- `UserInMemoryRepository` — in-memory store (test/demo).
- `OpenAITranscriptionEngine` — OpenAI is the provider.
- `LocalDiskStorageGateway` — local filesystem.

This breaks if the project has a single ORM and you decide to drop the qualifier (`UserRepository` for the impl). Do not — it conflicts with the interface name. The qualifier is mandatory.

---

## 5. Composition (preview)

The full wiring lives in `composition-root.md`. Quick preview:

```ts
// main.ts
const prisma = new PrismaClient({ datasourceUrl: config.databaseUrl });

const userRepo = new UserPrismaRepository(prisma);
const userQueries = new UserPrismaQueries(prisma);

const transcriptionEngine = new OpenAITranscriptionEngine(new OpenAI({ apiKey: config.openaiApiKey }));

const createUser = new CreateUserUseCase(userRepo);
const listUsers = new ListUsersUseCase(userRepo, userQueries);
const transcribeVideo = new TranscribeVideoUseCase(videoRepo, transcriptionEngine);
```

The use case sees only the domain interfaces (`UserRepository`, `UserQueries`, `TranscriptionEngine`). It cannot import Prisma or OpenAI. The composition root is the bridge.

---

## 6. Common pitfalls

| Pitfall                                                       | Fix                                                          | See      |
|---------------------------------------------------------------|--------------------------------------------------------------|----------|
| Repository returning a row or a DTO                           | Map to entity in the implementation; return Entity           | A16      |
| Repository with `findActive`, `findByTag`, `findRecent`       | Move to `Queries`                                            | A17      |
| Use case using `Repository` for a list endpoint               | Use `Queries`                                                | A18      |
| Repository interface importing Prisma type                    | Domain interfaces speak only domain types                    | A19      |
| Mapper calling `User.create` (regenerates ID, re-hashes)      | Call `User.restore`                                          | A7       |
| `save` split into `create` and `update` methods               | Single `save` (upsert)                                       | rule 14  |
| `delete` throwing when id does not exist                      | Make it idempotent (swallow not-found)                       | rule 14  |
| In-memory repo implementing only some methods (`throw 'todo'`) | Implement all methods; LSP requires substitutability        | rule 13  |
| In-memory repo using a different entity shape                 | Use the real domain entity                                   | rule 13  |
| Queries returning entities                                    | Return DTOs (`UserListItem`, `UserDetail`)                   | rule 13  |
| Same `Queries` and `Repository` returning the same type       | They should not — Repository=Entity, Queries=DTO             | rule 13, 15 |
| Gateway implementation directly used by a use case            | Inject the interface, not the impl                           | rule 11  |

---

## Cross-references

- **`SKILL.md` rules**: 13 (CQRS-lite), 14 (Repository contract), 15 (Repository returns Entity).
- **`anti-patterns.md`**: A16 (returning DTO from repo), A17 (fat repository), A18 (Repo for read), A19 (ORM type leak), A7 (mapper calling `create`).
- **`domain-modeling.md`**: aggregates and aggregate roots; how `restore` rehydrates state.
- **`use-case-pattern.md`**: when a use case uses `Repository` vs `Queries`; pagination input/output.
- **`composition-root.md`**: how repositories, queries, gateways are wired in `main.ts`; transaction-context (AsyncLocalStorage) mechanism for `currentClient`.
- **`error-handling.md`**: `NotFoundError` vs returning `null`; rule of thumb is "repo returns null when missing, use case decides whether that is an error".
