# SOLID applied to this architecture

How each SOLID principle manifests concretely in the skill's structure. Each section maps the principle to the rules and anti-patterns it generates. Use this as the conceptual grounding behind the prescriptive rules in `SKILL.md`.

A useful frame: SOLID is not a checklist to apply manually — the structure already encodes it. When the rules feel arbitrary, the principle behind them explains why.

---

## SRP — Single Responsibility Principle

> A class should have one, and only one, reason to change.

### How the skill encodes SRP

- **One use case = one class with one public method `execute`.** A use case represents a single application action; its reason to change is "the way this action works changes". When a class has two `execute`-style methods, it has two reasons to change → split it.
- **One repository per aggregate root.** The repository's reason to change is "how this aggregate is persisted changes" (schema migration, ORM swap). It does not also handle queries (those have a different reason: "the read shape changes").
- **`Repository` and `Queries` are separate interfaces** — write side and read side change for different reasons (transactions and consistency for writes; aggregation and shape for reads).
- **Handlers do nothing but parse → call → return.** Their reason to change: "the HTTP shape of this endpoint changes". Business rules don't trigger a handler change because handlers don't carry them.
- **VOs encapsulate one concept.** `Email` is responsible for "what is a valid email"; nothing else.

### Tells

- A class with two public methods doing different jobs → split.
- A repository with both `save` (write) and `listActiveUsers` (read shape) → move the listing to `Queries`.
- A use case that authenticates AND creates a user (login auto-registration) → if the rule survives ("login auto-creates"), make it explicit in the name (`AuthenticateOrCreateUserUseCase`); otherwise split.
- A handler that loads an entity, mutates it, and saves it → push everything into a use case.

### Cross-refs

- `SKILL.md` rule 10 (single `execute`), 13 (Repository ≠ Queries), 14 (Repository contract), 16 (handler shape).
- `anti-patterns.md` A11 (multiple public methods), A17 (fat repository), A21 (business logic in handler).

---

## OCP — Open/Closed Principle

> Software entities should be open for extension, but closed for modification.

### How the skill encodes OCP

- **Use cases depend on interfaces from `domain/`, not implementations.** Adding a new persistence backend (Mongo, Redis, an HTTP-backed remote store) means writing a new `Repository` implementation in `infra/`; the use case is unchanged.
- **Adding a new external provider** (a different transcription engine, a different mailer, a different storage) means a new `Gateway` implementation in `infra/gateway/`. The interface in `domain/` is the stable extension point.
- **Adding a new HTTP framework** (Express → Fastify) means rewriting the adapter in `main.ts`. Handlers, use cases, repos are unchanged.
- **Adding a new feature** is purely additive: new feature folder in `domain/`, `usecase/`, `infra/repository/`, `infra/queries/`, `infra/http/`. Existing features are not modified.

### Tells of OCP violation

- A use case with `if (provider === 'openai') ... else if (provider === 'anthropic')` → missing gateway abstraction.
- Handler `switch (req.body.kind)` dispatching to different use cases inline → split into multiple handlers/routes.
- A repository with branching by feature flag inside its methods → likely two implementations sharing one class.
- Modifying an existing entity to add a "second variant" via boolean flags → the variants may be different aggregates.

### Cross-refs

- `SKILL.md` rules 11 (DI), 13 (Repository / Queries), 14 (Repository contract).
- `anti-patterns.md` A12 (`new` in use case), A19 (ORM type leak — locks the abstraction).

---

## LSP — Liskov Substitution Principle

> Subtypes must be substitutable for their base types.

### How the skill encodes LSP

- **In-memory fakes implement the same interface as production implementations.** Both `UserPrismaRepository` and `UserInMemoryRepository` satisfy `UserRepository` — fully, every method, with semantics matching the contract.
- **Concrete error subclasses** (`UserNotFoundError`, `InvalidEmailError`) all satisfy the `AppError` contract: they have `code`, `status`, `message`. Anywhere `AppError` is expected, any subclass works (this is what makes `instanceof AppError` in `toHttpResponse` reliable).
- **`User.create` and `User.restore` both return a fully functional `User`** — they cannot return a "half-built" instance. Calling `user.suspend()` works regardless of which factory created it.

### Tells of LSP violation

- Fake repository methods that `throw new Error('not implemented')` → fail substitution; real and fake disagree on behavior.
- A subclass strengthening preconditions (`childMethod` requires more than `parentMethod`) — calling code expecting the parent's contract breaks.
- A subclass weakening postconditions (returning `null` when the parent guarantees a value) — same violation, opposite direction.
- A `User` subclass `AdminUser` that overrides `suspend()` to silently no-op — caller expects a state change; it doesn't happen.

### Cross-refs

- `SKILL.md` rule 13 (CQRS-lite — both Repository and Queries have full implementations including in-memory).
- `repository-and-queries.md` section 1 (in-memory fakes implement everything).
- `error-handling.md` (the AppError hierarchy is LSP-clean by design).

---

## ISP — Interface Segregation Principle

> Clients should not be forced to depend on methods they do not use.

### How the skill encodes ISP

