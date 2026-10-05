---
name: spec-writer
description: Generates technical implementation spec, plan, and behavior contract for one or more features based on PRD, codebase analysis, and iterative clarification. The contract is a stack-agnostic, consumer-agnostic GWT-style file (`contract.md`) describing the testable promise of the feature. Supports batch mode for generating multiple features from the same wave in parallel.
---

# Feature Specs Writer

Generate implementation-ready technical specifications based on the project's PRD and existing codebase patterns. The skill has two modes:

- **Single-feature mode (default):** operates on one feature at a time, identified by its PRD feature ID (F01, F02...), with an interactive interview (Steps 1–7 below).
- **Batch mode:** operates on multiple features from the same wave in parallel, auto-accepting all interview recommendations. Activated automatically when the input contains multiple IDs, a wave reference, or a mix. See the **Batch Mode** section near the end of this file.

**Output:** THREE files are required:
1. `spec.md` - Technical specification (7 sections)
2. `plan.md` - Implementation plan (phases and steps)
3. `contract.md` - Behavior contract (verification surfaces + GWT items + coverage manifest); the testable promise of the feature, written in consumer-agnostic language so any tool, agent, or human can read and exercise it

**Output location:** `docs/<feature-id>-<kebab-name>/spec.md`, `docs/<feature-id>-<kebab-name>/plan.md`, and `docs/<feature-id>-<kebab-name>/contract.md`
- The `<kebab-name>` is derived from the feature's name in the PRD Section 6 (lowercase, spaces → hyphens, special characters removed). Example: `F03. Video Upload` → `docs/F03-video-upload/`.

`contract.md` is a **sibling** of `spec.md`, not a child: both are generated in the same run from the same PRD, but the contract's content is grounded in PRD Section 9 acceptance criteria (not in the spec's implementation choices), so refactoring the implementation never affects the contract.

---

## Execution Steps (7 Steps)

Note: These are internal agent execution steps. The OUTPUT plan document will have 1-5 phases based on feature complexity.

### Step 1: Resolve Input and Pre-Analysis

**1.1: Identify the PRD and the target feature**

Accept free-form input from the user. The user may reference the feature by ID (`F03`), by name (`Video Upload`), by path (`docs/PRD.md F03`), or any combination. Resolve the reference:

- Locate the PRD file from the user's reference or look for `docs/PRD.md`, `PRD.md`, or similar conventional locations. If multiple plausible PRDs exist, ask the user which one.
- Identify the target feature within the PRD by ID or name.
- If the input is ambiguous (e.g., "upload" matches multiple features), confirm with the user before proceeding.
- If the referenced feature does not exist in the PRD, list available features from Section 8 and ask the user to clarify.

**Optional flag:** the input may include `create-issue` (anywhere). When present, the skill will create a GitHub tracking issue for the feature in Step 6 without prompting. When absent in single-feature mode, Step 6 will ask the user `y/n` before creating; when absent in batch mode, the orchestrator's consolidated plan (B.4) asks once and the answer applies to every feature in the batch. See **Step 6** for the issue creation flow and **Batch Mode** for the batch interaction.

**PRD is mandatory.** If no PRD is found in the project, stop and instruct the user to generate one first with the `prd-writer` skill. Do not fall back to an unstructured interview.

**1.2: Check dependency readiness and Foundation features (greenfield)**

