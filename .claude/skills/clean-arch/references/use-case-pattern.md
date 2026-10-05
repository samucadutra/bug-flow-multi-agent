# Use case pattern

Deep dive on `usecase/` artifacts: class shape, DTO conventions, validation flow, pagination contract, and authorization handoff. Read alongside `SKILL.md` rules 10–12 and `anti-patterns.md` A11–A15, A18.

A use case is a **single application action** — "create a user", "suspend a user", "list videos". It is not a service, not a feature, not a CRUD bundle. One class, one method, one job.

---

## 1. Class shape

Every use case in `usecase/<feature>/<action>-<feature>.usecase.ts` has:

1. **One class** named `<Action><Feature>UseCase` in PascalCase (e.g., `CreateUserUseCase`, `SuspendUserUseCase`).
2. **One public method `execute(input): Promise<output>`**. No other public methods.
3. **Dependencies via constructor (DI)**. The composition root wires implementations of `Repository`, `Queries`, `Gateway`, `UnitOfWork` (when needed) into the use case.
4. **No `new`** — use cases never instantiate concrete classes from `infra/`. They depend only on interfaces from `domain/`.
5. **No shape validation** (the handler does it via a schema library) and **no business invariants** (the entity does it).

### Full example

```ts
// usecase/user/create-user.usecase.ts
import { User } from '@/domain/user/user.entity';
import type { UserRepository } from '@/domain/user/user.repository';
import { UserAlreadyExistsError } from '@/domain/user/errors';
import { type CreateUserInput, type CreateUserOutput, toOutput } from './create-user.dto';

export class CreateUserUseCase {
  constructor(private readonly userRepo: UserRepository) {}

  async execute(input: CreateUserInput): Promise<CreateUserOutput> {
    const existing = await this.userRepo.findByEmail(input.email);
    if (existing) throw new UserAlreadyExistsError(input.email);

    const user = User.create({ email: input.email, password: input.password });
    await this.userRepo.save(user);

    return toOutput(user);
  }
}
```

What this use case does, in order:
1. **Inter-aggregate check**: is the email already taken? This requires a repository query, so the entity cannot do it. Use case does it.
2. **Create the entity**: `User.create` runs creation rules (new ID, hash password, validate email format).
3. **Persist**: `userRepo.save(user)` upserts the aggregate.
4. **Map to DTO**: `toOutput(user)` converts the entity to a serializable shape for the handler.

