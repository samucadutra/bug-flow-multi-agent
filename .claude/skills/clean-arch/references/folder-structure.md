# Folder structure

Deep dive on the canonical tree, how to add a new feature, where multi-feature flows live, and the `domain/_shared/` whitelist. Read alongside `SKILL.md` rules 1–5.

The structure is **prescriptive** — three layers (`domain/`, `usecase/`, `infra/`) plus `config/` and `main.ts`. Inside `domain/`, `usecase/`, `infra/repository/`, `infra/queries/`, and `infra/http/`, feature folders are **mirrored** by name. Everything else follows from those rules.

---

## 1. Canonical tree (annotated)

```
src/
  config/
    env.ts                                # ONLY place that reads process.env
                                          # exports a typed `config` object
  domain/                                 # business core — no I/O imports
    _shared/                              # whitelist (see section 4)
      id.vo.ts
      errors.ts                           # AppError + abstract categories + ForbiddenError + UnauthenticatedError + InvalidIdError
      unit-of-work.ts                     # opt-in interface
      pagination.ts                       # PageInput, PageOutput<T>
    user/                                 # feature folder
      user.entity.ts
      user-id.vo.ts                       # extends Id
      email.vo.ts
      hashed-password.vo.ts
      user.repository.ts                  # interface (write side)
      user.queries.ts                     # interface (read side) + DTO types
      errors.ts                           # all User errors in one file
    video/
      video.entity.ts
      video-id.vo.ts
      video-status.vo.ts
      video.repository.ts
      video.queries.ts
      errors.ts
    transcription/                        # feature with no aggregate (pure gateway)
      transcription-engine.gateway.ts     # interface for external API
  usecase/                                # orchestration — depends only on domain/
    user/
      create-user.usecase.ts
      create-user.dto.ts
      authenticate-user.usecase.ts
      authenticate-user.dto.ts
      list-users.usecase.ts               # uses UserQueries (read side)
      list-users.dto.ts
      suspend-user.usecase.ts
      suspend-user.dto.ts
    video/
      upload-video.usecase.ts
      upload-video.dto.ts
      ...
  infra/                                  # external world — implements domain interfaces
    http/
      handler.ts                          # interface Handler
      types.ts                            # HttpRequest, HttpResponse, HttpRoute
      error-handler.ts                    # toHttpResponse(err)
      middleware/
        auth.ts                           # populates req.user from session/JWT
      user/
        create-user.handler.ts
        authenticate-user.handler.ts
        list-users.handler.ts
        suspend-user.handler.ts
        user.routes.ts                    # exports HttpRoute[] for the feature
      video/
        ...
      index.ts                            # buildHttpRoutes(deps) — single allowed barrel
    repository/                           # write-side implementations
      user/
        user.prisma-repository.ts
        user.in-memory-repository.ts      # fake (LSP-substitutable)
        user.mapper.ts                    # Entity ↔ persistence row
      video/
        ...
    queries/                              # read-side implementations
      user/
        user.prisma-queries.ts
        user.in-memory-queries.ts
      video/
        ...
    gateway/                              # external API adapters
      openai-transcription.gateway.ts     # implements TranscriptionEngine
      local-disk-storage.gateway.ts
    persistence/                          # cross-cutting persistence infra
      transaction-context.ts              # AsyncLocalStorage for opt-in UoW
      prisma-unit-of-work.ts              # implements UnitOfWork
  main.ts                                 # composition root — only place that uses `new`
```

Tests are co-located with their `*.spec.ts` siblings inside the same folders. They are not shown above to keep the structure readable.

---

## 2. Adding a new feature — step by step

The mirrored layout means adding a feature follows a fixed checklist. Walk through it for `Folder` (the `Folder` aggregate from videomax F05):

1. **Decide the aggregate root.** `Folder` is its own aggregate (or a child of `User`?). For F05 a folder belongs to a user but exists independently — `Folder` is a separate aggregate referencing `userId`.

