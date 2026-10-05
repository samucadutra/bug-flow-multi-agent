# Authorization

Deep dive on the authentication / authorization split, the `actorId` pattern, and common scenarios. Read alongside `SKILL.md` rule 18 and `anti-patterns.md` A23.

The skill draws a sharp line between **authentication** ("who is this caller?") and **authorization** ("may this caller do this thing?"). Authentication is HTTP-layer plumbing; authorization is a domain rule. They live in different places.

---

## 1. The split

| Concern         | Question                                              | Layer                                          | Failure                       |
|-----------------|-------------------------------------------------------|------------------------------------------------|-------------------------------|
| Authentication  | Is there a valid session/JWT? Who is the caller?     | Middleware in `infra/http/middleware/auth.ts`  | `UnauthenticatedError` → 401  |
| Authorization   | May this caller perform this action on this resource? | Use case (`actorId` in input)                  | `ForbiddenError` → 403        |

Authentication has no domain knowledge — it just verifies the token and identifies the caller. Authorization needs domain knowledge — "may THIS user delete THIS video" depends on the video's owner field, the user's admin flag, and possibly the video's current state.

---

## 2. Authentication — the middleware

`infra/http/middleware/auth.ts` runs on every request before handlers. It reads the credentials (cookie session, Bearer token, etc.), looks up the user, and either populates `req.user` or rejects with 401.

```ts
// infra/http/middleware/auth.ts
import { UnauthenticatedError } from '@/domain/_shared/errors';

export const authMiddleware = async (req, res, next) => {
  const sessionId = req.cookies?.session;
  if (!sessionId) {
    if (isPublicRoute(req.path)) return next();
    throw new UnauthenticatedError();
  }

  const session = await sessionStore.get(sessionId);
  if (!session) throw new UnauthenticatedError('Session expired');

  req.user = { id: session.userId, isAdmin: session.isAdmin };
  next();
};
```

Conventions:

- **Public routes** (registration, login, landing) skip the middleware via a `isPublicRoute` allowlist.
- **`req.user`** holds only what the rest of the system needs to know about the caller: `id`, plus possibly cached flags like `isAdmin`. Loading the full `User` aggregate from `req.user` happens later, in the use case.
- The middleware throws `UnauthenticatedError`. The framework adapter in `main.ts` catches it (single `try/catch`) and passes it to `toHttpResponse`, which maps to 401.

The middleware does **not**:
- Look up roles to decide if the caller may access a specific endpoint.
- Read URL params and check ownership.
- Make any decision that depends on the resource being acted upon.

Those are authorization concerns. They live in the use case.

### Why the middleware doesn't authorize

Three reasons:

1. **Authorization rules depend on domain state**: "only the owner can delete this video" needs to load the video and compare `video.userId` against `req.user.id`. The middleware runs before route resolution; it does not know which video is being acted upon.
2. **Middleware-based authorization scatters rules**: each route has its own decorator/guard, the rule lives away from the use case it guards, and changes ripple across the HTTP layer.
3. **Other entry points (workers, CLIs) skip middleware**: a background job processing the same use case would need a duplicated authorization guard. Putting the rule in the use case unifies entry points.

See `anti-patterns.md` A23 for the explicit anti-pattern.

---

## 3. Authorization — `actorId` in the use case input

For every authenticated operation, the handler passes `actorId` (and optionally `actorIsAdmin`) into the use case input.

### DTO shape

```ts
// usecase/video/delete-video.dto.ts
export type DeleteVideoInput = {
  actorId: string;       // populated by the handler from req.user.id
  videoId: string;
};
```

`actorId` is always a `string` — the caller's `User.id`. It is not the full entity. The use case loads the actor only when it needs the entity (e.g., to read `actor.isAdmin`).

### Handler

