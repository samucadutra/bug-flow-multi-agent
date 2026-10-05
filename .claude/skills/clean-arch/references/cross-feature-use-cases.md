# Cross-feature use cases

Where to place a use case that touches multiple aggregates from different features. Read alongside `SKILL.md` rule 3 (mirrored feature folders) and `folder-structure.md` section 3.

Most use cases mutate exactly one aggregate; their feature folder is obvious. Cross-feature use cases — `RegisterUser` (User + Profile), `OnboardCompany` (Company + initial Owner User + initial Tenant config), `TranscribeVideo` (Video + Transcription) — need a placement rule. The skill prescribes a default and a single fallback.

---

## 1. The decision tree

```
Does this use case touch more than one aggregate?
├─ No  → live in usecase/<feature>/ named after the aggregate.
└─ Yes → can you name a primary aggregate?
         ├─ Yes → live in usecase/<primary>/ named with the verb-noun.
         └─ No  → composite-flow folder usecase/<flow-name>/.
```

In practice, the "Yes" branch covers ~95% of cross-feature flows. The composite-flow folder is rare.

---

## 2. Default — primary aggregate

The **primary aggregate** is the one whose creation/mutation gives the use case its name.

### How to identify it

Read the use case name backward. The verb-noun (`Register-User`, `Onboard-Company`, `Transcribe-Video`) names the primary aggregate.

### How to confirm it

Mentally remove the secondary effects. Is the use case still meaningful?

- `RegisterUser` creates User + Profile. Without Profile creation, you still have a meaningful "register user" — the Profile is supportive. **Primary: User.**
- `OnboardCompany` creates Company + Owner User + Tenant config. Without Owner User, you cannot onboard (a company without an owner is not onboarded). The Company is the *named subject*; the Owner User is required for the operation but does not name it. **Primary: Company** (the use case is "onboard the company"). The Owner User creation is part of how onboarding happens.
- `TranscribeVideo` mutates Video (writes the transcription back) and uses TranscriptionEngine (gateway, not aggregate). **Primary: Video.**

### Where it lives

```
usecase/user/register-user.usecase.ts                # touches User + Profile
usecase/company/onboard-company.usecase.ts           # touches Company + User + Tenant
usecase/video/transcribe-video.usecase.ts            # touches Video; uses TranscriptionEngine
```

The use case is one class with one `execute`. It depends on the repositories of all aggregates it touches:

```ts
// usecase/user/register-user.usecase.ts
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

Notes:
- It uses `UnitOfWork` because two aggregates are written atomically (opt-in pattern; see `composition-root.md` section 3).
- It imports from `domain/user/`, `domain/profile/`, and `domain/_shared/`. Cross-feature imports inside `domain/` are normal — features reference each other, just not by direct entity reference (only by ID — see `domain-modeling.md` aggregate rules).
- The DTO file `register-user.dto.ts` lives next to the use case, in `usecase/user/`.

---

## 3. The composite-flow exception

Some flows have **no primary aggregate** — multiple aggregates of equal weight participate in a coordinated process. These are rare but real. Examples:

- A subscription billing cycle that consumes a `Subscription`, generates `Invoice`s, charges via `Payment`, and updates `Account` balance — all four are equally part of the cycle.
- A multi-step workflow (`UserOnboardingFlow`) that has phases, each touching different aggregates, where the named subject is the *flow itself*, not any one aggregate.

For these, create a **named composite folder**:

```
usecase/user-onboarding/
  start-onboarding.usecase.ts
  start-onboarding.dto.ts
  complete-onboarding.usecase.ts
  complete-onboarding.dto.ts
  cancel-onboarding.usecase.ts
  cancel-onboarding.dto.ts