2. **Create `domain/folder/`**:
   ```
   domain/folder/
     folder.entity.ts                     # static create/restore, methods like rename(name)
     folder-id.vo.ts                      # extends Id
     folder-name.vo.ts                    # validation: 1–80 chars, unique-per-user is use-case-level
     folder.repository.ts                 # interface: findById, findByUserAndName, save, delete
     folder.queries.ts                    # interface: listByUser(userId, page), DTO types
     errors.ts                            # FolderNotFoundError, DuplicateFolderNameError
   ```

3. **Create `usecase/folder/`** with the actions you actually need:
   ```
   usecase/folder/
     create-folder.usecase.ts + .dto.ts
     rename-folder.usecase.ts + .dto.ts
     delete-folder.usecase.ts + .dto.ts
     list-folders.usecase.ts + .dto.ts
   ```
   Each use case is a separate file. Do not bundle them.

4. **Create `infra/repository/folder/`**:
   ```
   infra/repository/folder/
     folder.prisma-repository.ts          # implements FolderRepository
     folder.in-memory-repository.ts       # fake
     folder.mapper.ts                     # toDomain via Folder.restore, toPersistence
   ```

5. **Create `infra/queries/folder/`**:
   ```
   infra/queries/folder/
     folder.prisma-queries.ts             # implements FolderQueries
     folder.in-memory-queries.ts          # fake
   ```

6. **Create `infra/http/folder/`**:
   ```
   infra/http/folder/
     create-folder.handler.ts
     rename-folder.handler.ts
     delete-folder.handler.ts
     list-folders.handler.ts
     folder.routes.ts                     # exports folderRoutes(deps): HttpRoute[]
   ```

7. **Wire in `infra/http/index.ts`**:
   ```ts
   import { folderRoutes, type FolderRoutesDeps } from './folder/folder.routes';

   export type HttpDeps = UserRoutesDeps & VideoRoutesDeps & FolderRoutesDeps;

   export const buildHttpRoutes = (deps: HttpDeps): HttpRoute[] => [
     ...userRoutes(deps),
     ...videoRoutes(deps),
     ...folderRoutes(deps),
   ];
   ```

8. **Wire in `main.ts`**: instantiate the new repo, queries, use cases, handlers — in that topological order. Pass them all into `buildHttpRoutes`.

9. **Run the self-audit** (rule 19): every gate should pass. New mirrored folders + `check-architecture.ts` will catch any forgotten file (e.g., a use case without a DTO, an entity without a `errors.ts`).

The skill's `templates/initial-project/` includes empty `domain/`, `usecase/`, and `infra/` folders ready for this checklist.

---

## 3. Cross-feature use cases

Most use cases live in a single feature folder named after the **primary aggregate** they create or mutate. But some flows touch multiple aggregates (`RegisterUser` creates User + Profile; `OnboardCompany` creates Company + Owner User + initial Tenant config).

### Default rule

A cross-feature use case lives in **the feature folder of its primary aggregate**. The primary aggregate is the one named in the use case's verb-noun: `register-user.usecase.ts` lives in `usecase/user/`, even if it also touches `Profile` and emits an `OrgInvitation`.

Heuristic: if you renamed the use case to drop the secondary effects, what would remain? `RegisterUser` survives without `CreateProfile` (registration without auto-profile is meaningful). Therefore `User` is primary; the use case lives in `usecase/user/`.

### Composite-flow folder (rare exception)

When there is genuinely no primary aggregate — multiple aggregates of equal weight participate in a coordinated flow — create a named composite folder:

```
usecase/user-onboarding/
  start-onboarding.usecase.ts
  start-onboarding.dto.ts
  complete-onboarding.usecase.ts
  complete-onboarding.dto.ts
```

The folder name describes the flow (`user-onboarding`, `checkout`, `subscription-renewal`), not the aggregates. Use this only when "primary aggregate" genuinely cannot be chosen.