```ts
// infra/http/video/delete-video.handler.ts
import { z } from 'zod';
import { UnauthenticatedError } from '@/domain/_shared/errors';

const schema = z.object({ videoId: z.string().uuid() });

export class DeleteVideoHandler implements Handler {
  constructor(private readonly deleteVideo: DeleteVideoUseCase) {}

  async handle(req: HttpRequest): Promise<HttpResponse> {
    if (!req.user) throw new UnauthenticatedError();
    const { videoId } = schema.parse({ videoId: req.params.videoId });
    await this.deleteVideo.execute({ actorId: req.user.id, videoId });
    return { status: 204 };
  }
}
```

The `if (!req.user) throw new UnauthenticatedError()` guard exists because TypeScript types `req.user` as optional — public routes skip the middleware. For protected routes, the middleware would have thrown earlier, so this check is defensive against routing mistakes.

### Use case

```ts
// usecase/video/delete-video.usecase.ts
import { ForbiddenError } from '@/domain/_shared/errors';
import { VideoNotFoundError } from '@/domain/video/errors';

export class DeleteVideoUseCase {
  constructor(
    private readonly videoRepo: VideoRepository,
    private readonly userRepo: UserRepository,
  ) {}

  async execute(input: DeleteVideoInput): Promise<void> {
    const video = await this.videoRepo.findById(input.videoId);
    if (!video) throw new VideoNotFoundError(input.videoId);

    const actor = await this.userRepo.findById(input.actorId);
    if (!actor) throw new ForbiddenError('actor not found');

    if (video.userId !== actor.id && !actor.isAdmin) {
      throw new ForbiddenError('only the owner or an admin can delete this video');
    }

    await this.videoRepo.delete(video.id);
  }
}
```

The authorization decision lives **inside `execute`**, after loading the resource and the actor, before mutating.

---

## 4. Common scenarios

### A. Owner-only operation

The most common case: only the resource's owner may perform the action.

```ts
async execute(input) {
  const video = await this.videoRepo.findById(input.videoId);
  if (!video) throw new VideoNotFoundError(input.videoId);
  if (video.userId !== input.actorId) throw new ForbiddenError('not the owner');
  // ... mutate
}
```

Loads the actor only as `actorId` (string). No need to fetch the full `User` aggregate when comparing IDs.

### B. Admin override

Owner OR admin may perform the action:

```ts
const actor = await this.userRepo.findById(input.actorId);
if (!actor) throw new ForbiddenError('actor not found');
if (video.userId !== actor.id && !actor.isAdmin) {
  throw new ForbiddenError('only the owner or an admin can delete this video');
}
```

Loads the actor entity to read `actor.isAdmin`. The middleware-cached flag (`req.user.isAdmin`) is a convenience for fast-path 401 decisions; for authorization, load the entity to get a fresh state (the user might have been demoted between session creation and now).

### C. Role-based (admin only)

```ts
const actor = await this.userRepo.findById(input.actorId);
if (!actor || !actor.isAdmin) throw new ForbiddenError('admin required');
```

`SuspendUserUseCase`, `DeleteUserUseCase`, anything in the `/admin/*` area uses this pattern.

### D. State-dependent rules

Some authorization depends on the resource state, not just the actor:

```ts
const video = await this.videoRepo.findById(input.videoId);
if (!video) throw new VideoNotFoundError(input.videoId);
if (video.status !== 'ready') {
  throw new ForbiddenError('cannot edit a video that is still processing');
}
if (video.userId !== input.actorId) throw new ForbiddenError('not the owner');
// ...
```

These checks belong on the entity when they are **invariants** (`video.rename(name)` should refuse if `!ready`). They belong in the use case when they are **inter-aggregate or actor-relative** ("not the owner", "is the actor an admin").

### E. Self-action restriction

"Admin cannot self-suspend":

```ts
async execute(input) {
  const target = await this.userRepo.findById(input.userId);
  if (!target) throw new UserNotFoundError(input.userId);
  if (target.id === input.actorId) throw new ForbiddenError('cannot suspend yourself');
  const actor = await this.userRepo.findById(input.actorId);
  if (!actor || !actor.isAdmin) throw new ForbiddenError('admin required');
  target.suspend();
  await this.userRepo.save(target);
}
```

