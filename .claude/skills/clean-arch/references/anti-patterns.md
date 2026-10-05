# Anti-patterns

This file is the operational checklist of violations the agent must actively avoid. Load it before any non-trivial structural change. Each entry follows the same shape: **what it looks like, why it's wrong, the rule it violates, the fix.**

---

## Layer violations

### A1. UseCase imports from `infra/`

❌ Wrong:
```ts
// usecase/user/create-user.usecase.ts
import { PrismaClient } from '@prisma/client';
import { UserPrismaRepository } from '@/infra/repository/user/user.prisma-repository';
```

✅ Right: import only the **interface** from `domain/`. The composition root injects the implementation.
```ts
import type { UserRepository } from '@/domain/user/user.repository';
```

**Violates rule 1.** Detection: `dependency-cruiser` catches this with `usecase-no-infra` rule.

---

### A2. Domain imports from `usecase/` or `infra/`

❌ Wrong:
```ts
// domain/user/user.entity.ts
import type { CreateUserInput } from '@/usecase/user/create-user.dto';
```

✅ Right: domain defines its own types. DTOs in `usecase/` are derived from the entity, not the other way around.

**Violates rule 1.** Detection: `dependency-cruiser` catches this with `domain-no-deps`.

---

### A3. `process.env` outside `src/config/env.ts`

❌ Wrong:
```ts
// infra/gateway/openai-transcription.gateway.ts
const apiKey = process.env['OPENAI_API_KEY'];
```

✅ Right: read all env vars in one place; pass them via composition root.
```ts
// src/config/env.ts
export const config = z.object({ openaiApiKey: z.string().min(1) }).parse({
  openaiApiKey: process.env['OPENAI_API_KEY'],
});

// main.ts
const transcriptionGateway = new OpenAITranscriptionGateway(config.openaiApiKey);
```

**Violates rule 2.** Detection: ESLint `no-restricted-properties` (target `process.env`) or `no-restricted-syntax` (selector `MemberExpression[object.name="process"][property.name="env"]`), restricted to files outside `src/config/`.

---

### A4. Barrel file (`index.ts` re-exporting)

❌ Wrong:
```ts
// domain/user/index.ts
export * from './user.entity';
export * from './email.vo';
export * from './user.repository';

// usage:
import { User, Email, UserRepository } from '@/domain/user';
```

✅ Right: import directly from each file.
```ts
import { User } from '@/domain/user/user.entity';
import { Email } from '@/domain/user/email.vo';
import type { UserRepository } from '@/domain/user/user.repository';
```

**Violates rule 4.** Barrel files break tree-shaking, encourage circular deps, and slow `go-to-definition`. The single allowed `index.ts` is `infra/http/index.ts` (the routes builder). `main.ts` is unaffected — it is a single file, not a barrel.

---

## Domain anti-patterns

### A5. Anemic entity (data class with public fields, logic in use case)

❌ Wrong:
```ts
export class User {
  id: string;
  email: string;
  isSuspended: boolean;
}

// use case:
if (user.isSuspended) throw new Error('already suspended');
user.isSuspended = true;
await userRepo.save(user);
```

✅ Right: rule lives on the entity.
```ts
class User {
  suspend(): void {
    if (this._isSuspended) throw new UserAlreadySuspendedError(this._id.value);
    this._isSuspended = true;
  }
}

// use case:
user.suspend();
await userRepo.save(user);
```

**Violates rule 6.** When the same `if` appears in multiple use cases, the rule belongs in the entity.

---

### A6. Public setter on entity (`set foo(v)`)

❌ Wrong:
```ts
class User {
  set isSuspended(v: boolean) { this._isSuspended = v; }
}
user.isSuspended = true;
```

✅ Right: mutations via domain-named methods.
```ts
class User { suspend(): void { /* ... */ } }
user.suspend();
```

**Violates rule 6.** Detection: ESLint `no-restricted-syntax` with selector `MethodDefinition[kind="set"]`, restricted to `domain/`. Also caught by `check-architecture.ts`.