Read the PRD's Section 8 (Dependency Graph). For every feature in the target feature's `Dependencies` column, check whether it appears to be implemented in the codebase (source files exist matching the feature's scope). If any dependency is not yet implemented, warn the user: "F<X> depends on F<Y> (not yet implemented). Continue anyway?" Proceed only if confirmed.

If the PRD contains a **Foundation Features** subsection in Section 8, apply these additional checks based on the implementation state of each Foundation feature:

- **Foundation state detection (the correct greenfield signal):** for each feature listed in Foundation Features, check whether it appears implemented in the codebase by looking for one or more characteristic output files that the feature is supposed to create — for example, an ORM schema or migration file for a database Foundation, a session/middleware module for an auth Foundation, a root layout/template file for a layout Foundation, or any equivalent artifact in the stack being used (web framework, backend service, mobile app, etc.). Do NOT rely on the mere presence of generic project markers such as a source folder or a package/manifest file — any scaffolding tool (`create-next-app`, `rails new`, `django-admin startproject`, etc.) already creates those, yet the PRD's Foundation features may still be unimplemented.
  - **Greenfield** = zero Foundation features are implemented yet.
  - **Partial Foundation** = some Foundation features are implemented, others are still pending.
  - **Foundation complete** = every Foundation feature is implemented.
- **Scenario 1 — greenfield + target feature IS a Foundation feature:** proceed without extra warning. This is the expected path for a greenfield project.
- **Scenario 2 — greenfield + target feature is NOT in Foundation Features:** warn the user: "This appears to be a greenfield project (no Foundation feature is implemented yet). F<target> is not a Foundation feature. Foundation features (F<ID>, ...) set up the shared infrastructure and should be implemented first. Recommend starting with F<first-foundation>. Continue with F<target> anyway?" Proceed only if confirmed.
- **Scenario 3 — Partial Foundation (some Foundation features implemented, others pending) and target is not one of the remaining Foundations:** list the pending Foundation features and warn: "Foundation features F<ID1>, F<ID2>... are not yet implemented. Implementing F<target> before these may create file conflicts in the scaffolding. Continue anyway?" Proceed only if confirmed.
- **Foundation complete (mature codebase for Foundation purposes):** skip all Foundation-specific checks. The normal dependency readiness check above is enough.

**Batch Mode note:** In Batch Mode, the orchestrator performs these dependency and Foundation checks once across the whole batch (B.2 and B.3) and filters features before dispatch. Sub-agents skip every "warn the user / Continue anyway?" prompt in this step — assume the check was already resolved by the orchestrator and proceed.

**1.3: Codebase Pattern Discovery (two layers)**

Explore the codebase before writing the spec (before the interview in single-feature mode; before applying the Auto-Accept Policy in Batch Mode) to extract patterns. This is mandatory whenever the codebase is non-empty — do not wait for the user to provide paths.

**Layer 1 — Baseline (floor, not ceiling):** at minimum, extract observable patterns in these categories. Examples are illustrative across multiple stacks — the categories are the stack-agnostic intent.
- Runtime and language (any — Node, Python, Ruby, Go, Java, .NET, Rust, PHP, etc.)
- Framework and project layout (any — Next.js/Remix, Django/Flask/FastAPI, Rails, Spring, Phoenix, etc.)
- Database and data access (any — Postgres/MySQL/Mongo/SQLite; Prisma/SQLAlchemy/ActiveRecord/GORM/Entity Framework; raw SQL)
- Authentication strategy and library
- API or entry-point style (REST, GraphQL, RPC, CLI, job queue, event handler — whatever the project uses) and response/error format
- Validation approach (typed schemas, runtime validators, manual checks — whatever the codebase prefers)
- Testing framework and style (unit and integration)
- Error handling (exceptions, Result types, error codes, panic/recover, etc.)
- Folder structure and naming conventions
- **Persistent-state seeding convention** (used by `contract.md` Prerequisites). How does the project arrange test data — migrations + seed files (`prisma/seed.ts`, `db/seeds/`), factory functions (`tests/factories/`), setup hooks (`globalSetup`, `beforeAll`), INSERT helpers, or something else? Inspect the test setup code, seed/migration folders, factory files, and existing `contract.md` files in `docs/F*-*/` for the dominant mechanism.
- **Static-input / fixture path convention** (used by `contract.md` Prerequisites). Where do test data files live — `tests/fixtures/`, `__fixtures__/`, `fixtures/`, `cypress/fixtures/`, `playwright/fixtures/`? Per-app or root? Read prior `contract.md` files first; their declared paths are authoritative when present.
- **Test configuration convention** (used by `contract.md` Prerequisites). `.env.test`, `config/test/`, framework-specific blocks — the file (or scheme) the test runner reads for env vars and flags.
- **Mock / external-dependency convention** (used by `contract.md` Prerequisites). `tests/mocks/`, MSW handlers, mountebank stubs, etc. Discovered when items will eventually demand simulated externals.

**Layer 2 — Broad exploration (also mandatory):** beyond the baseline, capture any additional pattern you observe that could inform implementation — architectural decisions, codebase idioms, recurring abstractions, logging/observability, config management, deploy conventions, internationalization, accessibility, anything. Do not restrict yourself to the baseline list. A thorough report in a medium project typically has 8-15 patterns.

**1.4: Empty codebase handling**

If the codebase is empty or only has scaffolding (e.g., only `package.json` with defaults, no `src/` implementation yet), skip Layer 1/Layer 2 discovery and instead plan to ask transversal stack questions inline during Step 2 (these questions will only be asked once — on the first feature. Subsequent features will find the answers in the codebase).

**Batch Mode note:** In Batch Mode there is no Step 2 interview. Apply the "Empty codebase bootstrap" row of the Auto-Accept Policy: fall back to industry best practices for the detected stack (or for the scaffolding that exists, if any), and document every bootstrap choice explicitly under the spec's Assumptions/Decisions section.

**1.5: Read the PRD feature data**

Extract the target feature's full definition from the PRD and load it as context for the spec (used by the interview in single-feature mode, and by the Auto-Accept Policy in Batch Mode):
- Feature name and ID
- Consumes block (if present)
- Provides block (if present)
- Core Scope block (if present)
- Full Scope additions block (if present)
- Capabilities
- Experience
- Error Handling (if present)
- Section 9 per-feature acceptance criteria
- Section 9 Cross-Feature Integration criteria that reference this feature (either as the consumer or the provider)

**1.6: Present understanding to the user**

```
Based on my analysis, I understand you want to implement:

**Feature:** F<ID>. <Name>
**Technical Summary:** [1-2 sentences derived from PRD Capabilities + Experience]
**Observed codebase patterns:** [summary of Layer 1 + Layer 2 findings, or "empty codebase — will bootstrap"]
**PRD context loaded:** Consumes, Provides, Core Scope, Full Scope, Capabilities, Experience, Error Handling, acceptance criteria

I need to clarify some technical decisions that the PRD and codebase don't already answer.
```

**Batch Mode note:** Sub-agents skip this step — there is no interactive user to present to. The orchestrator's consolidated plan (B.4) covers shared understanding for the batch.

### Step 2: Interview

**Batch Mode override:** In Batch Mode, this entire step is replaced by the Auto-Accept Policy (see Batch Mode section). Sub-agents skip Step 2 and proceed directly to Step 3 with the Auto-Accept defaults applied. Every "ask the user" instruction below becomes "apply the Auto-Accept default and document the choice in the spec's assumptions".

Interview the user relentlessly about every aspect of this plan until we reach a shared understanding. Walk down each branch of the design tree, resolving dependencies between decisions one-by-one. For each question, provide your recommended answer.

Ask the questions one at a time.

If a question can be answered by exploring the codebase or reading the PRD, explore or read instead of asking.

**Scope question (ask first, when applicable):** If the feature has both `Core Scope` and `Full Scope additions` blocks in the PRD, ask: "Should the spec cover Core Scope only, or Core + Full Scope additions?". If only one of the blocks is present, or neither is present, skip this question and assume the full feature scope.

**Quality gates clarification (ask second, after the scope question):** Detect the project's quality gates from the project context already in your reach (the harness has injected `CLAUDE.md` and project docs; manifests like `package.json`, `Makefile`, `Taskfile`, `justfile`, `pyproject.toml`, etc., are readable). Surface the detected list to the user: "I detected these quality gates from the project — confirm or edit the list before I write `## Quality gates` into the contract." Each detected entry should carry a name, the literal command to run, and a one-line description of what passing means. Accept the user's edits (additions, removals, reorderings, command corrections, description rewrites) before continuing. If you find no gates, ask: "I did not detect quality gates in this project. Skip the `## Quality gates` section in the contract?" — the user may decline (in which case ask them to dictate the gates inline) or accept (the section is omitted entirely from the generated contract).

**Anti-redundancy rule:** Do NOT ask about anything already observable in:
- The PRD's feature definition (Consumes, Provides, Core Scope, Capabilities, Experience, Error Handling)
- The PRD's acceptance criteria for this feature
- The codebase patterns discovered in Step 1.3
- A previously generated `spec.md` or `plan.md` for another feature in the same project (when those exist and are relevant)

Focus the interview on decisions the PRD and codebase **do not** already answer: internal architecture, database schema details (columns, indexes, constraints), endpoint signatures, validation rules not specified in Capabilities, naming of new files, choice between libraries when patterns aren't established, edge cases not covered by Error Handling.

**Partial PRD specifications:** When the PRD mentions a capability but omits a specific detail (e.g., "chunked upload" without chunk size), ask for the missing detail rather than assuming a default.

**Empty codebase bootstrap:** If Step 1.4 flagged empty codebase, ask transversal stack questions inline during this step (framework, ORM, auth, API style, validation, testing, error handling, folder structure). Once the first feature is implemented, the codebase becomes the reference for subsequent features.

### Step 3: Summary and Assumptions

After receiving answers:
- Summarize technical decisions made
- List assumptions derived from PRD, codebase patterns, and interview answers
- Explicitly note which PRD blocks informed which parts of the spec (traceability)

**Batch Mode note:** In Batch Mode there are no interview answers. Treat each Auto-Accept default that was applied as if it were an interview answer — list it under assumptions, name the policy row that produced it, and flag it so the user can review and override later. Traceability to PRD blocks works the same way as in single-feature mode.

### Step 4: Generate Documents

**Announce:** "Generating THREE documents: SPEC, PLAN, and CONTRACT..."

**Scaling guidance by complexity:**
- trivial: 1-2 phases, 2-4 steps
- simple: 2-3 phases, 5-8 steps
- medium: 3-4 phases, 10-15 steps
- complex: 4-5 phases, 15-25 steps

Note: SPEC document depth (schemas, indexes, migrations) scales with complexity. PLAN steps are always high-level regardless of complexity.

**4.1: Generate SPEC**:
- Scale sections based on COMPLEXITY_LEVEL:
  - trivial/simple: Skip API Contracts and Data Model if not applicable
  - medium/complex: All 7 sections required
- Scale depth within sections based on complexity
- Include JSON examples, SQL migrations, test specifications
- **Testing Strategy section content:** describe test files, test functions, frontend tests, and E2E scenarios as implementation guidance for whoever writes the code. **Do not include an "Acceptance test mapping (PRD Section 9)" table, do not attach an "Acceptance criterion covered" column to E2E or other sub-tables, and do not annotate cross-feature ACs as "OUT OF SCOPE" inside spec.md.** AC ↔ verification mapping is generated separately into `contract.md`'s Coverage Manifest in step 4.3, which is the single source of truth for that linkage. The cross-feature filter is encoded silently by which ACs make it into the Coverage Manifest — never by an in-spec annotation.
- **If FEATURE_CROSS_CUTTING exists:** Include integrated cross-cutting concerns in the Scope section:
  ```
  **Included:**
  - Core feature functionality
  - Integrated from cross-cutting concerns:
  ```

**PRD → SPEC mapping (apply consistently across all specs):**

| PRD block | Spec.md destination |
|-----------|---------------------|
| Consumes | Scope (input contracts) + API Contracts (when the input arrives via API) |
| Provides | Scope (output contracts) + API Contracts (when the output is exposed via API) |
| Core Scope | Scope → "Included" |
| Full Scope additions | Scope → "Deferred" (when user picked Core only) or "Included" (when user picked Core + Full) |
| Capabilities | Requirements / Business Rules |
| Experience | Requirements / UX Flows |
| Error Handling | Error Handling section |

**Note on PRD Section 9 acceptance criteria:** Section 9 ACs are NOT mapped inside `spec.md`. The single source of truth for AC ↔ verification mapping is `contract.md`'s Coverage Manifest (verbatim AC text → covering item IDs). `spec.md`'s Testing Strategy section still lists test files, frontend tests, and E2E scenarios as implementation guidance, but does NOT carry an "AC ↔ test" table or any column that ties scenarios to ACs. Cross-Feature Integration criteria (referencing this feature) likewise live in the contract that owns them, never in this feature's spec. This separation lets the implementer focus on structure/architecture (spec) and the contract evaluator own behavioral verification (contract).

**4.2: Generate PLAN**:
- Prerequisites section
- Phases with numbered steps (1-3 sentences each, high-level)
- Describe WHAT to do, reference spec for HOW

**4.3: Generate CONTRACT**:
- Read the full format, surface catalog, item schema, guard-rails, Prerequisites rules, and coverage-manifest rules from `references/contract-template.md`. That template is the single source of truth for `contract.md` shape — do not improvise structure.
- **Filter PRD Section 9 ACs against the feature's spec.md `Included` block before generating items.** ACs whose verifying behavior belongs to another feature entirely (whether downstream of this one, sibling in the same wave, or anywhere else in the PRD) are dropped silently — they do not enter the manifest, do not generate items, and do not produce console warnings during generation. The remaining set is the "in-scope ACs". Principle: every item must be testable with this feature + its PRD Section 8 dependency closure implemented; items requiring features OUTSIDE the dependency closure to verify their behavior must not be generated. (When the AC's behavior is this feature's but its natural test setup would need outside infrastructure, do not drop the AC — keep it and apply the Preparation Pattern in the dependency-closure rule below.)
- Detect which surfaces apply (`Service`, `HTTP API`, `CLI`, `UI`, `Worker`, `Event`, `E2E`) by inspecting PRD Capabilities, Experience, and Provides for surface signals. In single-feature mode, ask during the interview when ambiguous. In Batch Mode, default to "all surfaces with at least one PRD signal" and document the decision under Assumptions.
- Apply the **Service Admission Rule** strictly: emit `## Service` only when there is a real consumer outside this feature. Never emit it for internal helpers, VOs, entities, or per-class items.
- Generate items with the four guard-rails on `then` (surface cohesion, action atomicity, ~5 bullet soft cap, atomic bullet). Use `Common given:` per capability to avoid repetition.
- Item IDs follow `<SURFACE>-<CAPABILITY>-<NN>` (no feature ID prefix). Surface codes: `SVC`, `API`, `CLI`, `UI`, `WRK`, `EVT`, `E2E`.
- Build the **Coverage Manifest** at the top (after Prerequisites) by mapping every in-scope PRD Section 9 AC to its covering item IDs. The first column carries the **verbatim AC text from the PRD**, not a synthetic ID.
- Build the **Prerequisites** section as the first `##` section under the title (the italic regeneration line below the title is not a section), placed above the Coverage Manifest. Derive forward-looking conditions without inspecting the filesystem (the implementation does not exist yet); use the project conventions captured in Step 1.3 to anchor paths and mechanisms.
- Build the **Quality gates** section directly after `## Prerequisites` and before `## Coverage Manifest`. Render each gate confirmed in the Step 2 clarification turn as a bullet of the shape `- **<name>** — \`<command>\` — <one-line description of what passing means>`. Open the section with one short paragraph that says "Each gate must pass for the feature to be considered ready" — describe behavior only, never name an executor (no "the evaluator runs", no fail-fast vocabulary, no order-of-execution prescription). If the user declined the section in the Step 2 clarification (no gates detected and no manual list provided), omit the section entirely — do not render an empty placeholder.
- Use the **five fixed subsections** in this order, omitting any with no entries (no "none." placeholder): `Runtime services`, `Persistent state`, `Static inputs`, `Configuration`, `External dependencies`.
- **`Persistent state` and `Static inputs` are NEVER conflated.** Persistent state covers entities/accounts/rows/messages/tokens that must exist *inside* the system store/queue (declarative WHAT — the project's seeding convention dictates HOW). Static inputs covers files items reference by path (the project's fixture path convention dictates WHERE on disk). An account belongs to Persistent state, never to Static inputs. A video file belongs to Static inputs, never to Persistent state.
- **Reuse the project's discovered conventions, never invent paths or mechanisms.** Static-input paths come from the project's fixture path convention discovered in Step 1.3 and declared by prior contracts in `docs/F*-*/`. Persistent-state entries are written declaratively; the implementer fulfills them via the project's seeding convention discovered in Step 1.3. Configuration entries follow the project's test-config convention. External dependencies follow the project's mock convention.
- **Dependency-closure rule for Prerequisites (independence vs preparation).** Every Prerequisites entry MUST be satisfiable from this feature's own deliverables OR from features in this feature's PRD Section 8 **dependency closure** (this feature + its declared dependencies + their transitive dependencies). Never declare a prereq that requires a feature **outside** this closure to be implemented — even when the outside feature sits in the same wave or appears "logically related". The Section 8 dependency table is the only authoritative source of what this feature may rely on.

  When an in-scope AC describes this feature's own surface behavior but its natural test setup would normally need infrastructure from an outside-of-closure feature (typical case: a sibling feature that builds auth, sessions, payments, file storage, etc.), apply the **Preparation Pattern**:

  1. Confirm the AC describes THIS feature's surface behavior. If it actually describes a system-level integration with another feature, drop it as cross-feature (the existing Step 4.3 filter handles this).
  2. Treat the missing infrastructure as a stub/override/flag that THIS feature delivers as part of its own scope — not as a real-world state the sibling feature produces.
  3. Phrase the prereq around the F-internal mechanism, never around the sibling feature's real state.

  Concrete example. F01 (Landing Page, deps: none) has the AC "authenticated users visiting `/` are redirected to `/app`". Auth is delivered by F02 (sibling, also no deps). F02 is **outside** F01's dependency closure. WRONG: declare `landing-returning-user — exists as a real authenticated user with a valid session`, which requires F02's auth flow. RIGHT: declare a `Configuration` entry like `the session check used by /` `can be driven into an authenticated state via an F01-scoped test mechanism (test-only flag, session-module override, or test cookie honored by F01 itself); this mechanism is part of F01's deliverables.` F01 implements both the production behavior AND the test override; the contract is exercisable with F01 alone.

  Rationale: a feature's contract must be exercisable when only this feature + its declared dependencies are implemented. If it isn't, either (a) the contract reached outside its declared scope and the prereq is wrong, or (b) the AC is genuinely cross-feature and should have been filtered out in Step 4.3.
- **Greenfield (no convention found):** in single-feature mode, surface the question during the interview ("Where should fixtures live? How is test data seeded? Which env file does the test runner read?"). In Batch Mode, apply the most common default for the detected stack (e.g., `tests/fixtures/` for Node/Vitest projects) and document each chosen convention under the spec's Assumptions. Subsequent features in the same project reuse the choice.
- Cite consuming items in each Persistent state and Static inputs entry's `Used by:` clause. Items reference these entries by handle (account name, file path) in their `given` and `when`.
- Write Prerequisites in consumer-agnostic language — never name "the implementing agent" or "the evaluator"; just state the conditions.
- Subjective ACs (visual identity, qualitative judgment) are covered by a placeholder item carrying `notes: subjective; manual review only`.
- Cross-feature integration ACs from PRD Section 9 are NOT in this feature's manifest — they belong to the contract of the feature that owns them.

Use the following templates: `references/feature-template.md` (for spec/plan) and `references/contract-template.md` (for contract).

**Announce:** "Three documents drafted. Validating coverage..." (the actual save is contingent on Step 5 passing, including the contract hard coverage gate).

### Step 5: Validate and Save

**Validate before saving:**

SPEC document:
- [ ] Required sections present (all 7 for medium/complex, skip API/DB if N/A for trivial/simple)
- [ ] Component overview has complete file paths
- [ ] API contracts have JSON examples (if included)
- [ ] Data model has column types, indexes, constraints (if included)
- [ ] Testing strategy has specific test functions
- [ ] PRD blocks mapped correctly per the PRD → SPEC table
- [ ] Consumes/Provides from PRD are reflected in Scope or API Contracts
- [ ] **No AC ↔ test mapping in spec.md.** Testing Strategy lists test files / frontend tests / E2E scenarios as implementation guidance only; no "Acceptance test mapping (PRD Section 9)" table, no "Acceptance criterion covered" column on any sub-table, no per-AC traceability inside spec.md. AC ↔ verification mapping lives exclusively in `contract.md`'s Coverage Manifest.
- [ ] PRD Traceability section does not contain a row pointing AC text into spec.md (Coverage Manifest in `contract.md` is canonical for that linkage)

PLAN document:
- [ ] Numbered steps across phases
- [ ] Format: **N. Component** - High-level paragraph (1-3 sentences)
- [ ] Steps describe WHAT, not HOW (spec has details)

CONTRACT document:
- [ ] Title is followed by an italic regeneration line (`*Generated by spec-writer. Hand edits are overwritten on regeneration.*`), not by an HTML comment
- [ ] First `##` section under the title is `## Prerequisites` (the italic regeneration line is not a section); it sits above the Coverage Manifest and uses the **five fixed subsections** in order (`Runtime services`, `Persistent state`, `Static inputs`, `Configuration`, `External dependencies`), omitting any with no entries
- [ ] Prerequisites are written as forward-looking conditions, never as snapshots of current state. The phrasing supports two readings without privileging either: (a) for someone building the feature, prerequisites are deliverables to produce alongside the code; (b) for someone exercising the contract afterward, prerequisites are preconditions to verify before running items
- [ ] Generated content is consumer-agnostic: the contract never names "the implementing agent", "the evaluator", "the evaluating agent", or any specific tool — it describes behavior, not who runs it
- [ ] `Persistent state` and `Static inputs` are not conflated — accounts/rows/sessions/tokens never appear under `Static inputs`; files never appear under `Persistent state`
- [ ] `Persistent state` entries are declarative ("alice exists with X attributes"), never operational ("run this seed file" / "execute this SQL")
- [ ] `Static inputs` paths follow the project's discovered fixture path convention (matching prior `docs/F*-*/contract.md` declarations and existing fixture folders); no ad-hoc paths invented
- [ ] Every handle referenced in any item's `given` or `when` (account names, file paths) has a matching declaration in the corresponding Prerequisites subsection
- [ ] No declaration in `Persistent state` or `Static inputs` lacks at least one consuming item in its `Used by:` clause (no orphan declarations)
- [ ] **Dependency-closure check.** Every Prerequisites entry (across all five subsections) is satisfiable from this feature's own deliverables or from features inside this feature's PRD Section 8 dependency closure. No entry references a real-world state, account, session, capability, or runtime concept that exclusively a feature OUTSIDE the closure would produce. When an in-scope AC's natural test setup would have needed outside infrastructure, the prereq describes an F-internal stub/override/flag (the Preparation Pattern), not the outside feature's real state.
- [ ] If `## Quality gates` is present, it sits between `## Prerequisites` and `## Coverage Manifest`; each entry follows `- **<name>** — \`<command>\` — <description>`; the section preamble describes behavior only and never names an executor (no "the evaluator", no fail-fast vocabulary, no execution order prescription); when no gates were detected and the user declined to dictate any, the section is omitted entirely (no empty placeholder)
- [ ] `## Coverage Manifest` is the next `##` section under either `## Prerequisites` (when no Quality gates) or `## Quality gates` (when present) and maps verbatim in-scope PRD Section 9 AC text → covering item IDs
- [ ] No manifest row references an AC whose verification falls outside the feature's spec.md `Included` scope (cross-feature ACs were dropped silently as part of generation)
- [ ] Every top-level surface section corresponds to a surface from the catalog (`Service`/`HTTP API`/`CLI`/`UI`/`Worker`/`Event`/`E2E` or a documented extension)
- [ ] Every surface section has a `Verification mode:` line directly under the heading
- [ ] `## Service` (if present) names a real consumer outside this feature; no per-class/per-VO/per-helper items anywhere
- [ ] Sub-headers carry capability vocabulary, not surface-entity vocabulary (no `### POST /auth/register`, no `### /login page`)
- [ ] Every item has `id`, `given`, `when`, `then` (in that order); `notes` only when needed
- [ ] Item IDs are unique across the file and follow `<SURFACE>-<CAPABILITY>-<NN>` (no feature ID prefix)
- [ ] No item's `then` exceeds ~5 bullets without a clear justification; none exceed 10
- [ ] No bullet smuggles multiple observations via "and" conjunctions
- [ ] Every item is testable with this feature + its PRD Section 8 dependency closure implemented. No item's behavior verification depends on a feature outside that closure (downstream consumers AND siblings included). Test setup that would naturally need outside infrastructure is satisfied via the Preparation Pattern, not by referencing the outside feature directly.
- [ ] No anti-pattern from `references/contract-template.md` § "Anti-patterns to refuse" is present (no `then` that restates `when`, no per-class items, no operational setup leaking into `given`, no "test passes" / "function is called" bullets, no manifest row with empty "Covered by", no fixture reference without a Prerequisites declaration)

**Hard coverage gate:** before saving, verify that every **in-scope** PRD Section 9 acceptance criterion for this feature (i.e., every AC that survived the cross-feature filter in Step 4.3) appears in the Coverage Manifest with at least one covering item ID. If any in-scope AC has zero coverage, abort and save NOTHING (no spec, no plan, no contract). Print:

```
ERROR: contract coverage gap for F<ID>. The following in-scope PRD Section 9 acceptance
criteria have no covering item:
  - "<verbatim AC text>"
  - "<verbatim AC text>"
Either generate covering items, or revise the PRD/spec if the AC is no longer
applicable to this feature.
```

Aborting all three files (not only the contract) keeps the feature folder consistent.

**Save all three files to `docs/<feature-id>-<kebab-name>/spec.md`, `plan.md`, and `contract.md`.** Create the folder if it doesn't exist. Verify all three files with the Read tool.

### Step 6: Issue Creation (optional)

After Step 5 saves the three files successfully, decide whether to open a GitHub tracking issue for this feature.

**6.1 — Decide whether to create.**

- If `create-issue` flag was present in the input → proceed to 6.2 without prompting.
- If absent (single-feature mode) → ask the user: `"Create a GitHub issue for F<ID> <Feature Name>? (y/n)"`. Proceed to 6.2 only on `y` / `yes` / `sim`. Any other answer (or `n`) skips creation entirely; jump to Step 7.
- If absent (Batch Mode) → the orchestrator already asked once in B.4 and propagated the decision. Sub-agent treats the absence-here as "don't create" because the orchestrator only forwards `create-issue` when the user opted in. Skip to Step 7.

**6.2 — Detect existing open issue.**

Search GitHub for an existing open issue whose title starts with `[F<ID>]`:

```
gh issue list --search "[F<ID>] in:title" --state open --json number,url --limit 5
```

- **One open match** → skip creation. Record the existing URL for Step 7's output.
- **Multiple open matches** → use the first; log under `Soft-fails`: `"multiple open issues with [F<ID>] prefix; reporting only #<first-number>"`.
- **Only closed matches OR no matches** → proceed to 6.3 (create new). A closed issue means the prior cycle of this feature already shipped; the new spec deserves a fresh issue.

**6.3 — Build title and body.**

Sources for the placeholders (mirror the orchestrator's PR-body discipline — no double-reading):

- **`<Feature Name>`** — from the PRD Section 6 entry already loaded in Step 1.5; otherwise derive from the feature folder name (`F<ID>-<kebab>` → strip prefix, replace hyphens with spaces, title-case).
- **`<verbatim AC text>`** — the per-feature acceptance criteria from PRD Section 9 (already loaded in Step 1.5).
- **`<dependencies>`** — from PRD Section 8's dependency table for this feature (already loaded in Step 1.5).
- **`<wave>` / `<priority>`** — from PRD Section 8 (same row).
- **`<2–3 sentence summary>`** — first 1–2 sentences of `Capabilities` plus, if needed, one sentence of `Experience`, from PRD Section 6.

Title:
```
[F<ID>] <Feature Name>
```

Body template:

````markdown
## Summary

Implements **F<ID>: <Feature Name>**.

<2–3 sentence summary derived from PRD Capabilities + Experience>

## Acceptance Criteria

- [ ] <verbatim AC text from PRD Section 9>
- [ ] <verbatim AC text from PRD Section 9>
...

## Dependencies

- F<dep-ID>: <dep name>
- ...

(or "None" if no dependencies)

## Wave & Priority

- Wave: <N>
- Priority: <1|2|3>

## Documents

- Spec: `docs/F<ID>-<name>/spec.md`
- Plan: `docs/F<ID>-<name>/plan.md`
- Contract: `docs/F<ID>-<name>/contract.md`
- PRD section: `docs/PRD.md` § F<ID>

---

🤖 Auto-generated. Every acceptance criterion above will be verified end-to-end against the contract.
````

**6.4 — Create the issue.**

```
gh issue create --title "<title>" --body "$(cat <<'EOF'
<body content>
EOF
)"
```

Capture the returned issue URL. Do NOT add labels, assignees, milestones, or projects — none are set by default. Teams that want them configure GitHub repo defaults or apply manually after creation.

**6.5 — Failure handling.** If `gh` exits non-zero (auth, network, gh not installed, repo not connected), do NOT abort the run. The three files are already saved — that is the skill's primary deliverable. Record under `Soft-fails`: `"issue not created: <gh stderr excerpt>; run manually: gh issue create --title \"<title>\" --body-file <path-to-body>.md"`. Continue to Step 7.

### Step 7: Output Result

Inform the paths of the spec, plan, and contract files, the complexity level of the feature, the number of phases in the plan, and the count of contract items per surface (e.g., "Contract: 14 items across HTTP API (8), UI (4), E2E (2); 9/9 PRD ACs covered").

---

## Batch Mode

Generate specs for multiple features of the same wave in parallel, auto-accepting all interview recommendations. This mode is a thin orchestration wrapper on top of Steps 1–7: sub-agents run the full single-feature flow; the orchestrator only resolves input, validates, dispatches, and reports.

### Activation

The skill enters Batch Mode automatically when the input matches any of these shapes:
- Multiple feature IDs: `F01 F02 F03`
- Wave reference: `wave 3`
- Mix within the same wave: `wave 3 F04`
- Multiple feature names, or names mixed with IDs, as long as all resolve to the same wave

Single-feature input (e.g., `F03`, `Video Upload`) continues to use the interactive flow (Steps 1–7).

### Same-wave rule

All features in a single batch must belong to the same wave (per PRD Section 8).

- Cross-wave input (e.g., `wave 3 wave 4`, or `F04 F05` where F04 is wave 3 and F05 is wave 4) is rejected. Message: "Features from different waves cannot be generated in the same batch. Later-wave specs are richer when generated after earlier waves are implemented, so the codebase has more patterns to observe. Run wave N first."
- Mixing `wave N` with extra feature names/IDs is allowed only if every listed feature belongs to wave N. Any outlier triggers the same rejection.
- Unknown wave number → reject, listing available waves from Section 8.
- Unknown feature ID/name → reject, listing available features.

### Orchestration flow

Step 1 (Resolve Input and Pre-Analysis) is adapted for the batch context as described below. Steps 2–7 are NOT executed by the orchestrator — they run inside each sub-agent, one per feature, per the Auto-Accept Policy.

**B.1: Resolve the batch**

- **Locate the PRD** using Step 1.1 rules (user-provided path, `docs/PRD.md`, `PRD.md`, or similar). If no PRD is found, stop and direct the user to `prd-writer`. If multiple plausible PRDs exist, ask the user which one BEFORE continuing — this is the first possible interactive pause in the orchestrator.
- Parse input into a list of target features (expand waves, merge lists, deduplicate).
- If the PRD has no `Execution Waves` subsection in Section 8 and the input references a wave (e.g., `wave 3`), reject with: "Wave references require a 'Execution Waves' subsection in Section 8 of the PRD, which this PRD does not have. Use feature IDs directly or update the PRD." Do not attempt to synthesize waves.
- If any feature name in the input is ambiguous (matches multiple features in the PRD, e.g., "upload" matches F03 and F11), list the candidates to the user and ask for disambiguation BEFORE proceeding to the rest of B.1. This is the second possible interactive pause before the consolidated plan.
- If any feature ID or name does not exist in the PRD, reject with the list of available features.
- Validate the same-wave rule.
- For each target, check whether `docs/<feature-id>-<kebab-name>/spec.md`, `plan.md`, or `contract.md` already exists. Mark such features as "already has spec/plan/contract" (treated as a unit — the three files share lifecycle).

**B.2: Greenfield and Foundation classification**

Apply the Foundation state detection from Step 1.2 once for the whole batch. Classify each target feature as:
- **Foundation, not implemented** → must run sequentially (shared scaffolding prevents parallelism).
- **Non-Foundation, or Foundation already implemented** → eligible for the parallel pool.

**B.3: Dependency readiness**

For each target feature, check its PRD dependencies (Section 8). If a dependency is not implemented AND is not itself in the current batch, mark the feature as "dependency missing — will abort". Dependencies satisfied by other features in the same batch are acceptable (they'll be spec'd together; implementation order is the user's decision).

**B.4: Present consolidated plan and await confirmation**

Show the plan and await explicit confirmation. Default template:

```
Batch plan for <input>:
- F04 Video Library (Core only) — new
- F07 Background Processing Pipeline (full scope) — already has spec (skip / regenerate?)
- F12 Administration Panel (full scope — no Core/Full split) — new

Mode: parallel (N sub-agents)   # or "sequential (Foundation detected)" when applicable
Codebase state: Foundation complete   # or greenfield / Partial Foundation
Auto-accept: all spec-writer recommendations will be applied
Destination: docs/F04-video-library/, docs/F07-background-processing-pipeline/, docs/F12-administration-panel/

OK to proceed? (yes/no)
```

Per-feature scope tag (choose the right one per PRD shape):
- `(Core only)` — feature PRD has both `Core Scope` and `Full Scope additions` blocks (Auto-Accept picks Core).
- `(full scope)` — feature PRD has only one of the scope blocks, so Core and Full are the same.
- `(full scope — no Core/Full split)` — feature PRD has neither block; entire feature is in scope.

Per-feature status tags: `new`, `already has spec (skip / regenerate?)`, `dependency missing — will abort`, `Foundation, will run sequentially`, `already implemented (Foundation), skipping`.

Proceed only on explicit "yes". On "no" or any negative/ambiguous response, abort cleanly without dispatching sub-agents and without creating any files. If the user wants to change the plan, they re-invoke the skill with updated input. Features marked "already has spec" are skipped by default; the user can request regeneration in the confirmation response (e.g., "yes, regenerate F07").

**Issue creation prompt (only when `create-issue` flag was NOT in the batch input):** after the user answers "yes" to the consolidated plan above, ask one additional question: `"Also create a GitHub issue per feature in this batch? (y/n)"`. The answer applies to **every** feature in the batch — sub-agents do not ask individually. Record the answer:
- `y` / `yes` / `sim` → set the flag `create-issue` and forward it to every sub-agent prompt in B.5.
- anything else → do not forward; sub-agents skip Step 6 issue creation.

If `create-issue` was already in the batch input, skip this prompt and forward the flag to every sub-agent unconditionally.

**B.5: Dispatch sub-agents**

- **Sequential phase (Foundations only, when greenfield or Partial Foundation):** dispatch Foundation sub-agents one at a time, waiting for each to complete before starting the next, in the order they appear in PRD Section 8.
- **Parallel phase:** dispatch all remaining sub-agents in a single message with multiple Agent tool calls, no concurrency cap.
- Each sub-agent prompt includes:
  - The target feature ID and the PRD path
  - Instruction to execute Steps 1–7 of this SKILL.md for that feature
  - The Auto-Accept Policy below, replacing the interactive interview (Step 2)
  - Reminder to save `spec.md`, `plan.md`, and `contract.md` per Step 5, and to enforce the contract hard coverage gate (abort all three on gap)

Each sub-agent performs its own Pattern Discovery (Step 1.3) independently — no sharing between sub-agents.

**B.6: Collect and report**

Wait for all sub-agents. Report consolidated result:

```
Batch complete: 3/4 features generated successfully
✓ F04 → docs/F04-video-library/
✓ F07 → docs/F07-background-processing-pipeline/
✓ F12 → docs/F12-administration-panel/
✗ F05 → failed: <reason>
```

Sub-agent failures are isolated — other sub-agents continue. Failed features can be re-run individually.

### Auto-Accept Policy

Each sub-agent skips the interactive interview (Step 2) and applies these defaults for the decisions the interview would have surfaced:

| Decision | Default |
|---|---|
| Scope (Core vs Core+Full, when both blocks exist) | Core only |
| Technical decisions with a clear recommendation from spec-writer | Apply the recommendation |
| Dependency not yet implemented (Step 1.2 warning) | Orchestrator handles in B.3 — sub-agent never receives a feature with an unmet external dependency; skip the Step 1.2 warning entirely |
| Greenfield Foundation warnings (Step 1.2 Scenarios 2/3) | Orchestrator handles in B.2 — sub-agent skips these scenarios |
| Feature requires new technology not present in the codebase | Auto-confirm; document the new dependency in the spec's decisions/assumptions |
| Multiple conflicting patterns in the codebase | Pick the most frequent (or most recent when tied); document the choice |
| Ambiguous feature reference | Cannot occur — orchestrator asks the user to disambiguate in B.1 before dispatch |
| Empty codebase bootstrap (Step 1.4) | Fall back to industry best practices for the detected stack; document assumptions explicitly |
| Partial PRD specifications (Step 2 — capability mentioned but a technical detail omitted, e.g., "chunked upload" without chunk size) | Apply an industry-standard default for the missing detail; document it as an explicit assumption in the spec. Do NOT block. |
| Description too vague (feature definition leaves many decisions open) | Apply best-practice defaults for each open decision and document them as explicit assumptions in the spec; never silently infer |
| No codebase patterns found (codebase non-empty but Pattern Discovery returned nothing) | Fall back to industry best practices for the detected stack; document as an explicit assumption |
| Contract surface set ambiguous (PRD does not clearly indicate HTTP vs UI vs both) | Emit every surface with at least one PRD signal (Capabilities, Experience, Provides); document the choice under Assumptions |
| Quality gates clarification (Step 2 — detected gates) | Auto-include every detected gate without asking; document the list under Assumptions so the user can review and override later. Do NOT block. |
| Quality gates clarification (Step 2 — no gates detected) | Omit the `## Quality gates` section entirely; document the absence under Assumptions ("no quality gates detected in the project; section omitted"). Do NOT block. |
| Issue creation (Step 6 — `create-issue` flag absent) | The orchestrator already resolved this in B.4 (asked once, propagated to every sub-agent). Sub-agent treats absence-here as "do not create"; the orchestrator only forwards `create-issue` when the user opted in at B.4. Do NOT prompt; do NOT create silently. |
| Issue creation (Step 6 — `create-issue` flag present, forwarded by orchestrator) | Create the issue per Step 6 without prompting. On `gh` failure, log under `Soft-fails` (mirror the failure-mode rule from Step 6.5); do NOT block the sub-agent's success. |
| Contract coverage gate failure in Batch Mode | Sub-agent fails the feature (no files saved). Reported back to orchestrator like any other failure (B.6) so the user can investigate |

All other spec-writer rules (PRD-driven content, codebase pattern adherence, SPEC/PLAN validation, kebab-case naming, file structure) apply unchanged.

**Documentation requirement:** every time a sub-agent applies an Auto-Accept default for a decision the PRD did not answer, it MUST record that decision under an "Assumptions" or "Decisions" subsection of the spec, so the user can review and correct later.

---

## Rules

**Precedence:** When a feature is running in Batch Mode, the `(Batch Mode)` rule groups below override any conflicting rule in the general `Always`/`Never` lists — notably, Batch Mode overrides the interview-related rules ("Preserve the iterative interview style", "Skip interview questions...", etc.). All non-conflicting rules still apply.

**Always:**
- Generate THREE files (spec, plan, contract) in `docs/<feature-id>-<kebab-name>/`
- Validate all three documents before saving
- Run Codebase Pattern Discovery in two layers (baseline + broad) before the interview
- Read the target feature from the PRD and use Consumes/Provides/Core Scope/Full Scope/Capabilities/Experience/Error Handling/acceptance criteria as primary context
- Skip interview questions whose answers are already in the PRD, the codebase, or previous specs
- Apply the PRD → SPEC mapping consistently across all features
- Preserve the iterative interview style: one question at a time, walk down the decision tree, provide a recommended answer
- Build the contract Coverage Manifest from in-scope PRD Section 9 acceptance criteria, using verbatim AC text as the row key
- Filter out PRD Section 9 ACs whose verification falls outside the feature's spec.md `Included` scope; drop them silently from the manifest (no console warning, no items generated)
- Build the contract Prerequisites section as forward-looking conditions derived from the spec architecture and item references, with the **five fixed subsections** (Runtime services, Persistent state, Static inputs, Configuration, External dependencies). Frame these conditions so they read both as deliverables for the feature builder (produce them alongside the code) and as preconditions for whoever exercises the contract afterward — never as gates that block development before the feature is built
- Build the contract `## Quality gates` section (when gates were confirmed in Step 2's clarification turn) directly between `## Prerequisites` and `## Coverage Manifest`. Each entry is `- **<name>** — \`<command>\` — <description of what passing means>`. Keep the section consumer-agnostic: describe the gate, never the executor
- Reuse the project's discovered conventions captured in Step 1.3 (persistent-state seeding, static-input/fixture path, test config, mock) when generating Prerequisites — a path/mechanism declared by a prior contract or already present in the codebase is authoritative; never invent ad-hoc alternatives
- Keep `Persistent state` (entities, accounts, rows, messages, tokens — declared declaratively) strictly separate from `Static inputs` (files on disk at the project's fixture path)
- Ensure every handle referenced by any item (account name in `Persistent state`, file path in `Static inputs`) is declared in the corresponding subsection AND every declaration has at least one consuming item in its `Used by:` clause (no orphan declarations)
- Apply the contract hard coverage gate before saving: if any in-scope PRD Section 9 AC has zero covering items, abort all three files
- Bound contract Prerequisites by this feature's PRD Section 8 dependency closure: every declared resource (Persistent state, Static inputs, Configuration, Runtime services, External dependencies) is satisfiable from the feature itself or one of its declared dependencies. When an in-scope AC needs infrastructure that only a sibling feature outside the closure would normally produce, apply the **Preparation Pattern** (declare an F-internal stub/override/flag and require this feature to deliver it as part of its own scope) instead of referencing the sibling feature's real-world state
- Apply Step 6 (Issue Creation) according to the documented flag/prompt logic — when the `create-issue` flag is present, create the issue without prompting; when it is absent in interactive single-feature mode, ask once before creating; when it is absent in Batch Mode, treat absence as "do not create" (the orchestrator already resolved the question in B.4)
- Detect existing open issues via `gh issue list --search "[F<ID>] in:title" --state open --json number,url --limit 5` before creating a new one — if any match exists, skip creation and reuse the first match's URL in the spec-writer output
- Treat `gh` failures during Step 6 as soft-fails — record under the spec-writer's `Soft-fails` output and continue; the spec files are already saved at Step 5 and must not be rolled back

**Never:**
- Put actual code in spec (describe structure only)
- Put architecture decisions in plan
- Include time estimates
- Create testing phases in plan document
- Include Feature ID/Date/Version metadata
- Include implementation details in plan steps (data types, columns, methods)
- Proceed without a PRD — always require one and direct the user to `prd-writer` if absent
- Re-ask questions whose answers are observable in the codebase or already stated in the PRD
- Restrict codebase exploration to the baseline checklist — the baseline is a floor, not a ceiling
- Save the spec or plan when the contract coverage gate fails — all three are saved together or none
- Emit an "Acceptance test mapping" table (or any AC ↔ test row) in `spec.md`, or attach an "Acceptance criterion covered" column to any sub-table inside Testing Strategy — `contract.md`'s Coverage Manifest is the single source of truth for that linkage
- Annotate "OUT OF SCOPE for F<ID>" notes inside `spec.md` for cross-feature ACs — the cross-feature filter is encoded silently by the absence of those ACs from `contract.md`'s Coverage Manifest, and `spec.md` should not duplicate that signal
- Emit a `## Service` section in `contract.md` without a real consumer outside this feature
- Generate contract items per-class, per-VO, per-helper, per-test-file — items describe boundary behavior, not internal units
- Use surface-entity sub-headers in the contract (`### POST /auth/register`, `### /login page`) — capability vocabulary only
- Skip the `Verification mode:` line on any contract section
- Hand-edit `contract.md` after generation — regeneration is wholesale
- Generate items whose behavior depends on a feature OUTSIDE this feature's PRD Section 8 dependency closure — whether downstream (a feature that depends on this one) or sibling (no edge in either direction). Items whose behavior is owned by another feature live in that feature's contract; items whose behavior is this feature's but whose test setup needs outside infrastructure use the Preparation Pattern instead.
- Print a console warning when a cross-feature AC is dropped — the drop is silent by design
- Describe Prerequisites as snapshots of existing state — they are forward-looking conditions that must hold before items can be exercised
- Mention "implementing agent", "evaluator", "evaluating agent", or any specific consumer in the generated `contract.md` — the contract is consumer-agnostic
- Use HTML comments (`<!-- ... -->`) anywhere in the generated `contract.md` — they break some markdown viewers; use an italic regeneration line below the title instead
- Reference a handle (account, session, row, file path) in any item's `given`/`when` without declaring it in the corresponding Prerequisites subsection (`Persistent state` or `Static inputs`)
- Conflate `Persistent state` with `Static inputs` — declare an account or row under `Static inputs`, or declare a file under `Persistent state`
- Write `Persistent state` entries operationally ("run this migration", "execute this seed") instead of declaratively ("alice exists with X attributes")
- Invent fixture paths in `Static inputs` when the project already has a discovered fixture path convention (or a prior contract that declared one) — reuse the existing convention
- Diverge from a project convention without documenting an explicit Assumption explaining why
- Declare a Prerequisite that requires a feature OUTSIDE this feature's PRD Section 8 dependency closure to be implemented (e.g., declaring `landing-returning-user` as a real authenticated user inside `Persistent state` when this feature does not depend on the auth feature). The fix is the **Preparation Pattern**: replace the prereq with an F-internal stub, override, or configuration knob that this feature itself delivers as part of its own scope, so the contract is exercisable when only this feature + its declared dependencies are implemented
- Confuse "preparation for a sibling feature" with "dependency on a sibling feature". A feature MAY build interfaces, hooks, and stubs that other features will later plug into (preparation) — that does NOT make those other features its dependencies, and Prerequisites must reflect that boundary

**Always (Batch Mode):**
- Validate the same-wave rule before dispatch; reject cross-wave batches
- Present a consolidated plan and await explicit confirmation before dispatching sub-agents
- Skip features whose `spec.md`, `plan.md`, AND `contract.md` all exist unless the user explicitly requests regeneration. If only one or two of the three are present, treat the feature as incomplete and regenerate the full set
- Run Foundation features sequentially when the codebase is greenfield or Partial Foundation
- Apply the Auto-Accept Policy inside each sub-agent instead of running the interactive interview

**Never (Batch Mode):**
- Mix features from different waves in the same batch
- Dispatch Foundation features in parallel when any Foundation is still unimplemented
- Cancel running sub-agents because another sub-agent failed
- Share a single Pattern Discovery across sub-agents — each runs its own

---

## Edge Cases

**Batch Mode precedence:** In Batch Mode, any edge case below that instructs the sub-agent to "ask the user", "confirm with the user", or "go deeper in the interview" is overridden by the corresponding row of the Auto-Accept Policy (Batch Mode section). Sub-agents never pause to ask; orchestrator-level edge cases ("Multiple PRD files", "Ambiguous feature reference", dependency warnings) are resolved once in B.1–B.3 before dispatch.

**No PRD found:** Stop and instruct the user to generate one first with `prd-writer`. Do not run the skill without a PRD.

**Feature not found in PRD:** List the available features from PRD Section 8 and ask the user which one was intended.

**Ambiguous feature reference:** If the user's input matches multiple features (e.g., "upload" matches F03 and F11), list the candidates and ask the user to disambiguate.

**Multiple PRD files in the project:** Ask the user which PRD to use.

**Dependency not yet implemented:** Warn the user (e.g., "F08 depends on F07, which is not yet implemented. Continue anyway?") and proceed only if confirmed. The spec can still be generated — implementation order is the user's decision.

**Empty/scaffolded-only codebase (first feature):** Skip Pattern Discovery and ask transversal stack questions inline in Step 2. Subsequent features will read the codebase instead.

**PRD has no Core Scope / Full Scope blocks for the feature:** Skip the scope question; assume full feature scope.

**PRD only has Core Scope (no Full Scope additions):** Assume scope = Core; do not ask.

**Description too vague:** If the PRD's feature definition is unusually thin and leaves many decisions open, go deeper in the interview — do not assume defaults silently.

**No codebase patterns found (but codebase non-empty):** Ask the user to confirm using industry best practices or provide a reference.

**Feature requires new technologies not present in the codebase:** List the new dependencies, ask the user to confirm, document in decisions.

**Multiple conflicting patterns in the codebase:** Present both, ask which to follow, document the choice.

**Sanitizing feature name to kebab-case:** lowercase the name, replace spaces with hyphens, strip characters outside `[a-z0-9-]`. Example: `F07. Background Video Processing Pipeline` → `F07-background-video-processing-pipeline`.

**Cross-wave batch input:** Reject with a message pointing to Section 8 of the PRD and explaining that waves run sequentially so the codebase accumulates patterns between waves. Do not auto-split into two batches — the user should run the earlier wave first, implement it, then run the next.

**Unknown wave reference:** List available waves from PRD Section 8 and ask the user to clarify.

**Batch contains a feature already spec'd:** The consolidated plan flags it as "already has spec"; default is skip. User can request regeneration explicitly in the confirmation response.

**Batch contains a feature whose external dependency is not implemented:** Mark the feature as "dependency missing — will abort" in the plan; generate specs for the remaining features and report the aborted one in the final result. Dependencies satisfied by another feature in the same batch do not count as missing.

**Batch with multiple Foundation features in a greenfield project:** Foundations run sequentially in the order they appear in PRD Section 8. The plan states this explicitly ("Mode: sequential (Foundation detected)"). Non-Foundation features in the same batch still run in parallel after the Foundations finish.

**Sub-agent failure in batch:** Other sub-agents continue to completion. Final report lists successes and failures with reasons. Failed features can be re-run individually or as a smaller batch.

**PRD without "Execution Waves" subsection in batch mode:** Wave references (`wave N`) require this subsection to expand into features. Reject with: "Wave references require a 'Execution Waves' subsection in Section 8 of the PRD. This PRD does not have one. Use feature IDs directly or update the PRD." Do not attempt to synthesize waves.

**User declines the consolidated plan (responds "no" at B.4):** Abort cleanly. No sub-agents dispatched, no files created, no partial state left behind. User re-invokes the skill with adjusted input.
