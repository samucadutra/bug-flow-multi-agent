# Testing — structural conventions only

This skill defines **only structural conventions for tests**: where tests live, how they are named, and how the architecture supports testing through in-memory implementations of every contract. The *what* and *how* of testing — strategies, types of tests, mocking philosophy, coverage thresholds — belong to a separate testing skill.

Read alongside `SKILL.md` rules 13 (CQRS-lite, fakes), 19 (self-audit), and `folder-structure.md` section 5.

---

## 1. Co-location

Test files live next to the file they test, named `<file>.spec.ts`:

```
domain/user/
  user.entity.ts
  user.entity.spec.ts
  email.vo.ts
  email.vo.spec.ts
usecase/user/
  create-user.usecase.ts
  create-user.usecase.spec.ts
infra/repository/user/
  user.prisma-repository.ts
  user.prisma-repository.spec.ts
  user.in-memory-repository.ts
  user.in-memory-repository.spec.ts
```

Why co-located:
- **Renaming the file under test surfaces the test alongside it.** No orphan tests.
- **Imports are `from './user.entity'`**, not `from '../../../src/domain/user/user.entity'`. Refactoring folders does not break test imports.
- **The presence of a test file is visible in the folder.** A feature folder with no `.spec.ts` is a flag.

---

## 2. The `.spec.ts` suffix

The suffix is `.spec.ts`, not `.test.ts`. Conventional in OOP-heavy ecosystems (Angular, NestJS, Mocha). Easy to grep, easy to filter in test runners (`vitest run **/*.spec.ts`).

`check-architecture.ts` flags any test file in a separate folder mirroring `src/` — tests live next to source.

---

## 3. In-memory implementations are part of the architecture

Every interface that has a production implementation (`Repository`, `Queries`, `Gateway`) also has an **in-memory implementation** sitting next to it in `infra/`:

```
infra/repository/user/
  user.prisma-repository.ts        # production implementation
  user.in-memory-repository.ts     # in-memory implementation (tests, demos, no-DB dev)

infra/queries/user/
  user.prisma-queries.ts
  user.in-memory-queries.ts

infra/gateway/
  openai-transcription.gateway.ts
  fake-transcription.gateway.ts    # for tests / local dev
```

The in-memory implementation:
- Implements **the same interface** as the production one.
- Implements **all methods** (LSP — substitutability is the contract). Methods that throw `'not implemented'` are violations.
- Uses the **real domain entity**. There is no "test entity" or contrived data class.
- May be wired in `main.ts` for demo modes (e.g., `NODE_ENV=demo` swaps Prisma for in-memory).

This is structural, not test-specific: the in-memory implementation is a real production-grade artifact. Use it from a no-DB demo binary, from a CLI tool, from an offline development setup. The fact that it is also useful in tests is a consequence, not the purpose.

`check-architecture.ts` requires every `<feature>.<provider>-repository.ts` to have a corresponding `<feature>.in-memory-repository.ts` next to it. Same for queries.

---

## 4. The `tests/` folder at project root

Cross-cutting test infrastructure (helpers, builders, fixtures, DB setup) lives in `tests/`, **outside `src/`**:

```
tests/
  _shared/
    builders/
      user.builder.ts
      video.builder.ts
    fixtures/
      sample-video.mp4
    db.ts                            # any helper for setting up a test database
```

Conventions:
- **Tests inside `src/` may import from `tests/`** (one-way). Production code never imports from `tests/`.
- **Builders and fixtures are not part of the architecture** — they are testing-only conveniences. The testing skill prescribes their shape; this skill only fixes the location.
- **`dependency-cruiser` enforces the one-way rule**: imports from `tests/` are allowed only inside `**/*.spec.ts` files.

---

## 5. What this skill does NOT prescribe

Hand off to the separate testing skill for:

- **What types of tests to write** (unit, integration, contract, end-to-end, property-based).
- **What to mock vs what to fake** (philosophy: prefer fakes — but the testing skill argues this in detail).
- **Coverage thresholds.**
- **Test-data builder patterns** (object mother, builder, factory).
- **Database setup** (Docker, testcontainers, a local Postgres, an SQLite override, a transaction-rollback strategy).
- **HTTP test approach** (in-process supertest, full e2e against a running server, contract testing).
- **Snapshot testing** policy.
- **Test runner choice** (Vitest, Jest, Node test runner).

When the testing skill is loaded, it builds on the structure this skill defines: co-located `.spec.ts`, in-memory fakes as substitutable implementations, `tests/` for shared infrastructure.

---

## 6. Common pitfalls

| Pitfall                                                       | Fix                                                          |
|---------------------------------------------------------------|--------------------------------------------------------------|
| Tests in a separate folder mirroring `src/` (e.g., `tests/unit/domain/user/...`) | Co-locate next to the file under test                  |
| `.test.ts` suffix instead of `.spec.ts`                       | Use `.spec.ts` for consistency                                |
| In-memory repo missing methods (`throw 'todo'`)               | Implement all methods of the contract                         |
| In-memory repo using a different entity shape                 | Use the real domain entity; do not invent test entities       |
| Production code importing from `tests/`                       | Reverse the dependency; tests import production               |
| Builder living inside `src/` instead of `tests/_shared/builders/` | Move to `tests/`; builders are test-only                  |
| Forgetting to write the in-memory counterpart                 | `check-architecture.ts` flags missing in-memory implementations |

---

## Cross-references

- **`SKILL.md` rules**: 13 (CQRS-lite — both contracts have in-memory implementations), 19 (self-audit gates).
- **`folder-structure.md`**: section 5 (co-location, `tests/` folder layout).
- **`repository-and-queries.md`**: in-memory repositories and queries as architectural artifacts.
- **`composition-root.md`**: how a demo mode wires in-memory implementations through the same composition root.