---

### A7. `User.create(...)` and `User.restore(...)` collapsed into one factory

❌ Wrong:
```ts
class User {
  static create(props): User {
    // Generates new UUID even when restoring from DB → duplicates pile up
    return new User(props.id ?? UserId.generate(), ...);
  }
}
```

✅ Right: distinct factories for distinct intents.
```ts
class User {
  static create(props): User { return new User(UserId.generate(), ...); }
  static restore(props): User { return new User(UserId.from(props.id), ...); }
}
```

**Violates rule 6.** `create` applies creation rules (new ID, hashing, defaults). `restore` rehydrates trusted state without re-running rules.

---

### A8. VO without validation in `create()`

❌ Wrong:
```ts
class Email {
  constructor(public value: string) {} // public, no validation
}
```

✅ Right: private constructor + validating factory.
```ts
class Email {
  private constructor(public readonly value: string) {}
  static create(raw: string): Email {
    const parsed = schema.safeParse(raw);
    if (!parsed.success) throw new InvalidEmailError(raw);
    return new Email(parsed.data);
  }
}
```

**Violates rule 7.** Without `private constructor`, anyone can bypass validation by `new Email('not-an-email')`.

---

### A9. Domain importing I/O libraries

❌ Wrong:
```ts
// domain/user/user.entity.ts
import axios from 'axios';
import { PrismaClient } from '@prisma/client';
import fs from 'node:fs';
```

✅ Right: I/O lives in `infra/`. Domain may import validation/utility libs (zod, valibot, date-fns, decimal.js) but never network/disk/process.

**Violates rule 9.** Detection: `dependency-cruiser` rule `no-prisma-outside-infra` (extend the same pattern for `axios`, `fs`, `node:fs`, `node:http`, etc.).

---

### A10. `domain/_shared/` becoming a junk drawer

❌ Wrong:
```
domain/_shared/
  string-utils.ts          # not domain
  date-helpers.ts          # not domain
  user-event.ts            # belongs to user/
  video-thumbnail.helper.ts # belongs to video/
```

