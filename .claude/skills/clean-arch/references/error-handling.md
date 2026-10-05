# Error handling

Deep dive on the error class hierarchy, the per-feature `errors.ts`, the central HTTP mapper `toHttpResponse`, and the status-code rules. Read alongside `SKILL.md` rules 12 (use case validates inter-aggregate rules), 16 (no try/catch in handlers), 18 (authentication vs authorization errors), and `anti-patterns.md` A20.

Errors in this skill are **classes that carry their own status and code**. They are not strings, not `Error` with magic messages, not `Result<T, E>` types. The classes form a small hierarchy under `domain/_shared/errors.ts`; concrete errors per feature live in `domain/<feature>/errors.ts`.

---

## 1. The hierarchy

`domain/_shared/errors.ts` defines abstract base classes; concrete errors extend them.

```ts
// domain/_shared/errors.ts
export abstract class AppError extends Error {
  abstract readonly code: string;
  abstract readonly status: number;
  readonly details?: unknown;
  constructor(message: string, details?: unknown) {
    super(message);
    this.name = this.constructor.name;
    this.details = details;
  }
}

// Abstract categories — concrete errors per feature extend these.
export abstract class DomainError extends AppError {}        // 400 / 422 — invariant violation
export abstract class NotFoundError extends AppError {}      // 404 — resource does not exist
export abstract class ConflictError extends AppError {}      // 409 — state conflict

// Concrete generic errors — instantiated directly by use cases / middleware.
export class UnauthenticatedError extends AppError {
  readonly code = 'UNAUTHENTICATED';
  readonly status = 401;
  constructor(message = 'Authentication required') { super(message); }
}

export class ForbiddenError extends AppError {
  readonly code = 'FORBIDDEN';
  readonly status = 403;
  constructor(message = 'Forbidden') { super(message); }
}

// Shared concrete error.
export class InvalidIdError extends DomainError {
  readonly code = 'INVALID_ID';
  readonly status = 422;
  constructor(value: string) { super(`Invalid id: "${value}"`); }
}
```

`AppError` carries:
- `code: string` — a stable string contract for API consumers (`USER_NOT_FOUND`, `INVALID_EMAIL`). Stays even if the human message changes.
- `status: number` — the HTTP status to map to.
- `message: string` — human-readable explanation, may change freely.
- `details?: unknown` — optional structured payload (validation errors, conflict info).
- `name: string` — set to `this.constructor.name` so stack traces and `instanceof` checks read naturally.

The five abstract subclasses are **categories by semantics**, not by status. `DomainError` is "you violated a domain invariant" (regardless of whether that maps to 400 or 422). `NotFoundError` is "the resource does not exist" (always 404). Subclasses make `instanceof` checks expressive: `if (err instanceof NotFoundError) /* generic 404 handling */`.

---

## 2. Per-feature errors

Each feature has a single `errors.ts` file containing all the errors that feature can throw.