Or push it into the entity method (preferred when the rule is intrinsic to the suspension):

```ts
target.suspendBy(input.actorId);   // method enforces self-suspension and already-suspended
```

The choice — method on entity vs check in use case — depends on whether the rule survives across all callers. "An admin cannot self-suspend" is a domain rule that survives, so it lives on the entity.

---

## 5. 404 vs 403 — when to hide existence

Sometimes returning 403 leaks information ("yes, this resource exists, but you can't access it"). For sensitive resources, return 404 instead, masking the existence.

### Default (transparent)

```ts
const video = await this.videoRepo.findById(input.videoId);
if (!video) throw new VideoNotFoundError(input.videoId);          // 404
if (video.userId !== input.actorId) throw new ForbiddenError(...); // 403
```

The caller can distinguish "doesn't exist" from "exists but forbidden". Reasonable for most APIs.

### Hiding existence (recommended for `/admin/*`)

```ts
const video = await this.videoRepo.findById(input.videoId);
if (!video || video.userId !== input.actorId) throw new VideoNotFoundError(input.videoId); // always 404
```

Or, for admin areas where non-admin presence should be invisible:

```ts
// videomax /admin/* — non-admin gets 404 not 403
const actor = await this.userRepo.findById(input.actorId);
if (!actor || !actor.isAdmin) throw new VideoNotFoundError(input.videoId);  // 404
```

The choice is a **policy decision per feature**, not a global rule. Default to transparent; switch to 404-masking for sensitive admin areas (videomax PRD F12 explicitly requires this).

---

## 6. Anonymous endpoints

Registration, login, public listings: the use case input does **not** include `actorId`. There is no actor.

```ts
// usecase/user/create-user.dto.ts
export type CreateUserInput = {
  email: string;
  password: string;
};

// usecase/user/authenticate-user.dto.ts
export type AuthenticateUserInput = {
  email: string;
  password: string;
};
```

The handler does not call `if (!req.user) throw ...` because these routes are in the public allowlist (the middleware skipped them).

`check-architecture.ts` allows use cases without `actorId` — it does not enforce its presence. The decision is per use case.

---

## 7. Common pitfalls

| Pitfall                                                        | Fix                                                          | See        |
|----------------------------------------------------------------|--------------------------------------------------------------|------------|
| Authorization decision in middleware                           | Move to the use case; pass `actorId` in input                | A23, rule 18 |
| `if (!req.user.isAdmin) return 403` in handler                 | Move check to use case                                       | A21        |
| Use case using `req.user` directly (handler import)            | Pass `actorId` (string) into input; never import HTTP types  | rule 1     |
| Trusting `req.user.isAdmin` for authorization                  | Re-fetch actor via repo; session state may be stale          | section 4B |
| Same authorization rule duplicated across N use cases          | Push the rule into the entity method                         | section 4D, A14 |
| Returning 403 from a sensitive admin endpoint                  | Return 404 to mask resource existence                        | section 5  |
| `actorId` missing on an authenticated operation                | Add `actorId: string` to the `Input` type                    | rule 18    |
| `actorId` present on registration / login                      | Remove — these are anonymous                                 | rule 18    |
| Catching `UnauthenticatedError` in the handler                 | Let it propagate; the framework adapter maps to 401          | A20        |

---

## Cross-references

- **`SKILL.md` rules**: 16 (handler shape), 18 (auth in middleware, authz in use case).
- **`anti-patterns.md`**: A20 (try/catch in handler), A21 (business logic in handler), A23 (authz in middleware).
- **`use-case-pattern.md`**: `actorId` in input, the validation order in `execute`.
- **`error-handling.md`**: `UnauthenticatedError` (concrete), `ForbiddenError` (concrete), HTTP status mapping.
- **`composition-root.md`**: where `authMiddleware` is mounted in `main.ts`.
- **`domain-modeling.md`**: when an authorization rule belongs as an entity method vs a use case check.