```

Conventions:

- **The folder name describes the flow**: `user-onboarding`, `subscription-billing`, `checkout`, `tenant-provisioning`.
- **Not generic names**: never `_shared`, `cross`, `multi`, `common`. The folder name says what the flow *is*, not that it crosses features.
- **The folder has a single coherent purpose** — if you are tempted to put unrelated cross-feature use cases in the same composite folder, they are probably each primary-aggregate use cases in disguise.
- **Mirroring**: composite folders generally do **not** appear in `domain/`, `infra/repository/`, or `infra/queries/`. They are use-case-only folders. The aggregates they touch live in their own feature folders. The composite folder owns only the orchestration.

The mirror exception: if a composite flow has a genuinely new aggregate of its own (e.g., `OnboardingSession` aggregate that tracks state across phases), then `domain/user-onboarding/` may exist for that aggregate. In that case it is a *new feature*, and the cross-feature label was wrong — pick a single noun that describes the aggregate (`onboarding-session/`, not `user-onboarding/`).

---

## 4. Forbidden placements

| Placement                     | Why it's wrong                                         |
|-------------------------------|--------------------------------------------------------|
| `usecase/_shared/`            | The convention is the whitelist `domain/_shared/`. There is no `usecase/_shared/`. Cross-feature use cases have a primary aggregate or a composite-flow name. |
| `usecase/cross/`              | Vague — "crosses what?" — and tempts everything-bin growth. |
| `usecase/multi/`              | Same. |
| `usecase/common/`             | Same; also collides with the implication "common helpers". There are no helpers in `usecase/`. |
| `usecase/<primary>/<secondary>/` | Nested feature folders are not allowed; flat inside a feature folder. |

`check-architecture.ts` flags these patterns and asks for a primary-aggregate folder or a named composite-flow folder.

---

## 5. Worked examples

### Example A — `RegisterUser`

**Touches**: `User` (created), `Profile` (created with defaults).
**Primary**: `User` — the use case is named "register user".
**Folder**: `usecase/user/register-user.usecase.ts`.
**Imports**: from `domain/user/`, `domain/profile/`, `domain/_shared/unit-of-work.ts`.
**Wraps in UoW**: yes (two writes).

### Example B — `UploadVideo`

**Touches**: `Video` (created), `Storage` gateway (writes file).
**Primary**: `Video` — the use case is named "upload video".
**Folder**: `usecase/video/upload-video.usecase.ts`.
**Imports**: from `domain/video/`, `domain/storage/storage.gateway.ts`.
**Wraps in UoW**: optional. The storage write is not transactional with the DB save; if storage succeeds and DB save fails, you have an orphan file. Acceptable: clean up via a periodic sweeper. Not acceptable: a UoW would not help here (storage is not transactional).

### Example C — `SuspendUser` (admin action)

**Touches**: `User` (mutated), authorization check loads actor's `User`.
**Primary**: `User`.
**Folder**: `usecase/user/suspend-user.usecase.ts`.
**Wraps in UoW**: no (one write).

### Example D — `ProcessVideoPipeline` (background, multi-stage)

**Touches**: `Video` (status transitions), `Transcription` data, `Summary` data; `TranscriptionEngine` and `SummaryEngine` gateways.

If `Transcription` and `Summary` are VOs inside the `Video` aggregate (they belong to one video, never exist independently), then **primary is `Video`** and the use case lives in `usecase/video/`. Single aggregate; standard placement.

If `Transcription` and `Summary` were separate aggregates (with their own IDs, lifecycles), then this is a candidate for split: `TranscribeVideo`, `SummarizeVideo`, two use cases in `usecase/video/`, each touching one aggregate, coordinated by the worker layer (each phase is its own `Job`).

For the videomax PRD: Transcription and Summary are part of the Video — the use case is one, primary is `Video`, lives in `usecase/video/`.

### Example E — Subscription billing cycle

**Touches**: `Subscription`, `Invoice`, `Payment`, `Account` — four aggregates, none clearly primary.
**Composite-flow**: yes.
**Folder**: `usecase/subscription-billing/`.
**Use cases inside**: `start-cycle.usecase.ts`, `process-charge.usecase.ts`, `finalize-cycle.usecase.ts`.

This is the rare case where the composite folder is justified. The flow itself (`subscription-billing`) is the named concept; no single aggregate dominates.

---

## 6. Common pitfalls

| Pitfall                                                            | Fix                                                          |
|--------------------------------------------------------------------|--------------------------------------------------------------|
| Creating `usecase/_shared/` for "shared" use cases                 | Pick the primary aggregate's folder; or named composite      |
| Using a generic name (`cross`, `multi`, `common`) for the folder   | Name the flow concretely (`user-onboarding`, `checkout`)     |
| Splitting a cross-feature use case across multiple files           | One use case = one class = one file                          |
| Creating a "cross-feature service" with multiple methods           | These are separate use cases; one class each                 |
| Placing a use case in the secondary aggregate's folder             | Re-read the verb-noun; primary is named in it                |
| Creating a `domain/<flow-name>/` folder when only orchestration crosses features | Aggregates live in their own feature folders; the flow lives in `usecase/<flow-name>/` only |

---

## Cross-references

- **`SKILL.md` rules**: 3 (mirrored feature folders), 10 (one use case per class), 11 (DI by constructor — `UnitOfWork` is injected like any other dependency).
- **`folder-structure.md`**: section 3 introduces this; this doc is the deep dive.
- **`use-case-pattern.md`**: section 6 (Unit of Work for multiple writes).
- **`domain-modeling.md`**: aggregate boundaries — the question "is this one aggregate or two?" determines whether a flow even crosses features.
- **`domain-events.md`**: when cross-aggregate consistency does NOT need a single transaction — events provide eventual consistency.