✅ Right: `_shared/` is a closed whitelist — `id.vo.ts`, `errors.ts`, `unit-of-work.ts`, `pagination.ts`. Anything else belongs to a feature folder or to `infra/` (utility code that's not domain).

**Violates rule 5.** Detection: `check-architecture.ts` enforces the whitelist.

---

## Use case anti-patterns

### A11. Use case with more than one public method

❌ Wrong:
```ts
class UserUseCase {
  async create(input) { /* ... */ }
  async authenticate(input) { /* ... */ }
  async suspend(input) { /* ... */ }
}
```

✅ Right: one class per use case.
```ts
class CreateUserUseCase { async execute(input) {} }
class AuthenticateUserUseCase { async execute(input) {} }
class SuspendUserUseCase { async execute(input) {} }
```

**Violates rule 10.** Detection: `check-architecture.ts` flags any class in `usecase/` with more than one public method that isn't the constructor.

---

### A12. `new` of a concrete dependency inside use case

❌ Wrong:
```ts
class CreateUserUseCase {
  async execute(input) {
    const repo = new UserPrismaRepository(new PrismaClient());
    /* ... */
  }
}
```

✅ Right: receive via constructor.
```ts
class CreateUserUseCase {
  constructor(private readonly userRepo: UserRepository) {}
  async execute(input) { /* uses this.userRepo */ }
}
```

**Violates rule 11.** Detection: ESLint `no-restricted-syntax` for `NewExpression` of imported infra classes outside `main.ts`.

---

### A13. Use case validating input shape

❌ Wrong:
```ts
async execute(input) {
  if (!input.email) throw new Error('email required');
  if (typeof input.email !== 'string') throw new Error('email must be string');
}
```

✅ Right: handler does shape validation with zod. Use case receives a typed, validated input.
```ts
// handler:
const input = schema.parse(req.body);
await this.createUser.execute(input);
```

**Violates rule 12.** If the handler is doing its job, the use case never sees malformed input.

---

### A14. Use case containing business invariants

❌ Wrong:
```ts
async execute(input) {
  if (!input.email.includes('@')) throw new InvalidEmailError(input.email);
  const user = User.create(input);
}
```

✅ Right: the entity (or its VOs) owns the invariant.
```ts
async execute(input) {
  const user = User.create(input); // Email.create() inside throws if invalid
}
```

**Violates rule 12.** When the same invariant check would appear in 3 use cases, you've located the rule wrong.

---

### A15. Cross-feature business logic split across use cases instead of an aggregate method

❌ Wrong (suspension logic spread across handler + use case):
```ts
async execute(input) {
  const user = await this.userRepo.findById(input.userId);
  if (user.isAdmin && user.id === input.actorId) throw new Error('cannot self-suspend');
  if (user.isSuspended) throw new Error('already suspended');
  (user as any)._isSuspended = true; // bypassing TS visibility — the entity is no longer guarding itself
}
```

✅ Right: the entity owns the rule.
```ts
async execute(input) {
  const target = await this.userRepo.findById(input.userId);
  target.suspendBy(input.actorId); // method enforces self-suspension + already-suspended
  await this.userRepo.save(target);
}
```

**Violates rule 12.** The entity can express the full invariant; the use case orchestrates load → method → save.

---

## Repository / Queries anti-patterns

### A16. Repository returning a DTO or raw row

❌ Wrong:
```ts
class UserPrismaRepository implements UserRepository {
  async findById(id): Promise<{ id: string; email: string }> { /* row */ }
}
```

✅ Right: repository always returns Entity (or `null`).
```ts
async findById(id): Promise<User | null> {
  const row = await this.prisma.user.findUnique({ where: { id } });
  return row ? UserMapper.toDomain(row) : null;
}
```

**Violates rule 15.** If you want a DTO, you want `Queries`, not `Repository`.

---

### A17. Repository with too many `findByX` methods

❌ Wrong:
```ts
interface UserRepository {
  findById(id): Promise<User | null>;
  findByName(name): Promise<User[]>;
  findActiveUsers(): Promise<User[]>;
  findUsersWithMoreThanNVideos(n): Promise<User[]>;
  // ... 12 more findX methods
}
```

✅ Right: those are read queries, not writes. Move to `UserQueries`.
```ts
interface UserRepository {
  findById(id): Promise<User | null>;
  findByEmail(email): Promise<User | null>; // for uniqueness check on write
  save(user: User): Promise<void>;
  delete(id: string): Promise<void>;
}

interface UserQueries {
  listActive(input: PageInput): Promise<PageOutput<UserListItem>>;
  searchByName(query: string, input: PageInput): Promise<PageOutput<UserListItem>>;
  // ...
}
```

**Violates rules 13, 14.** A "fat repository" mixes write and read responsibilities (ISP violation).

---

### A18. Use case using `Repository` for read-only listing

❌ Wrong:
```ts
class ListUsersUseCase {
  constructor(private readonly userRepo: UserRepository) {}
  async execute(input) {
    const users = await this.userRepo.findAll(input.page);
    return { items: users.map(toListItem) };
  }
}
```

✅ Right: read endpoints use `Queries`.
```ts
class ListUsersUseCase {
  constructor(private readonly userQueries: UserQueries) {}
  async execute(input) {
    return this.userQueries.listAll(input);
  }
}
```

**Violates rule 13.** Hydrating 100 entities just to list them is overhead with zero benefit — you don't need entity behavior, you need data.

---

### A19. ORM type leaking through Repository contract

❌ Wrong:
```ts
// domain/user/user.repository.ts
import type { Prisma } from '@prisma/client';
interface UserRepository {
  findMany(where: Prisma.UserWhereInput): Promise<User[]>;
}
```

✅ Right: domain interfaces speak only domain types.
```ts
interface UserRepository {
  findById(id: string): Promise<User | null>;
}
```

**Violates rules 1, 9.** If the contract carries Prisma types, you can't swap Prisma without rewriting the contract — the abstraction is a fake.

---

## HTTP / Handler anti-patterns

### A20. `try/catch` in handler

❌ Wrong:
```ts
async handle(req) {
  try {
    const out = await this.useCase.execute(input);
    return { status: 200, body: out };
  } catch (e) {
    if (e instanceof UserNotFoundError) return { status: 404, body: { error: e.message } };
    if (e instanceof DomainError) return { status: 422, body: { error: e.message } };
    return { status: 500, body: { error: 'internal' } };
  }
}
```

✅ Right: let exceptions propagate; the central error handler maps them.
```ts
async handle(req) {
  const input = schema.parse(req.body);
  const out = await this.useCase.execute(input);
  return { status: 200, body: out };
}

// infra/http/error-handler.ts maps every AppError subclass to its status/code.
```

**Violates rule 16.** Detection: ESLint `no-restricted-syntax` for `TryStatement` inside `infra/http/**/*.handler.ts`.

---

### A21. Business logic in handler

❌ Wrong:
```ts
async handle(req) {
  const user = await this.userRepo.findById(req.params.id);
  if (user.isSuspended) return { status: 403, body: { error: 'suspended' } };
  if (user.id !== req.user.id) return { status: 403, body: { error: 'not owner' } };
  await this.userRepo.delete(user.id);
}
```

✅ Right: handler is dumb wiring — parse, call, return.
```ts
async handle(req) {
  await this.deleteUser.execute({ actorId: req.user.id, userId: req.params.id });
  return { status: 204 };
}
// All checks live inside DeleteUserUseCase.
```

**Violates rule 16.** Handler that does anything between `parse` and `return` is doing too much.

---

### A22. Returning entity directly from handler

❌ Wrong:
```ts
async handle(req) {
  const user = await this.userRepo.findById(req.params.id);
  return { status: 200, body: user }; // JSON.stringify(user) → "{}" or throws
}
```

✅ Right: convert via `toOutput`.
```ts
async handle(req) {
  const out = await this.getUser.execute({ id: req.params.id });
  return { status: 200, body: out };
}
```

**Violates rule 17.** Entity has private fields and a `toJSON()` that throws — the failure is intentional and loud.

---

### A23. Authorization in middleware (not in use case)

❌ Wrong:
```ts
// infra/http/middleware/admin-only.ts
export const adminOnly = (req, res, next) => {
  if (!req.user.isAdmin) return res.status(403).end();
  next();
};
```

✅ Right: middleware does **authentication** only. Authorization that depends on domain state goes in the use case.
```ts
// usecase/user/suspend-user.usecase.ts
async execute(input) {
  const actor = await this.userRepo.findById(input.actorId);
  if (!actor.isAdmin) throw new ForbiddenError('admin required');
  // ...
}
```

**Violates rule 18.** Middleware doesn't know enough about the operation to make authorization decisions consistently. Centralizing in the use case keeps the rule near the data it queries.

---

## Naming / structure anti-patterns

### A24. Wrong file suffix or no suffix

❌ Wrong:
```
usecase/user/createUser.ts
usecase/user/CreateUser.ts
usecase/user/create-user-use-case.ts
```

✅ Right: kebab-case + `.usecase.ts` suffix.
```
usecase/user/create-user.usecase.ts
```

**Violates the naming table in `SKILL.md`.** Detection: `check-architecture.ts` enforces the suffix per location.

---

### A25. Use case named after data, not action

❌ Wrong:
```
usecase/user/user.usecase.ts            # what does it do?
usecase/user/users.usecase.ts
usecase/video/video-service.usecase.ts
```

✅ Right: `<verb>-<feature>.usecase.ts`.
```
usecase/user/create-user.usecase.ts
usecase/user/suspend-user.usecase.ts
usecase/video/upload-video.usecase.ts
```

A use case is an **action**. If you can't name the verb, you don't have a use case yet — you have a service grab-bag.

---

### A26. Interface prefixed with `I`

❌ Wrong:
```ts
interface IUserRepository { /* ... */ }
class UserRepositoryImpl implements IUserRepository { /* ... */ }
```

✅ Right:
```ts
interface UserRepository { /* ... */ }
class UserPrismaRepository implements UserRepository { /* ... */ }
```

**Violates the naming convention.** The interface owns the canonical name. The implementation differentiates with a provider qualifier (`Prisma`, `InMemory`, `Mongo`).

---

## Composition / process anti-patterns

### A27. `new` of an `infra/` concrete class outside `main.ts`

❌ Wrong:
```ts
// infra/http/user/create-user.handler.ts
export class CreateUserHandler {
  private repo = new UserPrismaRepository(new PrismaClient()); // ← instantiation outside the composition root
  /* ... */
}
```

✅ Right: composition root wires everything; handler receives use case via constructor.

**Violates rule 11.** Detection: ESLint `no-restricted-syntax` for `NewExpression` of imported `infra/repository/**`, `infra/queries/**`, `infra/gateway/**` outside `main.ts`.

---

### A28. Using `--no-verify` to skip a failing gate

❌ Wrong: `git commit --no-verify -m "fix"` because `tsc` is failing.

✅ Right: fix the TypeScript error. If you genuinely believe the gate is wrong, stop and ask the user.

**Violates rule 19.** Bypassing a gate destroys the entire enforcement contract — the whole point of the 6-gate self-audit is that violations cannot be merged. One bypass becomes a habit.

---

### A29. Skipping the self-audit before declaring done

❌ Wrong: writing code, declaring "task complete", letting the user discover that `tsc` doesn't compile.

✅ Right: run all 6 gates **before** declaring done.

```bash
npx tsc --noEmit -p tsconfig.json
npx eslint . --max-warnings=0
npx depcruise src --config .dependency-cruiser.cjs
npx tsx scripts/check-architecture.ts
npx madge --circular --extensions ts src
npx knip
```

**Violates rule 19.** If a gate fails, the task is **not** done.

---

## Quick detection cheatsheet

| Smell                                                     | Fix                                          | Rule |
|-----------------------------------------------------------|----------------------------------------------|------|
| `import` from `@/infra` inside `domain/` or `usecase/`    | Use the interface from `domain/`             | 1    |
| `process.env` outside `src/config/env.ts`                 | Move to `env.ts`, inject via composition     | 2    |
| `index.ts` re-exporting many things                       | Delete the barrel; import from each file     | 4    |
| `set` keyword inside `domain/`                            | Replace with named method                    | 6    |
| `User.create(...)` called from a mapper                   | Use `User.restore(...)` for rehydration      | 6    |
| Two factories merged into one                             | Split `create` and `restore`                 | 6    |
| `public` constructor on a VO                              | Make it `private`, expose `static create()`  | 7    |
| Two public methods on a use case class                    | Split into two classes                       | 10   |
| `new SomeRepository(...)` outside `main.ts`               | Inject via constructor                       | 11   |
| `if (!input.x)` at the top of `execute()`                 | Move to handler's zod schema                 | 12   |
| `if (regex.test(input.x))` at the top of `execute()`      | Move to entity / VO factory                  | 12   |
| `findX` listing methods on the Repository interface       | Move to `Queries`                            | 13   |
| Repository method returning a row or DTO                  | Map to Entity inside the implementation      | 15   |
| `try/catch` in a handler                                  | Delete it; let `toHttpResponse` map errors   | 16   |
| `res.json(entity)` or `body: entity`                      | Convert via `toOutput(entity)`               | 17   |
| Authorization decision inside middleware                  | Move to the use case (`actorId` in input)    | 18   |
| `git commit --no-verify`                                  | Fix the failing gate; never bypass           | 19   |