### Forbidden

Do **not** create:
- `usecase/_shared/` — there is no shared use case folder.
- `usecase/cross/`, `usecase/multi/`, `usecase/common/` — same problem.
- A use case "library" of helpers shared across features (helpers are domain methods or repository methods).

If you find yourself wanting a shared use case folder, you have either a primary aggregate hiding (find it) or duplicated logic that belongs on an entity / repository.

---

## 4. The `domain/_shared/` whitelist

`_shared/` is a **closed whitelist**. Adding a file to it requires it to fit one of the four allowed slots; otherwise the file belongs to a feature folder.

| File                  | Purpose                                                                       |
|-----------------------|-------------------------------------------------------------------------------|
| `id.vo.ts`            | Base `Id` VO + `Id.generate()` (UUID) + `Id.from(string)`. Feature IDs extend. |
| `errors.ts`           | `AppError`, abstract categories (`DomainError`, `NotFoundError`, `ConflictError`), generic concrete (`UnauthenticatedError`, `ForbiddenError`), `InvalidIdError`. |
| `unit-of-work.ts`     | `UnitOfWork` interface for opt-in atomic multi-aggregate writes.              |
| `pagination.ts`       | `PageInput`, `PageOutput<T>`.                                                  |

Anything else triggers `check-architecture.ts` to fail. Common temptations and where they actually belong:

| Tempting filename                | Where it actually goes                                                  |
|----------------------------------|--------------------------------------------------------------------------|
| `clock.vo.ts` / `clock.ts`       | If genuinely needed: `domain/_shared/`. But default to `new Date()`. Add only when you have a deterministic-time test or rule. (Not in the whitelist by default.) |
| `string-utils.ts`, `array-utils.ts` | Not domain. If pure utility, live with the consumer or in `infra/`.   |
| `user-event.ts`                  | `domain/user/` — events belong to the feature that emits them.          |
| `currency.vo.ts`                 | If used by multiple features, create `domain/currency/` (feature-shaped) or pick the dominant feature. |
| `logger.ts`                      | Not domain. Interface lives near the consumer or in `infra/gateway/`.   |
| `event.ts`                       | If domain events are in use, see `domain-events.md` — `DomainEvent` abstract class + `EventBus` interface live in `domain/_shared/event.ts` only when adopted skill-wide. |

If the project genuinely needs to extend the whitelist (e.g., adopting domain events across the codebase), document the addition in this skill's `references/` and update the rule, the linter, and `check-architecture.ts` together. **Never silently add a file to `_shared/`.**

---

## 5. Tests are co-located

Tests sit next to the file they test, named `<file>.spec.ts`:

```
domain/user/
  user.entity.ts
  user.entity.spec.ts            # tests for User entity
  email.vo.ts
  email.vo.spec.ts
usecase/user/
  create-user.usecase.ts
  create-user.usecase.spec.ts
infra/repository/user/
  user.prisma-repository.ts
  user.prisma-repository.spec.ts
```

`check-architecture.ts` does not require every file to have a `.spec.ts` (some files like `errors.ts` do not need behavior tests). What it does require: a `.spec.ts` file must sit **next to** the file it tests; orphan tests in a separate folder are flagged.

Test infrastructure (helpers, builders, fixtures) lives in `tests/` at the project root, **outside `src/`**:

```
tests/
  _shared/
    builders/
      user.builder.ts
      video.builder.ts
    db.ts
```

Tests inside `src/` may import from `tests/_shared/` (one-way). Production code never imports from `tests/`. `dependency-cruiser` enforces this with a rule blocking `tests/` imports inside `src/**` excluding `**/*.spec.ts`.

The *what* and *how* of testing belongs to a separate testing skill. This skill only fixes the structural conventions — co-location, `.spec.ts` suffix, and the `tests/` directory for shared test infrastructure.