```ts
// domain/user/errors.ts
import { DomainError, NotFoundError, ConflictError } from '@/domain/_shared/errors';

export class InvalidEmailError extends DomainError {
  readonly code = 'INVALID_EMAIL';
  readonly status = 422;
  constructor(value: string) { super(`Invalid email: "${value}"`); }
}

export class WeakPasswordError extends DomainError {
  readonly code = 'WEAK_PASSWORD';
  readonly status = 422;
  constructor(reasons: string[]) { super(`Password too weak: ${reasons.join(', ')}`, { reasons }); }
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

Conventions:
- One `errors.ts` per feature, **multiple classes inside**. The ESLint `max-classes-per-file` rule has an override for `**/errors.ts`.
- Class name ends in `Error` (e.g., `UserNotFoundError`, never `UserNotFound`).
- `code` is `SCREAMING_SNAKE_CASE`, prefixed with the feature noun: `USER_NOT_FOUND`, `VIDEO_TOO_LONG`. Stable contract for clients.
- `status` set on the concrete class (not inherited from a status-named base).
- Constructor takes whatever input is needed to build the message and the optional `details` payload.

---

## 3. Where each error is thrown

| Layer        | Thrown by                                          | Examples                                    |
|--------------|----------------------------------------------------|---------------------------------------------|
| Domain       | Entity / VO factory or method                      | `InvalidEmailError` from `Email.create`; `UserAlreadySuspendedError` from `user.suspend()` |
| Use Case     | Inter-aggregate checks                             | `UserAlreadyExistsError` (uniqueness query); `UserNotFoundError` (load returned null); `ForbiddenError` (actor not owner) |
| Handler      | Schema parse                                       | `ZodError` (or whatever your schema lib throws) |

The use case **does not catch** domain errors — they propagate. The handler **does not catch** use case errors — they propagate. The catch happens once, at the framework adapter in `main.ts`, which delegates to `toHttpResponse(err)`.

---

## 4. `toHttpResponse` — central mapper

```ts
// infra/http/error-handler.ts
import { ZodError } from 'zod';
import { AppError } from '@/domain/_shared/errors';
import type { HttpResponse } from './types';