What this use case does **not** do:
- Validate `input.email` is a string (handler did it).
- Validate `input.email` matches an email regex (entity's `Email.create` does it inside `User.create`).
- Hash the password manually (entity's `HashedPassword.create` does it inside `User.create`).
- Serialize the result for HTTP (handler does it from the DTO).

---

## 2. DTOs

Each use case has a sibling `<action>-<feature>.dto.ts` that exports:

- `<Action><Feature>Input` — the typed input the use case accepts.
- `<Action><Feature>Output` — the typed output the use case returns.
- `toOutput(entity): <Action><Feature>Output` — the function that converts a domain entity to the output DTO.

### Example

```ts
// usecase/user/create-user.dto.ts
import type { User } from '@/domain/user/user.entity';

export type CreateUserInput = {
  email: string;
  password: string;
};

export type CreateUserOutput = {
  id: string;
  email: string;
  isAdmin: boolean;
  createdAt: string;
};

export const toOutput = (user: User): CreateUserOutput => ({
  id: user.id,
  email: user.email,
  isAdmin: user.isAdmin,
  createdAt: user.createdAt.toISOString(),
});
```

### DTOs are `type`, not `class` and not `interface`

- `type` — plain data, structural typing, no runtime cost, JSON-compatible.
- `class` — implies behavior or identity. DTOs have neither.
- `interface` — works structurally but `type` is more flexible (unions, intersections, mapped types, branded types).

### Input and Output in the same file

The use case's contract is one piece. Splitting it across two files adds navigation cost without benefit.

### `toOutput` is the only path from entity to DTO

A handler that returns the entity directly violates rule 17 (entity has `toJSON` that throws) and is detected by `check-architecture.ts`. The single correct path:

```
Repository.findById → Entity → useCase.execute → toOutput(entity) → OutputDTO → handler.body
```

When the use case returns multiple entities or a paginated list, `toOutput` is mapped:

```ts
return { items: users.map(toOutput) };
```

But for read-side endpoints, prefer `Queries` directly — see `repository-and-queries.md`.

---

## 3. Validation flow

The skill's validation responsibility is split across three layers. The use case sits in the middle.

```
[Handler]                    [Use Case]                       [Entity / VO]
zod schema parse              inter-aggregate rules            invariants
  ↓                             ↓                                ↓
shape error → 400             ConflictError → 409              DomainError → 422
                              ForbiddenError → 403
                              NotFoundError → 404
```

### What the use case validates

Only **inter-aggregate rules that require queried state**. Examples:

- "Is this email already taken?" → query the repository, throw `UserAlreadyExistsError` if found.
- "Is the actor the owner of this resource?" → load the resource, compare its owner field (e.g., `video.userId`) against `input.actorId`, throw `ForbiddenError` if not.
- "Does this user still have unprocessed videos?" → query, throw if true.
- "Is the actor an admin?" → load actor user, check `actor.isAdmin`, throw `ForbiddenError` if not.

### What the use case does NOT validate

- **Input shape**: that's the handler's schema. `if (!input.email)` is a smell. Anti-pattern A13.
- **Single-aggregate invariants**: those live on the entity. `if (input.email.includes('@'))` is a smell — `Email.create` does it. Anti-pattern A14.
- **Internal state transitions**: `if (user.isSuspended) throw ...` should be `user.suspend()` (the method enforces it). Anti-pattern A5/A15.

### Order inside `execute`

A consistent order makes use cases easy to scan:

```ts
async execute(input) {
  // 1. Authorization (if applicable) — load actor, check role/ownership
  // 2. Load existing aggregates (uniqueness checks, references)
  // 3. Mutate or create domain entities
  // 4. Persist (one or more saves; wrap in UoW if multiple)
  // 5. Map to OutputDTO
  // 6. Return
}
```

Not every use case needs every step. But when a step is present, this is its position.

---

## 4. Authorization handoff

The handler authenticates (`req.user`) and passes `actorId` into the use case input for authenticated operations. Anonymous endpoints do not pass `actorId`.

### Authenticated example

```ts
// usecase/video/delete-video.dto.ts
export type DeleteVideoInput = {
  actorId: string;
  videoId: string;
};

// usecase/video/delete-video.usecase.ts
import { ForbiddenError } from '@/domain/_shared/errors';
import { VideoNotFoundError } from '@/domain/video/errors';

export class DeleteVideoUseCase {
  constructor(private readonly videoRepo: VideoRepository) {}

  async execute(input: DeleteVideoInput): Promise<void> {
    const video = await this.videoRepo.findById(input.videoId);
    if (!video) throw new VideoNotFoundError(input.videoId);
    if (video.userId !== input.actorId) throw new ForbiddenError('not the owner');

    await this.videoRepo.delete(video.id);
  }
}
```

The use case never asks "is this user authenticated?" (the handler/middleware already did). It asks "given an authenticated actor, may this actor do this thing?" That is **authorization**, and it depends on domain state. See `authorization.md` for more scenarios.

### Anonymous example

```ts
// usecase/user/create-user.dto.ts (no actorId — registration is anonymous)
export type CreateUserInput = {
  email: string;
  password: string;
};
```

When in doubt: if the operation requires "the user must be logged in", pass `actorId`. If it does not (login itself, registration, public listing), do not.

---

## 5. Pagination

List endpoints share a single contract. `domain/_shared/pagination.ts`:

```ts
// domain/_shared/pagination.ts
export type PageInput = {
  page: number;       // 1-based
  pageSize: number;   // bounded; the impl caps at a max
};

export type PageOutput<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
};
```

### Use case using pagination

```ts
// usecase/user/list-users.dto.ts
import type { PageInput, PageOutput } from '@/domain/_shared/pagination';
import type { UserListItem } from '@/domain/user/user.queries';

export type ListUsersInput = PageInput & { actorId: string };
export type ListUsersOutput = PageOutput<UserListItem>;
```

```ts
// usecase/user/list-users.usecase.ts
import { ForbiddenError } from '@/domain/_shared/errors';
import type { UserRepository } from '@/domain/user/user.repository';
import type { UserQueries } from '@/domain/user/user.queries';
import type { ListUsersInput, ListUsersOutput } from './list-users.dto';

export class ListUsersUseCase {
  constructor(
    private readonly userRepo: UserRepository,
    private readonly userQueries: UserQueries,
  ) {}

  async execute(input: ListUsersInput): Promise<ListUsersOutput> {
    const actor = await this.userRepo.findById(input.actorId);
    if (!actor || !actor.isAdmin) throw new ForbiddenError('admin required');

    return this.userQueries.listAll({ page: input.page, pageSize: input.pageSize });
  }
}
```

Note:
- The use case uses both `UserRepository` (to load the actor for authorization — needs the entity to call `actor.isAdmin`) and `UserQueries` (to list — read side).
- `UserListItem` is a query DTO defined in `domain/user/user.queries.ts`, not an entity. The use case returns it directly without further mapping.
- `ListXUseCase` and `SearchXUseCase` always have `PageInput` in the input shape. `check-architecture.ts` enforces this.

### Cursor-based pagination

Page-based is the default. If you need cursor pagination later (large lists, infinite scroll), introduce a parallel `CursorPageInput` / `CursorPageOutput<T>` in `_shared/pagination.ts`. Do not retrofit the existing types — keep them stable.

---

## 6. Multiple writes — Unit of Work (opt-in)

When a use case writes to two aggregates that must be atomic, use `UnitOfWork`:

```ts
// usecase/user/register-user.usecase.ts
import type { UnitOfWork } from '@/domain/_shared/unit-of-work';
// ...

export class RegisterUserUseCase {
  constructor(
    private readonly uow: UnitOfWork,
    private readonly userRepo: UserRepository,
    private readonly profileRepo: ProfileRepository,
  ) {}

  async execute(input) {
    return this.uow.run(async () => {
      const user = User.create({ email: input.email, password: input.password });
      const profile = Profile.createDefault(user.id);
      await this.userRepo.save(user);
      await this.profileRepo.save(profile);
      return toOutput(user);
    });
  }
}
```

Single-write use cases do **not** need `UnitOfWork`. The opt-in keeps the dependency surface small for the common case. See `composition-root.md` for the implementation mechanism.

If you find yourself wanting to write to two aggregates atomically, consider whether they should be one aggregate. See `domain-modeling.md` (aggregates section) and `domain-events.md` for the eventual-consistency alternative.

---

## 7. Tests

Co-located: `usecase/<feature>/<action>-<feature>.usecase.spec.ts`. Use cases test naturally with **fakes** (in-memory implementations of the interfaces), never with mocks of the production class.

```ts
// usecase/user/create-user.usecase.spec.ts
import { CreateUserUseCase } from './create-user.usecase';
import { UserInMemoryRepository } from '@/infra/repository/user/user.in-memory-repository';
import { UserAlreadyExistsError } from '@/domain/user/errors';

describe('CreateUserUseCase', () => {
  it('persists a new user', async () => {
    const repo = new UserInMemoryRepository();
    const useCase = new CreateUserUseCase(repo);

    const out = await useCase.execute({ email: 'a@b.co', password: 'TestPass123' });

    expect(out.email).toBe('a@b.co');
    expect(await repo.findById(out.id)).not.toBeNull();
  });

  it('throws UserAlreadyExistsError when email is taken', async () => {
    const repo = new UserInMemoryRepository();
    const useCase = new CreateUserUseCase(repo);
    await useCase.execute({ email: 'a@b.co', password: 'TestPass123' });

    await expect(
      useCase.execute({ email: 'a@b.co', password: 'OtherPass456' }),
    ).rejects.toBeInstanceOf(UserAlreadyExistsError);
  });
});
```

The fake (`UserInMemoryRepository`) implements the same `UserRepository` interface as the Prisma version. LSP holds: swapping fakes for the real implementation should not change use case behavior. See `repository-and-queries.md` for the fake's full shape.

The *what* and *how* of testing belongs to a separate testing skill. This skill only fixes the structural conventions: co-location and `.spec.ts` suffix.

---

## 8. Common pitfalls

| Pitfall                                                   | Fix                                                  | See      |
|-----------------------------------------------------------|------------------------------------------------------|----------|
| Use case with two public methods                          | Split into two use cases                             | A11      |
| `new SomeRepository()` inside the use case                | Inject via constructor                               | A12      |
| `if (!input.email) throw ...` at the top of `execute`     | Move to handler's schema                             | A13      |
| `if (!regex.test(input.email))` at the top of `execute`   | Move to entity (`Email.create`)                      | A14      |
| Manual `is-admin` / `is-suspended` checks across use cases | Move to entity method                                | A5, A15  |
| Use case using `UserRepository` for a list endpoint       | Use `UserQueries`                                    | A18      |
| Returning the entity from the use case                    | Map via `toOutput(entity)`                           | A22      |
| `actorId` missing on an authenticated operation           | Add `actorId: string` to the `Input` type            | rule 18  |
| `actorId` present on registration / login                 | Remove it — these endpoints are anonymous            | rule 18  |
| `ListXUseCase` without `PageInput` in input               | Spread `PageInput` into the input type               | rule 13  |
| Two repository writes without `UnitOfWork`                | Inject `UnitOfWork` and wrap in `uow.run`            | section 6, `composition-root.md` |

---

## Cross-references

- **`SKILL.md` rules**: 10 (single `execute`), 11 (DI by constructor), 12 (no shape validation, no invariants, only inter-aggregate rules), 13 (CQRS-lite Repository vs Queries), 17 (`toOutput` is the only path), 18 (authorization with `actorId`).
- **`anti-patterns.md`**: A11 (multiple public methods), A12 (`new` inside use case), A13 (shape validation), A14 (invariants), A15 (cross-feature logic), A18 (Repository for read), A22 (returning entity).
- **`domain-modeling.md`**: entity factories, VOs, aggregates, IDs.
- **`repository-and-queries.md`**: write-side vs read-side, mappers, fakes.
- **`error-handling.md`**: `ConflictError`, `ForbiddenError`, `NotFoundError`, status code mapping.
- **`composition-root.md`**: how the use case's dependencies are wired in `main.ts`; `UnitOfWork` mechanism.
- **`authorization.md`**: more on `actorId` patterns and common scenarios.
