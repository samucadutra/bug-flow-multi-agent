---
name: implement-feature
description: Implements a feature autonomously based on its spec, plan, and behavior contract; commits one commit per phase, produces every contract Prerequisite as authored artifacts, and reports preliminary readiness against the contract's Coverage Manifest.
---

# Implement Feature

Autonomously implement a feature from its existing `spec.md` + `plan.md` + `contract.md` triple. The skill reads the feature's technical specification (structure), the behavior contract (boundary behavior + prerequisites), and the implementation plan (phase order). It writes code phase by phase, produces every author-time artifact the contract's Prerequisites declare (fixtures, seeds, migrations, config defaults), validates each phase, commits, and reports preliminary readiness for a downstream **contract evaluator** agent.

The skill **does not** verify contract items itself (that is the evaluator's job). It produces the artifacts so the contract is exercisable, and gives a readiness signal in its report.

## INPUT

Free-form. The skill figures out what was passed. Any combination works:

- A feature identifier: `F09`, `Video Upload`, or similar.
- A feature folder: `docs/F09-in-video-transcription-search/`, `./F09/`, etc.
- A file inside the feature folder: `docs/F09-in-video-transcription-search/spec.md`.
- A PRD path: `@docs/PRD.md`, `docs/PRD.md`, `@PRD.md`.
- An optional `progress-path=<path>` pointing at the project's `prd_progress.json`. If omitted, the skill searches up from CWD (max 4 levels) for the nearest one. See **PROGRESS TRACKING**.
- Extra natural-language instructions appended anywhere (see **Overrides**).

The skill only needs to locate three feature files and one reference source:

1. **`spec.md`, `plan.md`, and `contract.md`** for the target feature — all three live as siblings in the same folder, generated together by `spec-writer`. If the input points to a folder, look inside. If it points to a file, look in its parent folder. If it points to an ID or name, search under `docs/` for a folder matching `<ID>-*` or whose name kebab-cases to the given name.
2. **The PRD**. If explicitly passed, use it. Otherwise, auto-discover: `docs/PRD.md` → `PRD.md` → any top-level `*.md` whose content reads like a product spec. If none found, abort. If multiple are plausible, abort and list them. (The PRD is needed for context and for the dependency-graph pre-flight; it is **not** the source of acceptance-criteria verification — that role belongs to `contract.md`'s Coverage Manifest.)

## OUTPUT

- **Commits**: one per phase of `plan.md`, on the current branch (no branch creation, no branch switching). Additional commits may be produced by the contract-prerequisites walk-through if it remediates missing artifacts (Step 6.3).
- **Chat report** at the end:
  - **AC pass-through over the contract Coverage Manifest** — each in-scope AC marked `~` (preliminary readiness — full suite + prereqs green) or `✗` (blocked — failures upstream), with its covering item IDs. The section carries an explicit header that AC verification is canonical for the contract evaluator agent, not for this skill.
  - **Contract Prerequisites readiness** — each entry of Persistent state, Static inputs, and Configuration marked ✓ produced or ✗ missing.
  - **Phase status, Missing from spec, Regressions, Deviations, Soft-fails, Pre-existing failures, Overrides applied, Overrides ignored, Abort reason (if any)**.

No files are written besides code changes and commit objects. The chat report is ephemeral.

---

## EXECUTION STEPS

### Step 1: Resolve Input

Parse the entire input as free-form. Extract:

- **Feature reference**: the first token that resolves to a folder containing `spec.md` + `plan.md` + `contract.md`. Matches: ID patterns like `F\d+`, folder paths, file paths (parent folder = target), feature names (kebab-case + fuzzy match to folder names under `docs/`).
- **PRD reference**: an explicit `*.md` path prefixed with `@` or written literally; if it looks like a PRD (product spec content at the top), accept it. Otherwise auto-discover.
- **Extra instructions**: any remaining text that isn't a path/ID/name — treat as natural-language overrides (Step 3).

If resolution fails:

- Any of `spec.md`, `plan.md`, or `contract.md` missing in the resolved folder → abort: "`<missing-file>` missing in `<folder>`. Regenerate the feature triple via the `spec-writer` skill — the three files share a single lifecycle and the implementer requires all three."
- No PRD found → abort: "No PRD found. Pass the path explicitly."
- Multiple plausible PRDs → abort and list candidates.
- Ambiguous feature reference (multiple folders match) → abort and list candidates.

### Step 2: Load Context

Read in full:

- `spec.md` of the target feature — Component Overview, Data Model, API Contracts, Business Rules, UX Flows, Error Handling, Testing Strategy, Assumptions/Decisions. **`spec.md` is the canonical source for internal structure** (file paths, decomposition, schema, library choices, naming).
- `plan.md` — phases and steps in order.
- `contract.md` — read the full file. Extract three things:
  - **Coverage Manifest** — the table mapping verbatim PRD §9 AC text → covering item IDs (`API-UPLOAD-01`, `UI-UPLOAD-01`, etc.). This is the **single source of truth for in-scope ACs**. ACs that are absent from the manifest were silently filtered as cross-feature by the `spec-writer` and are out of scope for this run — they are not loaded, not reported, not tested.
  - **Prerequisites** — three subsections matter to this skill: `Persistent state`, `Static inputs`, `Configuration`. Each entry describes a forward-looking condition (e.g., "alice exists with email…", "fixture file at path X is a valid H.264 MP4…", "`MAX_VIDEO_BYTES` is set in the test config"). The implementer MUST produce author-time artifacts that make every entry true. The other two subsections (`Runtime services`, `External dependencies`) describe runtime/host conditions and are the **contract evaluator's** concern, not this skill's — load them for context only, do not act on them.
  - **Item bodies** (given/when/then per surface) — these are the **canonical source of boundary behavior**. Items dictate observable contracts: HTTP status codes, response body shape (field names, types, presence), persisted side-effects (DB rows, columns, values), filesystem side-effects, error codes, UI selectors / labels. Items do NOT dictate internal structure (file paths, class names, library choices). When `spec.md` and items disagree about the same observable behavior, **items win**; spec wins on structure. Record any such tie-break in `Deviations` for the report.

If `contract.md` has an empty or absent Coverage Manifest, abort the run before any implementation (see Step 4).

Do NOT explore the codebase eagerly. Open files lazily as each phase requires them.

### Step 3: Apply Overrides

Interpret extra instructions as natural-language overrides on the defaults:

| Default | Example overrides |
|---|---|
| Hard-fail retry limit = 3 | "no retry limit", "max 5 tries" |
| Fully autonomous | "pause between phases" — skill waits in chat for a reply containing `ok`, `continue`, `segue`, `yes`, or similar |
| 1 commit per phase | "single commit at the end", "no commits, just implement" |
| Run lint + typecheck + tests | "skip tests", "skip lint", "skip typecheck" |
| Implement all phases | "only phases 1 and 2", "skip phase 3" — phase positions are ordinal; labels like `A/B/C` map to `1/2/3` |
| Abort tests on external dep missing | "stub missing services", "assume empty response for missing APIs" — substitutes stubs **ONLY in test code**, never in production modules |

For each recognized override, record before/after for the final report's "Overrides applied" section.

**Immutable core (cannot be overridden):** the contract integration as a whole — loading `contract.md`, running the AC pass-through in 6.4, running the Contract Prerequisites walk-through in 6.3, and rendering the AC report with its "preliminary readiness — canonical AC verification = contract evaluator" header. Instructions that would disable any of these are logged under "Overrides ignored" with the reason.

Ambiguous or contradictory instructions → default wins; logged under "Overrides ignored" with "ambiguous, kept default".

### Step 4: Pre-flight Dependency Check

**4.1 — Contract sanity:**
- `contract.md` has a recognizable `## Coverage Manifest` section (heading match by shape) → proceed.
- Coverage Manifest is empty or absent → abort: "F<target>'s contract has no in-scope ACs to verify. Regenerate via `spec-writer` to fix the coverage gate."
- `contract.md` has no `## Prerequisites` section, or the section is malformed (no recognizable subsections) → abort with the same regeneration message. Prerequisites is the only mechanism telling the implementer which artifacts to produce; without it the run cannot honor its contract.

**4.2 — Feature dependencies:**
Locate the dependency content in the PRD semantically (typical headings: "Dependency Graph", "Dependencies"; typical shape: a table or list pairing each feature with its prerequisites). For each listed dependency of the target feature, verify it appears implemented in the codebase (look for the characteristic files described in that dependency's own `spec.md` Component Overview, or obvious source-level markers).

- Any dependency missing → **abort before any implementation**. Report: "F<target> depends on F<N>, which is not implemented yet."
- All dependencies present → proceed to Step 5.

If the PRD has no dependency content, skip 4.2 and proceed.

### Step 5: Execute Phases

For each phase of `plan.md`, in order:

**5.1 — Skip if already done**

Inspect the last ~20 commits on the current branch. If any commit message indicates this exact phase already ran (same feature ID + phase name or ordinal), skip the phase with status `— already committed` and move on. Detection is best-effort: match on feature ID plus normalized phase name or phase index.

**5.2 — Implement**

Before editing code for this phase, read three sources together:

1. **`spec.md` sections relevant to the phase** — Component Overview entries the phase produces, plus the matching API Contracts / Data Model / Error Handling slices. Spec is the canonical source for **internal structure**: file paths, decomposition, schema columns, library choices, internal naming.
2. **All contract items** (every item under every surface section of `contract.md`). Items are the canonical source for **boundary behavior**: status codes, response body shape, persisted side-effects, filesystem side-effects, error codes, UI labels. Reading all items every phase is intentional — items relevant to a phase are not pre-filtered. Surface codes (`SVC`, `API`, `UI`, `WRK`, `EVT`, `CLI`, `E2E`) signal which items are observably exercised by which kind of phase, but the implementer reads every item for context regardless.
3. **The phase's `plan.md` step description** — anchors what the phase is delivering.

Then edit/create files to fulfill the phase's steps, **honoring the tie-break rule**:

- **Items win on observable behavior.** When `spec.md` describes a response shape, status code, error code, or any other externally observable property and a contract item asserts something different about the same property, follow the item. Spec drift is a `spec-writer` bug, but the implementer must not propagate it; the contract evaluator will check the item, not the spec. Record every such tie-break under `Deviations` with the form "spec said X, item `<ID>` asserted Y, followed Y".
- **Spec wins on internal structure.** Items never dictate file paths, class names, internal data-model columns that aren't externally asserted, or library choices. When in doubt about whether a divergence is "observable" or "internal", ask: would the contract evaluator notice this from outside the system? If yes, items win; if no, spec wins.

**Produce contract Prerequisites alongside the code.** When a phase naturally produces an artifact that satisfies a Prerequisites entry (a migration that creates the `videos` table, a fixture that the items reference, a seed that creates `alice`, a config default for `VIDEO_STORAGE_DIR`), produce it as part of that phase's commit. Do not defer to Step 6.3 except as a last-resort remediation.

**What counts as "done" for a phase** — all of the following, not just "I wrote the code":

- Every file listed for this phase in spec.md's Component Overview exists and contains the described content.
- Every contract (API, schema, function signature) described for this phase matches what was written, **modulo the items-win tie-break above**.
- Validation in 5.3 passes (hard fails resolved).
- If the phase produces runtime behavior that isn't covered by unit tests (UI pages, server routes, migrations, CLI commands), actually exercise it before claiming done: run the dev server / build / migration / command against a local environment and confirm it behaves. If the environment can't be brought up in this run, log the runtime-check under `Soft-fails` — do NOT silently claim the phase is done.
- **For surfaces whose contract items can only be observed in-browser, the runtime exercise must be in-browser.** When the phase produces a surface covered by contract items with surface code `UI-*` or `E2E-*`, the runtime exercise above is discharged only by driving a real browser against the live surface — HTTP-only smoke (e.g., `curl`) does not satisfy it, because the items typically assert observables that exist only in the rendered page (DOM state, focus, computed styles, media element state, scroll position, in-page navigation effects). Pick whichever browser-driving tool the project already uses. If the tool, the dev server, or the page cannot be brought up in this run, the check is recorded as `✗ blocked` in Step 6.5 — never as a soft-fail.

Writing code without running it is not "done". Declaring completion without meeting the checklist above is a violation of the skill's contract.

Adapt when reality diverges from the spec (column named `pinned` in DB vs `isPinned` in spec, different component file name, slightly different path, structurally compatible types). Specs are never 100% faithful to reality — adaptation is expected. Record every adaptation in a `Deviations` list for the final report. Do NOT abort on minor divergences.

**Abort the entire run only on:**

- Dependency feature missing (usually caught in Step 4; if discovered mid-phase, abort here).
- Hard fail past the retry limit in Step 5.3 below.

Missing external dependencies needed only by *tests* (e.g., `OPENAI_API_KEY` unavailable) do NOT abort the run — they soft-fail the affected test. The implementation code that calls the service is still written.

**5.3 — Validate**

Discover validation commands at runtime: inspect `package.json` `scripts`, or for non-Node stacks inspect the equivalent (`Makefile`, `pyproject.toml`, `Cargo.toml`, `vitest.config.*`, `jest.config.*`). Run the available ones.

- **Hard fail** = non-zero exit from lint, typecheck, or unit tests, where the failure is attributable to code this run changed. Retry up to the configured limit (default 3). Each retry reads the error, adjusts the code, re-runs. After the limit, abort the whole run and go to Step 6.
- **Soft fail** = validation cannot execute in this environment (e2e requiring browser/server not present; integration test requiring an external credential not set; suite explicitly marked non-runnable; command not found). Skip, log under `Soft-fails`, proceed.
- **Pre-existing failure** = validation fails but the failure is not attributable to code this run changed (touched unrelated files, existed on the branch before this run). Log under `Pre-existing failures`, do NOT count against the retry budget, proceed.

Warnings without non-zero exit are never failures.

**5.4 — Commit**

If validation passed (all hard fails resolved; only soft fails and pre-existing failures remain), stage only the files this phase touched and commit with a message summarizing the phase. Match the project's commit style by inspecting the last ~10 commit messages. Fallback: `feat(F<ID>): <phase name>`.

Stage specific files only (no `git add -A` / `git add .`). Commit on the current branch. Do not skip hooks.

If an override disabled commits, skip this sub-step and keep working-tree changes.

**5.5 — Proceed**

Move to the next phase. A run-level abort (hard fail past retry limit, dependency missing mid-phase) stops execution and goes to Step 6 with whatever phases already committed.

### Step 6: Final Verification

After the last phase commits (or when the run aborted), run an independent verification pass over the whole feature before writing the report. This step exists because per-phase checks can miss regressions, and because AI commonly claims "done" when it isn't.

Perform all of the following — no step is optional:

**6.1 — Full-suite validation**

Run the full validation suite on the entire repo (not just touched files): lint, typecheck, and the complete test suite as defined by the project. Do NOT filter to files this run changed.

- If failures appear that weren't flagged per-phase → they count as **regressions**. Attempt to fix up to the retry limit (same as hard-fail policy). If still failing, do NOT declare success — status becomes `completed with regressions` and the failures are listed under `Regressions` in the report.
- Pre-existing failures already logged in Step 5.3 stay categorized as pre-existing; they do not become regressions.

**6.2 — Component Overview walk-through**

Read spec.md's Component Overview (or equivalent file-list section) and, for every file listed, verify: the file exists, its described role is visible in the content, and its contracts (exports, routes, schemas) match the spec within the adaptation rules of Step 5.2.

Any missing file, missing export, or missing contract → add to `Missing from spec` in the report. Do NOT claim success if this list is non-empty.

**6.3 — Contract Prerequisites walk-through**

For each entry under the three in-scope Prerequisites subsections of `contract.md` — `Persistent state`, `Static inputs`, and `Configuration` — verify that an author-time artifact in the repo makes the entry true. Apply Level-2 rigor: presence + lightweight intrinsic check using tools the contract already assumes are available on the host (those tools also appear under `Runtime services` / `External dependencies` of the same contract).

Per subsection:

- **`Persistent state`** — declarative entries describing entities/accounts/rows/sessions that must exist inside the system store (e.g., "alice exists with email `alice@example.com`, password `Pass1234`, active, with a valid session cookie"). Verify by parsing the project's seeding artifact (the seed/factory/migration convention captured in the spec's Assumptions/Decisions) and confirming an entry creates the declared handle with the declared attributes. **Never** check by booting the system and querying the DB — that crosses into the evaluator's runtime concern.
- **`Static inputs`** — file paths the items reference (e.g., `apps/backend/tests/fixtures/videos/sample-30s.mp4`). Verify the file exists at the declared path AND its intrinsic property holds:
  - File-on-disk existence is mandatory.
  - For media fixtures with a stated codec/duration/size profile, run the host tool the contract names (e.g., `ffprobe`/`ffmpeg`) and confirm the property. For "must be readable" cases, the tool succeeds; for "must be unreadable" inversions, the tool fails as expected.
  - For text/binary fixtures with a size or content shape, confirm by file metadata (size, byte sniff, extension).
  - For fixtures whose intrinsic property depends on a config value (e.g., `oversize.bin` size > `MAX_VIDEO_BYTES`), resolve the config value from the test config artifact and compare.
- **`Configuration`** — config keys and defaults the contract names (e.g., `VIDEO_STORAGE_DIR`, `MAX_VIDEO_BYTES`, `videomax_session` cookie name). Verify the key is present in the project's test-config artifact (`.env.example`, `.env.test`, framework-specific config block — whichever convention the spec's Assumptions document) with a value compatible with the contract's stated meaning.

For each entry, classify as one of:

- `✓ produced` — the artifact exists, the intrinsic check passed.
- `✗ missing` — the artifact is absent, OR the intrinsic check failed, OR the required host tool is not available.

When a `✗ missing` entry is fixable in this run (the artifact can be authored within the skill's reach using available tools), attempt remediation as a separate commit titled `chore(F<ID>): produce contract prerequisite — <handle>` and re-verify. If remediation succeeds, the entry flips to `✓ produced`. If remediation fails (no `ffmpeg`, no permission, etc.), keep `✗ missing` and add a one-line reason under `Missing prerequisites` in the report.

The other two Prerequisites subsections — `Runtime services` and `External dependencies` — are intentionally skipped here. They describe runtime/host conditions the **contract evaluator** is responsible for satisfying when it exercises items. The implementer neither verifies nor produces them.

**6.4 — AC pass-through over the contract Coverage Manifest**

This step is **not** a per-AC test runner. Canonical AC verification belongs to a downstream contract evaluator agent that exercises the contract's GWT items end-to-end. This skill's job here is to project a **preliminary readiness signal** so the user knows whether the run is in shape for the evaluator to take over.

For each AC row in `contract.md`'s Coverage Manifest:

- Read the verbatim AC text (column 1) and the covering item IDs (column 2).
- Compute a readiness mark from the upstream Step 6 results — never by running an AC-specific test:
  - `~ ready` — Step 6.1 (full suite) is green AND Step 6.3 (Contract Prerequisites walk-through, defined above) is green AND no `Missing from spec` entry (Step 6.2) overlaps a file the covering items would reference.
  - `✗ blocked` — any of the above is red.
- Render the AC line as: `<mark> <verbatim AC text> [<item IDs>]`.

ACs absent from the Coverage Manifest are absent from the report — they were filtered as cross-feature by `spec-writer` and are out of scope by design (no `—` line, no "out of scope" line, no mention).

**6.5 — Environment smoke check (when applicable)**

If the feature produces runtime surfaces that per-phase validation couldn't exercise (UI page, HTTP endpoint, migration, CLI command), do one final exercise of each against a local environment (dev server, ephemeral DB, etc.). A quick load-and-interact is enough — the goal is to catch things unit tests don't.

The kind of exercise required depends on the surface code carried by the items covering it:

- **HTTP / SVC / WRK / EVT / CLI surfaces** — exercise via the matching transport (HTTP client for `API`, direct invocation for `SVC`/`WRK`/`EVT`, shell for `CLI`). If the environment cannot be brought up in this run, log under `Soft-fails`.
- **`UI-*` and `E2E-*` surfaces** — the items assert observables that exist only in a rendered page (DOM state, focus, computed styles, media element state, scroll position, in-page navigation). The exercise MUST therefore drive a real browser against the live page using whichever browser-driving tool the project already uses; HTTP-only or `curl`-only smoke does NOT discharge the check. If the browser tool, the dev server, or the page cannot be brought up, the check is `✗ blocked` (NOT a soft-fail) and the affected `UI-*` / `E2E-*` items propagate as `✗ blocked` covering ACs in 6.4.

The browser-driven exercise must verify rendered state, not just clickability or DOM text. Media (`<img>`, `<video>`, thumbnails) must actually load — a broken-image icon is not acceptable. Overlays, menus, dropdowns, popovers, and dialogs must open fully inside the viewport, not be clipped by ancestor `overflow`, and not be hidden behind surrounding UI. Any clearly-broken render visible in a screenshot must be fixed within the retry budget. Visual issues count as hard-fails for retry purposes; only the inability to bring up the browser or dev server is `✗ blocked`.

Status interaction: a `Soft-fail` smoke check still permits `success`. A `✗ blocked` smoke check does not — it degrades the status to `incomplete` per 6.6.

**6.6 — Status decision**

The run's final status is determined by this step, not by whether phases committed:

- `success` — full suite green (6.1), every Component Overview item present (6.2), every AC in the Coverage Manifest marked `~ ready` (6.4), every Prerequisites entry `✓ produced` (6.3), every smoke check passed or honestly soft-failed (6.5). A `UI-*` / `E2E-*` smoke check that was skipped because the browser tool, dev server, or page could not be brought up is `✗ blocked` (per 6.5), not soft-fail — its presence prevents `success`.
- `completed with regressions` — phases committed but 6.1 uncovered failures that the skill couldn't resolve.
- `incomplete` — `Missing from spec` (6.2) is non-empty, OR `Missing prerequisites` (6.3) is non-empty after remediation, OR any AC in 6.4 marked `✗ blocked`.
- `aborted at phase <N>` — run stopped during Step 5 before reaching here.

Never report `success` when any of the checks above has an unresolved failure, even if every phase individually committed clean.

### Step 7: Final Report

Output the report to chat. Status comes from Step 6.6, never from "I think I finished":

```
Feature F<ID> — <name>

Status: success | completed with regressions | incomplete | aborted at phase <N>
Phases: <N> committed / <M> total
Branch: <current-branch>

Acceptance Criteria (preliminary readiness — canonical AC verification = contract evaluator):
~ <verbatim AC text> [<item IDs>]
✗ <verbatim AC text> [<item IDs>] — blocked: <one-line reason pointing to the upstream failure>
...

Contract Prerequisites (from Step 6.3):
Persistent state:
  ✓ <handle> — <one-line locator: which seed/factory/migration carries it>
  ✗ <handle> — <reason: artifact missing | seed parse failed | …>
Static inputs:
  ✓ <path> — <intrinsic check that passed, e.g., "ffprobe: H.264 + AAC, duration 18s">
  ✗ <path> — <reason: file missing | ffprobe failed | tool not on PATH | …>
Configuration:
  ✓ <key> — <where: .env.example | config/test.ts | …>
  ✗ <key> — <reason>

Missing from spec (from Step 6.2):
- <file/export/contract that the spec required and is missing>
...

Missing prerequisites (from Step 6.3, after remediation attempts):
- <handle or path>: <reason the artifact could not be produced>
...

Regressions (from Step 6.1):
- <test name> started failing during this run: <error>
...

Deviations:
- <what was adapted and why; include items-win tie-breaks: "spec said X, item <ID> asserted Y, followed Y">
...

Soft-fails:
- <what was skipped and why, including runtime smoke checks not exercised>
...

Pre-existing failures:
- <test name>: failed on entry to this run; left as-is
...

Overrides applied:
- Retry limit: 3 → unlimited
...

Overrides ignored:
- "<text>" (reason)
...

Abort reason (if status is aborted): <error>
```

If aborted, the report still lists whatever committed phases achieved and clearly marks which phase failed and why. If `completed with regressions` or `incomplete`, the report makes clear which checks failed so the user knows what to fix. The Acceptance Criteria header **must** carry the "preliminary readiness — canonical AC verification = contract evaluator" caveat verbatim — never present these marks as a verdict.

---

## PROGRESS TRACKING

This skill writes its own status transitions to a shared `prd_progress.json` file, scoped strictly to the target feature's entry. The file is the deterministic record of feature state across the `implement-feature` → `evaluator` → `fix-runner` pipeline. Schema is canonical in `prd-writer/SKILL.md`; this section only documents this skill's writes.

**Locating the file:**
- If the input contains `progress-path=<path>`, use it.
- Otherwise, search up from CWD (max 4 levels) for the nearest `prd_progress.json`.
- If not found, log a `Soft-fails` line "progress file not found, status not tracked" and proceed. The implementation work is never blocked by tracking.

**Scope rule:** never touch any feature's entry other than the target feature's. Never modify top-level fields (`schema_version`, `prd_path`, `generated_at`).

**Failure modes — silent continuation:**
- File not found, fails to parse, or feature ID missing as a key under `features` → log `Soft-fails`, skip the write.
- Atomic write fails (rename error, permission, etc.) → log `Soft-fails`, skip.

Every write is read → modify the target feature's entry only → atomic write (`.tmp` + rename) of the entire JSON. Timestamps are RFC 3339 UTC (`2026-05-02T14:30:00Z`).

**Write 1 — At the start of Step 5 (Execute Phases), after pre-flight checks pass:**

- `status` ← `"implementing"` (transient — marks "implement-feature is running NOW")
- `started_at` ← now (only if currently `null`; never overwrite)
- `updated_at` ← now
- `failure_reason` ← `null` (clear stale failure note from any prior cycle)
- `report_path` ← `null` (clear pointer to any prior eval-report — implementation invalidates the prior verdict)
- `completed_at` ← `null`
- `cycles`, `priority`, `wave`, `dependencies`, `name` — untouched.

**Write 2 — On a pre-phase abort (any abort during Steps 1–4, before Write 1 occurred):**

- `status` ← `"fail"`
- `failure_reason` ← short reason ≤200 chars, e.g., `"aborted pre-phase: spec.md missing in docs/F03-video-upload/"`
- `updated_at` ← now
- All other fields untouched.

**Write 3 — At the end of Step 7, conditioned on the Step 6.6 status:**

- `"aborted at phase <N>"` → write `status="fail"`, `failure_reason="aborted at phase <N>: <one-line reason ≤200 chars>"`, `updated_at=now`. Other fields untouched.
- `success`, `completed with regressions`, or `incomplete` → write `status="implemented"` (the implementation phase is done; the feature is now in the implement → evaluate → fix loop awaiting a terminal verdict from the evaluator), `updated_at=now`. Other fields untouched. The downstream `evaluator` will replace `implemented` with `done` (clean) or `fail` (terminal failure).

These three writes cover every termination path. If the skill crashes (process dies, kill signal) between Write 1 and Write 3, status stays at `"implementing"` — visible signal that something was running but didn't finish; the user/orchestrator can re-run; Write 1 of the next run will refresh `failure_reason`/`report_path`/`completed_at` and re-set `status` to `"implementing"`.

---

## RULES

**Always:**
- Require `spec.md` + `plan.md` + `contract.md` in the target folder; abort without any of the three.
- Treat `contract.md`'s Coverage Manifest as the single source of truth for the in-scope AC list. ACs absent from the manifest are out of scope and never appear in the report.
- Treat `contract.md` items as canonical for boundary behavior; treat `spec.md` as canonical for internal structure. Apply the items-win tie-break and log every tie-break under `Deviations`.
- Produce author-time artifacts that satisfy every `Persistent state`, `Static inputs`, and `Configuration` entry of the contract's Prerequisites. Inline within the natural phase whenever possible; remediate as a separate commit during Step 6.3 only when the natural phase missed it.
- Locate dependency content in the PRD semantically, never by fixed section number.
- Commit 1 per phase (default), staging only the files that phase touched. Step 6.3 prerequisite remediation commits are an exception: they are titled `chore(F<ID>): produce contract prerequisite — <handle>` and stage only the artifact file(s) added.
- Match the project's recent commit-message style.
- Adapt to minor spec/code divergences; log every adaptation under `Deviations`.
- Run validation after each phase; differentiate hard-fail (retry ≤ limit) from soft-fail (skip + log) from pre-existing failure (log, don't retry).
- Before claiming a phase is "done": confirm every file listed for that phase exists with the described content AND validation has passed. Writing code without running it is never "done".
- For phases that produce runtime surfaces (UI, HTTP route, migration, CLI), actually exercise them against a local environment before claiming done, or soft-fail the runtime check. For surfaces whose contract items carry the `UI-*` or `E2E-*` surface code, the exercise must be browser-driven against the live page (the items assert in-browser observables that an HTTP-only smoke cannot see); skipping is `✗ blocked`, never soft-fail. The browser exercise must also verify rendered state — broken thumbnails, clipped overlays, hidden menus, and similar render-time bugs are hard-fails to fix in this run.
- Execute Step 6 (Final Verification) in full before reporting — full-suite re-run, Component Overview walk-through, Contract Prerequisites walk-through, AC pass-through, environment smoke check (in that order).
- Derive the final status exclusively from Step 6.6. Report `success` only when every Step 6 check is green.
- Render the Acceptance Criteria report header with the verbatim caveat "preliminary readiness — canonical AC verification = contract evaluator". Never present `~` as a verdict.
- Perform the three writes to `prd_progress.json` defined in **PROGRESS TRACKING** when the file is locatable: Write 1 at the start of Step 5; Write 2 on any pre-phase abort; Write 3 conditioned on the Step 6.6 status. Modify only the target feature's entry; never touch others.

**Never:**
- Claim the run is `success` when Step 6 found regressions, missing-from-spec items, missing prerequisites, or any AC marked `✗ blocked` — even if every phase individually committed clean.
- Soft-fail the smoke check for a `UI-*` or `E2E-*` surface. The browser-driven exercise is mandatory; if it cannot run, the surface is `✗ blocked` and status degrades per 6.6.
- Substitute an HTTP-only check (`curl`, fetch script, integration test) for the browser-driven smoke of a `UI-*` / `E2E-*` surface.
- Skip Step 6 (Final Verification) or any of its sub-steps.
- Run AC-specific tests in Step 6.4 (the step is a pass-through over the Coverage Manifest, not a test runner).
- Verify contract Prerequisites by booting the system and querying it (Persistent state, Static inputs, Configuration are checked against author-time artifacts). Booting is the contract evaluator's job.
- Verify, satisfy, or comment on `Runtime services` and `External dependencies` Prerequisites — they are evaluator-side.
- Render `✓` on any AC line in 6.4 — readiness is `~`, not a verdict.
- Treat `spec.md` as authoritative when an item explicitly contradicts it about an externally observable property; follow the item and log the deviation.
- Render an "out of scope" line for ACs absent from the Coverage Manifest — silence is by design.
- Create or switch branches.
- Abort on name/path/type cosmetic divergences.
- Abort on external dependency missing for a test — soft-fail the test, keep implementing.
- Use `git add -A` or `git add .`.
- Skip git hooks.
- Count pre-existing test failures against the retry budget.
- Re-run phases already committed on the branch (detected by commit-message match).
- Insert service stubs in production modules — stubs are allowed only in test files.
- Explore the codebase upfront with a broad sweep — read files lazily as phases require.
- Declare a phase complete based only on "I wrote the files". The completion checklist in 5.2 must hold.

---

## Overrides

Free-form instructions at the end of the invocation override defaults. Examples:

- **Retry limit**: `no retry limit`, `max 5 tries`.
- **Autonomy**: `pause between phases` — waits for user reply (`ok`, `continue`, `segue`, `yes`, etc.) after each phase.
- **Commit strategy**: `no commits, just implement`; `single commit at the end`.
- **Validation**: `skip tests`, `skip lint`, `skip typecheck`.
- **Phase selection**: `only phases 1 and 2`, `skip phase 3` — phase positions are ordinal; labels `A/B/C` map to `1/2/3`.
- **External services**: `stub OpenAI`, `assume empty response for missing APIs` — stubs apply ONLY in test code; production modules keep the real call.

Unrecognized or contradictory overrides: default wins; logged under `Overrides ignored`.

**Immutable core**: the contract integration cannot be overridden — `contract.md` loading, AC pass-through over the Coverage Manifest, Contract Prerequisites walk-through, and the AC report header all stand regardless of overrides.

---

## Edge Cases

**No PRD found**: abort before starting.

**No spec.md, plan.md, or contract.md**: abort before starting with the regeneration message — the three files share a single lifecycle and the skill cannot run on a partial set.

**`contract.md` exists but Coverage Manifest is empty/absent**: abort at Step 4.1 with the regeneration message.

**`contract.md` exists but Prerequisites section is empty/absent**: abort at Step 4.1 — the implementer cannot honor a contract with no prerequisites declaration.

**Dependency feature not implemented**: abort at Step 4.2 with a clear message.

**Ambiguous feature reference**: list candidates, abort asking which.

**Working tree has unrelated changes at start**: proceed anyway — the skill is designed to be invokable anywhere (typically from a worktree). Commits stage only the specific files each phase touched.

**Phase name contains special characters**: fall back to `feat(F<ID>): implement phase <N>`.

**Re-invocation after a partial run**: Step 5.1 detects already-committed phases by commit-message match and skips them. Step 6.3 still runs and may produce a remediation commit if a Prerequisite was missed by the skipped phases. Uncommitted working-tree changes from a prior interrupted run stay as-is; the skill does not clean them up.

**Spec and contract item disagree about an observable property**: follow the item, log "spec said X, item `<ID>` asserted Y, followed Y" under `Deviations`. Do not pause to reconcile, do not edit `spec.md` to match — drift is a `spec-writer` bug, not an implementer concern.

**Spec describes an internal structure detail (file path, class name) that has no item counterpart**: follow the spec; the items-win rule applies only when both sources speak about the same property.

**Static input fixture cannot be produced** (e.g., `ffmpeg` not on PATH but the contract demands a valid H.264 file): mark the fixture `✗ missing` in 6.3 with the reason, list it under `Missing prerequisites`, and let the status decision degrade to `incomplete`. Do not abort the run.

**Persistent state seed cannot be authored** because the project's seeding convention isn't documented in `spec.md`'s Assumptions: log under `Soft-fails` ("seeding convention undocumented; cannot author seed for `<handle>`") and mark the entry `✗ missing`. Status degrades to `incomplete`.

**Configuration key already present in the project but with a value incompatible with the contract's stated meaning**: do not silently overwrite. Log under `Deviations`, propose the contract-aligned value as a default, and add the key under `Missing prerequisites` so the user reviews.

**Hard fail past the retry limit on a step that isn't part of any AC**: abort anyway — the skill cannot judge which failures are "acceptable". User can override with `skip tests` or similar.

**External tool emits warnings, not errors**: warnings are not failures. Only non-zero exit codes count.

**Override contradicts the core contract** (e.g., `simplify the spec, drop requirements`, `skip prereqs`, `ignore the contract`): ignore it, log under `Overrides ignored`, proceed with the full spec + contract. The contract integration is not opt-outable.

**Validation commands not discoverable**: if `package.json` / config files don't reveal lint/typecheck/test commands, log each missing command under `Soft-fails` and proceed.

**PRD has no dependency content**: skip Step 4.2 and proceed.

**Commit-message style is inconsistent in recent history**: fall back to `feat(F<ID>): <phase name>` (or `chore(F<ID>): produce contract prerequisite — <handle>` for 6.3 remediation commits).
