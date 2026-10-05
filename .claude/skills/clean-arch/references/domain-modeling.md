# Domain modeling

Deep dive on `domain/` artifacts: entities, value objects, aggregates, IDs, and feature errors. Read alongside `SKILL.md` rules 5–9 and `anti-patterns.md` A5–A10, A14–A15.

The domain layer is the **business core**. It depends on nothing outside itself except validation/date/numeric libraries (zod, valibot, class-validator, date-fns, dayjs, decimal.js, big.js). It never depends on Prisma, axios, fs, http, or any I/O. The compiler does not enforce this directly — `dependency-cruiser` does (one rule per banned package: `no-prisma-outside-infra`, `no-axios-outside-infra`, etc.).

---

## 1. Entities

An entity has identity that persists across mutations. Two `User` instances with the same id represent the same user, even if other fields differ. Entities are **rich**: they carry the rules that govern their state.

### Required shape

Every entity in `domain/<feature>/<feature>.entity.ts` has:

1. **Private constructor** — only the class itself can instantiate.
2. **`static create(props)`** — applies creation rules (generates ID, sets defaults, hashes secrets, runs invariants). Used when the entity is born.
3. **`static restore(props)`** — rehydrates from a trusted source (the repository's mapper). Skips creation rules, accepts raw stored state.
4. **Mutation methods named for the domain action** — `suspend()`, `rename(title)`, `markAsReady()`. Never `set` keyword.
5. **Getters only** for reading state. No public mutable fields.
6. **`toJSON(): never`** — throws to fail-loud against accidental serialization.

### Full example

```ts
// domain/user/user.entity.ts
import { UserId } from './user-id.vo';
import { Email } from './email.vo';
import { HashedPassword } from './hashed-password.vo';
import { UserAlreadySuspendedError } from './errors';

export class User {
  private constructor(
    private readonly _id: UserId,
    private _email: Email,
    private _password: HashedPassword,
    private _isSuspended: boolean,
    private _isAdmin: boolean,
    private readonly _createdAt: Date,
  ) {}

  static create(props: { email: string; password: string; isAdmin?: boolean }): User {
    return new User(
      UserId.generate(),
      Email.create(props.email),
      HashedPassword.create(props.password),
      false,
      props.isAdmin ?? false,
      new Date(),
    );
  }

  static restore(props: {
    id: string;
    email: string;
    hashedPassword: string;
    isSuspended: boolean;
    isAdmin: boolean;
    createdAt: Date;
  }): User {
    return new User(
      UserId.from(props.id),
      Email.fromTrusted(props.email),
      HashedPassword.restore(props.hashedPassword),
      props.isSuspended,
      props.isAdmin,
      props.createdAt,
    );
  }

  suspend(): void {
    if (this._isSuspended) throw new UserAlreadySuspendedError(this._id.value);
    this._isSuspended = true;
  }

  reactivate(): void {
    this._isSuspended = false;
  }

  changeEmail(newEmail: string): void {
    this._email = Email.create(newEmail);
  }

  get id(): string { return this._id.value; }
  get email(): string { return this._email.value; }
  get hashedPassword(): string { return this._password.value; }
  get isSuspended(): boolean { return this._isSuspended; }
  get isAdmin(): boolean { return this._isAdmin; }
  get createdAt(): Date { return this._createdAt; }

  equals(other: User): boolean {
    return this._id.equals(other._id);
  }

  toJSON(): never {
    throw new Error('Do not serialize Entity directly. Use toOutput() in the use case DTO.');
  }
}
```

### `create` vs `restore` — why both

The two factories serve different intents:

| Factory     | When called                                | What it does                                          |
|-------------|--------------------------------------------|-------------------------------------------------------|
| `create`    | A new user signs up; new entity is born    | Generates new `UserId`, hashes plain password, sets defaults, validates `Email` format |
| `restore`   | The mapper reconstructs a user from a DB row | Trusts the stored ID, the stored hash, the stored email — no rule re-runs |

Why this split matters: if you call `create` from the mapper, you generate a **new** UUID every read, hash an already-hashed password, and re-validate stored data unnecessarily. The bug is silent and devastating. **The mapper always calls `restore`.**

### Mutations are domain methods, never setters

Wrong: `user.isSuspended = true` (setter or public field).
Right: `user.suspend()` — encapsulates "you may not suspend an already-suspended user".

When the rule grows — "admin cannot self-suspend", "cannot suspend a user who has open transactions" — it lives **inside the method**, not scattered across N use cases. The use case orchestrates load → method call → save. Nothing else.

### Equals

Entities are equal **by identity, not by value**. Two entity instances with the same id are the same entity, regardless of other field differences (one might be stale).

```ts
equals(other: User): boolean {
  return this._id.equals(other._id);
}
```

Use `equals(other)`, never `===` (different instances) and never `entity.id === other.id` (loses VO type safety).

### `toJSON` fails loud

`JSON.stringify(user)` returns `{}` by default (private fields are not enumerable). Silent failure produces empty API responses and wasted debugging hours. The fix is to make the failure obvious:

```ts
toJSON(): never {
  throw new Error('Do not serialize Entity directly. Use toOutput() in the use case DTO.');
}
```

The use case's `toOutput(entity): OutputDTO` is the only correct path from an entity to an external representation.

---

## 2. Value Objects

A value object is defined entirely by its value — there is no identity. Two `Email` instances with the same value are the same email. VOs are immutable: changing means creating a new instance.

### Required shape

Every VO in `domain/<feature>/<concept>.vo.ts` (or `domain/_shared/id.vo.ts` for shared ones) has:

1. **Private constructor** — bypassing validation is not allowed.
2. **`static create(raw)`** — validates input and instantiates.
3. **`value` getter** (or `value` readonly property) — exposes the underlying primitive.
4. **`equals(other)`** — value comparison.
5. Optionally, **`static fromTrusted(value)`** — for rehydration only, when the value comes from a trusted source (the repository).

### Example with library validation (preferred for non-trivial rules)

```ts
// domain/user/email.vo.ts
import { z } from 'zod';
import { InvalidEmailError } from './errors';

const schema = z.string().trim().toLowerCase().email();

export class Email {
  private constructor(public readonly value: string) {}

  static create(raw: string): Email {
    const parsed = schema.safeParse(raw);
    if (!parsed.success) throw new InvalidEmailError(raw);
    return new Email(parsed.data);
  }

  /** Skips validation. Only for rehydration from a trusted source (DB). */
  static fromTrusted(value: string): Email {
    return new Email(value);
  }

  equals(other: Email): boolean {
    return this.value === other.value;
  }
}
```

### Example with hand-rolled validation (fine for trivial rules)

```ts
// domain/video/video-status.vo.ts
import { InvalidVideoStatusError } from './errors';

const ALLOWED = ['validating', 'transcribing', 'summarizing', 'ready', 'failed'] as const;
type AllowedStatus = (typeof ALLOWED)[number];

export class VideoStatus {
  private constructor(public readonly value: AllowedStatus) {}

  static create(raw: string): VideoStatus {
    if (!ALLOWED.includes(raw as AllowedStatus)) throw new InvalidVideoStatusError(raw);
    return new VideoStatus(raw as AllowedStatus);
  }

  equals(other: VideoStatus): boolean {
    return this.value === other.value;
  }
}
```

Use whichever reads better. The point is not the validation tool — it is that the **rule is owned by the domain**, regardless of who validates.

### When does something become a VO?

A primitive becomes a VO when **either** is true:

- It has rules that the type system doesn't enforce (`Email` format, `Password` strength, `VideoDuration` ≤ 2h).
- It is meaningful by itself across multiple entities (`Money`, `DateRange`, `Coordinates`).

Don't VO-ify trivial primitives that are just stored values with no rules (e.g., `description: string`).

### Where to keep VOs

- **Feature-specific** (`Email`, `HashedPassword`, `VideoStatus`): `domain/<feature>/<concept>.vo.ts`. One file per VO.
- **Shared** (`Id`, `PageInput`/`PageOutput`): `domain/_shared/`. Closed whitelist.

If a VO conceptually belongs to a feature, **keep it there** even if another feature happens to use it. Cross-feature shared VOs are usually a smell — the two features may share a concept that should be its own bounded module.

---

## 3. IDs

IDs are a special VO. `domain/_shared/id.vo.ts` defines the base; each feature defines a typed subclass.

### Base `Id`

```ts
// domain/_shared/id.vo.ts
import { randomUUID } from 'node:crypto';

export class Id {
  protected constructor(public readonly value: string) {}

  static generate(): Id {
    return new Id(randomUUID());
  }

  static from(value: string): Id {
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value)) {
      throw new InvalidIdError(value);
    }
    return new Id(value);
  }
  // InvalidIdError is exported from domain/_shared/errors.ts.

  equals(other: Id): boolean {
    return this.value === other.value && this.constructor === other.constructor;
  }
}
```

Note: `node:crypto.randomUUID()` is a built-in. The domain may use Node built-ins (no install required, no I/O); it cannot use library wrappers like `uuid` purely for taste.

### Typed feature ID

```ts
// domain/user/user-id.vo.ts
import { Id } from '@/domain/_shared/id.vo';

export class UserId extends Id {
  static override generate(): UserId {
    return new UserId(super.generate().value);
  }
  static override from(value: string): UserId {
    return new UserId(super.from(value).value);
  }
}
```

Why subclass instead of `type UserId = string` (branded type)? The `equals` method checks `constructor === constructor` — it correctly returns `false` when comparing a `UserId` against a `VideoId` with the same string value. Branded types are erased at runtime; classes survive.

In the entity:

```ts
private readonly _id: UserId;
get id(): string { return this._id.value; }
```

The entity exposes the string via the getter for use cases / DTOs. Internally it works in `UserId` for safety.

---

## 4. Aggregates

An aggregate is a cluster of entities and VOs treated as **a single transactional consistency boundary**. It has one **aggregate root** — the entity that owns the cluster's identity and is the only entry point from outside.

### Rules

1. **One repository per aggregate root.** `UserRepository` loads/saves `User` (and any child entities/VOs inside it). Child entities have no repository of their own.
2. **References between aggregates use ID, not direct object reference.** `Video` does not hold a `User` instance; it holds a `userId: string`.
3. **Transactions cover one aggregate.** When you save a `User`, you save the whole `User` aggregate atomically. You do not save `User` and `Video` in the same transaction unless they are the same aggregate (they almost never are).

### Heuristic: is this one aggregate or two?

Ask: **is there an invariant that requires both to be consistent at the moment of any change?**

- Yes → same aggregate. Example: `Order` and its `OrderLine[]` — the total of lines must equal the order total at all times.
- No → two aggregates referenced by ID. Example: `User` and `Video` — a user can exist without videos, a video belongs to a user but the constraint is "video.userId points to an existing user", not a moment-to-moment invariant.

Vaughn Vernon's rule of thumb: **prefer small aggregates.** When in doubt, split. Merging two small aggregates into one is straightforward; splitting one large aggregate after the fact is painful (transactions, references, queries all change).

### Cross-aggregate consistency lives elsewhere

When two aggregates need to react to each other ("when a user is suspended, archive all their videos"), the path is:
1. Use case mutates aggregate A and saves it.
2. Use case publishes a domain event.
3. An event handler picks it up and mutates aggregate B in a separate transaction.

This is **eventual consistency by design**. See `domain-events.md`.

If you find yourself wanting to mutate two aggregates in one transaction, either: (a) you have one aggregate disguised as two — merge them; or (b) you should use eventual consistency — events.

---

## 5. Errors per feature

Every feature folder has an `errors.ts` containing all the domain errors raised by that feature.

```ts
// domain/user/errors.ts
import { DomainError, NotFoundError, ConflictError } from '@/domain/_shared/errors';

export class InvalidEmailError extends DomainError {
  readonly code = 'INVALID_EMAIL';
  readonly status = 422;
  constructor(value: string) { super(`Invalid email: "${value}"`); }
}

export class UserNotFoundError extends NotFoundError {
  readonly code = 'USER_NOT_FOUND';
  readonly status = 404;
  constructor(id: string) { super(`User not found: ${id}`); }
}

export class UserAlreadyExistsError extends ConflictError {
  readonly code = 'USER_ALREADY_EXISTS';
  readonly status = 409;
  constructor(email: string) { super(`User already exists: ${email}`); }
}

export class UserAlreadySuspendedError extends ConflictError {
  readonly code = 'USER_ALREADY_SUSPENDED';
  readonly status = 409;
  constructor(id: string) { super(`User already suspended: ${id}`); }
}
```

The base classes (`DomainError`, `NotFoundError`, `ConflictError`, `UnauthenticatedError`, `ForbiddenError`, `AppError`) live in `domain/_shared/errors.ts`. See `error-handling.md` for the full hierarchy and HTTP mapping.

**One `errors.ts` per feature.** Multiple classes in one file is correct — `max-classes-per-file` ESLint rule has an override for `**/errors.ts`.

---

## 6. What `domain/` may and may not import

### May import (always)

- `domain/_shared/*` — IDs, errors, pagination, unit-of-work.
- Other entities/VOs/interfaces in the same feature folder.
- Other feature's domain types **only by ID reference** (do not import another feature's entity for direct manipulation).