---

## 6. Naming reference

| Artifact            | File pattern                                | Class / Type                                |
|---------------------|---------------------------------------------|---------------------------------------------|
| Entity              | `<feature>.entity.ts`                       | `class Feature`                             |
| Value Object        | `<concept>.vo.ts`                           | `class Concept`                             |
| Use Case            | `<action>-<feature>.usecase.ts`             | `class ActionFeatureUseCase`                |
| DTO                 | `<action>-<feature>.dto.ts`                 | `type ActionFeatureInput`, `type ActionFeatureOutput` |
| Repository iface    | `<feature>.repository.ts`                   | `interface FeatureRepository`               |
| Repository impl     | `<feature>.<provider>-repository.ts`        | `class Feature<Provider>Repository`         |
| Queries iface       | `<feature>.queries.ts`                      | `interface FeatureQueries` + DTO types      |
| Queries impl        | `<feature>.<provider>-queries.ts`           | `class Feature<Provider>Queries`            |
| Mapper              | `<feature>.mapper.ts`                       | `class FeatureMapper` (static methods)      |
| Handler             | `<action>-<feature>.handler.ts`             | `class ActionFeatureHandler`                |
| Routes              | `<feature>.routes.ts`                       | `function <feature>Routes(deps): HttpRoute[]` |
| Gateway iface       | `<concept>.gateway.ts` in `domain/`         | `interface ConceptGateway`                  |
| Gateway impl        | `<provider>-<concept>.gateway.ts` in `infra/gateway/` | `class ProviderConceptGateway`    |
| Errors              | `errors.ts` (one per feature)               | multiple `class XxxError`                   |
| Test                | `<file>.spec.ts`                            | —                                            |

All file names: **kebab-case**. All class names and types: **PascalCase**. Interfaces have **no `I` prefix**.

---

## 7. Common pitfalls

| Pitfall                                                            | Fix                                                          | See       |
|--------------------------------------------------------------------|--------------------------------------------------------------|-----------|
| Adding a file to `domain/_shared/` outside the whitelist           | Move to a feature folder; if cross-feature, pick a primary    | A10       |
| Creating `usecase/_shared/` for cross-feature use cases            | Pick the primary aggregate's folder; or named composite      | section 3 |
| Wrong file suffix (camelCase, missing `.usecase`/`.entity` etc.)   | Match the naming table strictly                               | A24       |
| Use case named after the noun (`user.usecase.ts`)                  | Name it after the verb-noun (`create-user.usecase.ts`)        | A25       |
| Missing in-memory implementation alongside the Prisma one          | Add the fake; LSP requires substitutable contracts            | rule 13   |
| Test file in a separate `tests/` folder mirroring `src/`           | Co-locate with the file under test (`<file>.spec.ts`)         | rule 19   |
| Production code importing from `tests/`                            | Reverse the dependency: tests import production               | rule 1    |
| Adding a barrel `index.ts` outside `infra/http/index.ts`           | Import from specific files                                    | A4        |

---

## Cross-references

- **`SKILL.md` rules**: 1 (three layers + dependency rule), 2 (`process.env` only in `config/`), 3 (mirrored feature folders), 4 (no barrels except `infra/http/index.ts`), 5 (`_shared` whitelist).
- **`anti-patterns.md`**: A4 (barrels), A10 (`_shared` junk drawer), A24 (wrong suffix), A25 (use case named after noun).
- **`domain-modeling.md`**: what goes in `domain/` (entities, VOs, interfaces, errors).
- **`use-case-pattern.md`**: how use cases are organized inside `usecase/<feature>/`.
- **`repository-and-queries.md`**: contracts and implementations under `infra/repository/` and `infra/queries/`.
- **`composition-root.md`**: how `infra/http/index.ts` and `main.ts` come together.
- **`cross-feature-use-cases.md`**: detailed treatment of multi-aggregate flows.