export const toHttpResponse = (err: unknown): HttpResponse => {
  if (err instanceof AppError) {
    return {
      status: err.status,
      body: { code: err.code, message: err.message, ...(err.details !== undefined && { details: err.details }) },
    };
  }

  if (err instanceof ZodError) {
    return {
      status: 400,
      body: { code: 'VALIDATION_ERROR', message: 'Invalid request', details: err.errors },
    };
  }

  // Unexpected. Log full detail server-side; do not leak stack to client.
  console.error('Unexpected error:', err);
  return {
    status: 500,
    body: { code: 'INTERNAL_ERROR', message: 'Unexpected error' },
  };
};
```

Behavior:
1. **Known `AppError`**: status and code come from the error itself. Optional `details` included. Done.
2. **`ZodError`** (or any schema lib error you use): map to `400 VALIDATION_ERROR` with the structured `details` payload.
3. **Anything else**: log server-side, return a generic `500` without leaking the stack or message. Never return raw error messages from unknown errors — they may contain internal paths, query fragments, or secret values.

For schema libraries other than zod, branch on the relevant error type. The principle is the same: shape errors → `400`, with structured details.

### Calling it

The framework adapter in `main.ts` wraps the handler call:

```ts
let httpRes;
try {
  httpRes = await route.handler.handle(httpReq);
} catch (err) {
  httpRes = toHttpResponse(err);
}
```

This is the **only** `try/catch` in the HTTP layer. Handlers do not have one (rule 16 + anti-pattern A20).

---

## 5. Status code mapping

| Status | Meaning                                          | Source                                            |
|--------|--------------------------------------------------|---------------------------------------------------|
| 400    | Malformed request shape                          | `ZodError` (handler schema)                       |
| 401    | Not authenticated                                | `UnauthenticatedError` (auth middleware)          |
| 403    | Authenticated but not authorized                 | `ForbiddenError` (use case authorization check)   |
| 404    | Resource does not exist                          | `NotFoundError` subclass (`UserNotFoundError`)    |
| 409    | State conflict (uniqueness, already-in-state)    | `ConflictError` subclass (`UserAlreadyExistsError`, `UserAlreadySuspendedError`) |
| 422    | Domain invariant violation                       | `DomainError` subclass (`InvalidEmailError`, `WeakPasswordError`) |
| 500    | Unexpected error                                 | Anything not caught by the rules above            |

Choosing between 400 and 422:
- **400** for "your request body is malformed" (missing fields, wrong types).
- **422** for "your request is well-formed JSON but the values violate a domain rule" (e.g., `email: "notanemail"` parses as a string but `Email.create` rejects it).

Some teams use 400 for both. Either is defensible; the skill's default is the split, but if your team prefers a single 400, change `DomainError` subclasses to `status = 400` consistently and document it.

Choosing between 404 and 403:
- **404** when the resource genuinely does not exist for anyone.
- **403** when the resource exists but this actor cannot access it.
- **404 for both** is also defensible (avoids leaking the existence of resources). The skill's default is to be transparent (403 when the actor exists but lacks permission), but admin-only areas often deliberately return 404 to non-admins (see videomax PRD `/admin/*`).

---

## 6. Throwing from the right place

Common decisions:

### "User not found" — repo returns null, use case throws

```ts
// repository
async findById(id) { return row ? UserMapper.toDomain(row) : null; }

// use case
const user = await this.userRepo.findById(input.userId);
if (!user) throw new UserNotFoundError(input.userId);
```

The repository signals absence with `null`. The use case decides whether absence is an error in this context. (For example, `findByEmail` in `CreateUserUseCase` returns `null` to signal "available" — that's not an error, the use case proceeds.)

### "Email already exists" — use case throws after query

```ts
const existing = await this.userRepo.findByEmail(input.email);
if (existing) throw new UserAlreadyExistsError(input.email);
```

Inter-aggregate rule that requires queried state; use case is the right place. See `use-case-pattern.md` section 3.

### "Email format invalid" — VO throws on construction

```ts
// inside Email.create
if (!schema.safeParse(raw).success) throw new InvalidEmailError(raw);
```

Single-value invariant; the VO owns it. The error propagates up through `User.create` → use case → handler → adapter → `toHttpResponse`. No layer catches it.

### "Cannot suspend admin" — entity method throws

```ts
suspendBy(actorId: string): void {
  if (this._isAdmin && this._id.value === actorId) throw new CannotSelfSuspendAdminError(actorId);
  if (this._isSuspended) throw new UserAlreadySuspendedError(this._id.value);
  this._isSuspended = true;
}
```

State-transition rule, internal to the aggregate; the entity method owns it.

---

## 7. Common pitfalls

| Pitfall                                                            | Fix                                                          | See        |
|--------------------------------------------------------------------|--------------------------------------------------------------|------------|
| Throwing `new Error('user not found')` instead of a typed class    | Define `UserNotFoundError extends NotFoundError`             | rule 12    |
| Catching errors in the handler and converting to status codes      | Let them propagate; `toHttpResponse` handles it              | A20        |
| `try/catch` in the use case to "wrap" errors                       | Let them propagate; the central mapper does the work         | A20        |
| Status code embedded in the error message instead of `status` prop | Add `readonly status: number` to the class                   | rule 12    |
| Returning the raw error message from a 500                         | Log server-side; return a generic message                    | rule 12    |
| Missing `code` (clients can't programmatically branch)             | Always set `code` on the concrete class                      | section 2  |
| `code` differs across calls of the same error (dynamic strings)    | Make `code` a constant class property                        | section 2  |
| Not catching `ZodError` separately                                 | Map it explicitly to 400 in `toHttpResponse`                  | section 4  |
| Multiple errors per feature spread across files                    | Consolidate into one `errors.ts` per feature                  | section 2  |

---

## Cross-references

- **`SKILL.md` rules**: 12 (use case throws inter-aggregate errors), 16 (no try/catch in handlers), 17 (entities throw via `toJSON` for serialization defense), 18 (`UnauthenticatedError` 401, `ForbiddenError` 403).
- **`anti-patterns.md`**: A20 (try/catch in handler).
- **`domain-modeling.md`**: where errors are thrown from VOs and entity methods.
- **`use-case-pattern.md`**: where errors are thrown from use cases (inter-aggregate rules).
- **`composition-root.md`**: the framework adapter wraps `handler.handle` in the single `try/catch` and routes through `toHttpResponse`.
- **`authorization.md`**: `UnauthenticatedError` vs `ForbiddenError`; which layer throws which.