### May import (with care)

- Validation libraries: `zod`, `valibot`, `class-validator`.
- Date / time utilities: `date-fns`, `dayjs`.
- Numeric: `decimal.js`, `big.js`.
- Node built-ins for pure computation: `crypto.randomUUID()`, `crypto.createHash()`.

These bring no I/O. They are pure transforms — passing them in or out causes no side effect.

### Must NOT import (ever)

- ORMs / database clients: `@prisma/client`, `typeorm`, `mongoose`, `kysely`, `drizzle-orm`.
- HTTP / network: `axios`, `node-fetch`, `got`, native `node:http`, `node:https`.
- Filesystem: `node:fs`, `node:path` (when used for I/O — pure path manipulation is borderline).
- Process / OS: `node:child_process`, `node:os` (when querying state).
- Any custom code from `usecase/` or `infra/`.

`dependency-cruiser` enforces these prohibitions.

---

## 7. Common pitfalls

| Pitfall                                              | Fix                                          | See      |
|------------------------------------------------------|----------------------------------------------|----------|
| Calling `User.create` in the mapper                  | Use `User.restore`                           | A7       |
| Public field on entity (`email: string`)             | Private field + getter                       | A5       |
| Setter on entity (`set email(v)`)                    | Named method (`changeEmail(v)`)              | A6       |
| `new Email('foo')` from outside                      | Make constructor private; use `Email.create` | A8       |
| Anemic domain (logic in use case)                    | Move logic to entity method                  | A5, A14  |
| Importing Prisma type into domain interface          | Use domain types only                        | A19      |
| Holding `User` reference inside `Video` entity       | Hold `userId` (string) instead               | aggregate rule |
| Saving two aggregates in one transaction             | Either merge them, or use events             | aggregate rule |
| `entity.id === other.id` instead of `entity.equals`  | Use `equals` to leverage VO type safety      | entity equals |
| `JSON.stringify(entity)` returns `{}`                | `toJSON` throws; use `toOutput(entity)`      | A22      |

---

## Cross-references

- **`SKILL.md` rules**: 5 (`_shared` whitelist), 6 (rich entity), 7 (VO shape), 8 (IDs), 9 (allowed/forbidden imports).
- **`anti-patterns.md`**: A5 (anemic), A6 (setter), A7 (collapsed factories), A8 (VO without validation), A9 (I/O in domain), A10 (`_shared` junk drawer), A14 (invariant in use case), A15 (cross-feature business logic), A19 (ORM type leak).
- **`error-handling.md`**: full error hierarchy and HTTP mapping.
- **`repository-and-queries.md`**: how repositories use `restore` via mappers.
- **`domain-events.md`**: cross-aggregate consistency via events.