- **`Repository` (write) and `Queries` (read) are separate interfaces.** A read-only use case (`ListUsersUseCase`) depends on `UserQueries`. It does not see `save`, `delete`, `findByEmail`. The interface is exactly what the consumer needs.
- **`Gateway` interfaces are narrow per concept.** `TranscriptionEngine` has `transcribe`; it does not also have `summarize` (that would be `SummarizationGateway`). Two narrow interfaces > one fat interface, even if a single provider implements both.
- **Per-feature errors don't bleed into other features.** A use case that handles `User` errors imports from `domain/user/errors.ts`, not a giant central error bag.

### Tells of ISP violation

- A "fat repository" with `save`, `findById`, plus 12 listing methods (`findActive`, `findByTag`, etc.) → split into `Repository` + `Queries`.
- A `Service` interface with 20 methods, of which any consumer uses 2 → split by client purpose.
- A `Handler` interface forced to also handle WebSocket events and HTTP requests → split into `HttpHandler` and `WebSocketHandler`.

### Cross-refs

- `SKILL.md` rules 13 (CQRS-lite), 14 (Repository contract minimal).
- `anti-patterns.md` A17 (fat repository).

---

## DIP — Dependency Inversion Principle

> Depend on abstractions, not concretions.

### How the skill encodes DIP

- **Domain defines interfaces; infra implements them.** Use cases depend on `UserRepository`, not `UserPrismaRepository`. Infra reaches inward to satisfy the abstraction.
- **`main.ts` is the only place where concrete `infra/` classes are instantiated.** Everywhere else uses constructor parameters typed by the interface. Composition flows through the constructor — never through `new`, never through a service locator, never through ambient lookups.
- **The HTTP adapter is an abstraction (`Handler`, `HttpRequest`, `HttpResponse`)** — even the framework is "inverted". Express is a detail of `main.ts`; the rest of the codebase doesn't know it exists.

### Tells of DIP violation

- `import { PrismaClient } from '@prisma/client'` in a use case → inverted direction, use case depends on the concrete tool.
- `new UserPrismaRepository(...)` outside `main.ts` → service-locator-like; bypasses the inversion.
- A handler that imports an Express type (`Request`, `Response`) → leaks framework details upward.
- A static helper that "knows" how to read from the DB and is called from a use case → hidden coupling without a contract.

### Cross-refs

- `SKILL.md` rules 1 (dependency rule), 11 (DI by constructor), 13 (CQRS-lite contracts), 16 (handler interface).
- `anti-patterns.md` A1 (use case imports infra), A12 (`new` inside use case), A19 (ORM type leak), A27 (instantiation outside composition root).

---

## Beyond SOLID — the meta-rule of this skill

**DI by constructor, always.** No service locator, no singleton imports, no module-level state, no decorator-based DI containers. The composition root is the only place dependencies are wired, and it is wired by hand in `main.ts`.

This is more restrictive than SOLID strictly requires — SOLID admits service locator implementations of DIP. The skill rejects them because:

- **Constructor injection makes dependencies visible.** Reading a class's constructor tells you exactly what it needs. Service locator hides this in `locator.get(...)` calls scattered across methods.
- **Constructor injection is testable trivially.** Pass the fake; done. No test setup magic.
- **Constructor injection is statically verifiable.** TypeScript catches a missing dependency at compile time. Service locator catches it at runtime.
- **A small composition root is more readable than any DI container configuration.** When the dependency graph fits in 100 lines of straight code, you don't need a framework to manage it.

The rule appears in `SKILL.md` rule 11 ("Dependencies via constructor (DI), always") and is enforced by `check-architecture.ts` and ESLint together.

---

## How linters enforce SOLID

| Principle | Linter / tool                                          | Catches                                                       |
|-----------|--------------------------------------------------------|---------------------------------------------------------------|
| SRP       | `check-architecture.ts`                                | Use case classes with > 1 public method                       |
| SRP       | `dependency-cruiser`                                   | Repository file pattern containing query-style methods        |
| OCP       | manual review                                          | Branching on a `provider` string inside a use case           |
| LSP       | `check-architecture.ts`                                | In-memory repo missing methods of the interface               |
| ISP       | `check-architecture.ts`                                | Repository methods that look like read queries (`listX`, `searchX`) |
| DIP       | `dependency-cruiser`                                   | `domain/` or `usecase/` importing from `infra/`               |
| DIP       | ESLint `no-restricted-syntax` (NewExpression)          | `new SomeInfraClass()` outside `main.ts`                       |

---

## Cross-references

- **`SKILL.md` rules**: 10 (SRP — use case), 11 (DIP — DI by constructor), 13 (ISP — CQRS-lite), 14 (Repository contract), 15 (Repository returns Entity).
- **`anti-patterns.md`**: A1, A11, A12, A17, A19, A21, A27.
- **`domain-modeling.md`**: rich domain encodes SRP at the entity level.
- **`use-case-pattern.md`**: SRP applied to `execute`.
- **`repository-and-queries.md`**: ISP via the read/write split; LSP via fakes.
- **`composition-root.md`**: DIP made concrete in `main.ts`.
