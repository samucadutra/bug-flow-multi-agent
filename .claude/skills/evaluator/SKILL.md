---
name: evaluator
description: Verifies a feature's implementation against its behavior contract by exercising every contract item directly (HTTP / browser / DB / filesystem) and producing a verdict-per-item, AC pass-through, and persisted timestamped report. Stack-agnostic and project-agnostic — discovers everything from the contract, project docs, and codebase.
---

# Evaluator

Verify that a feature's implementation honors its `contract.md`. The skill is the **canonical verdict** counterpart to any preliminary readiness signal an implementer might emit — it owns environment lifecycle, exercises every in-scope item end-to-end, and persists a timestamped audit report.

The skill is **stack-agnostic** and **independent**: it does not import or reference any other skill. The contract format is the only formal coupling, and the skill reads structured markdown via lenient sectional reading (no strict grammar parser).

**Read-only on the project except for the report file and this feature's entry in `prd_progress.json`.** Never modifies code, tests, fixtures, seeds, configs, contracts, specs, or plans. Never modifies any feature entry in `prd_progress.json` other than the target feature's. Never commits, pushes, or opens PRs.

## INPUT

Free-form. Resolve a feature folder containing a `contract.md` and produce a verdict report. Accepted shapes:

- Feature ID (`F03`, `F12`).
- Feature folder (`docs/F03-video-upload/`, `./F03/`).
- File inside the feature folder (`docs/F03-video-upload/contract.md`).
- Feature name kebab-cased or fuzzy (`video upload`, `Video Upload`).
- Optional `progress-path=<path>` pointing at the project's `prd_progress.json`. If omitted, the skill searches up from CWD (max 4 levels) for the nearest one. See **PROGRESS TRACKING**.

Optional natural-language overrides anywhere in the input:

- `only API`, `only API-UPLOAD-03`, `only API and E2E`, `skip UI`.
- `only failed-last-run` — re-run only items marked `FAIL` or `BLOCKED` in the most recent `eval-report-<ISO-timestamp>.md` for this feature.
- `keep env` — skip teardown; leave DB and tmpdir for manual inspection.
- `pause on first failure` — stop after the first FAIL.

If resolution fails:

- No `contract.md` found in the resolved folder → abort with the resolved path.
- Contract malformed (no `## Coverage Manifest` section, no `## Prerequisites` section, or items referenced in the manifest that do not appear under any surface section) → abort.
- Filter `only failed-last-run` with no prior report → abort with explanation.
- Filter selects zero items → abort.

## OUTPUT

Two artifacts per run:

1. **Chat report (compact)** — header + aggregated status + only the FAIL / `⊘` ACs and FAIL / BLOCKED items in detail + path to the file report.
2. **File report (complete)** at `<feature-folder>/eval-report-<ISO-timestamp>.md`. Sibling of `contract.md`. Not gitignored. Format pinned by `references/report-template.md`.
3. **Screenshots** (UI/E2E runs only) at `<feature-folder>/eval-screenshots-<ISO-timestamp>/`. Sibling of the report; referenced from item Evidence. Not gitignored.

No other files are written. No commits are produced. No code changes are made.

---

## EXECUTION STEPS

The skill prescribes the **structure** of a run (phases, ordering, abort conditions, marks, anti-scope). It is permissive about **tactics** (which command runs the migration, which tool drives the browser, etc.) — the model discovers and applies what fits the project. Do not enumerate exhaustive heuristics in code or comments; let discovery do its job.

### Step 1 — Resolve input

Parse the input as free-form. Identify:

- The target feature folder (must contain `contract.md`).
- Filter overrides (`only`, `skip`, `only failed-last-run`, `keep env`, `pause on first failure`).

Abort with a clear message on any resolution failure listed under INPUT.

### Step 2 — Discovery

Read what the project entrusts to the skill, in this priority order. **Higher layers win**; record which layer answered each decision so the report's Discovery section is auditable.

1. **Contract Prerequisites** (the `## Prerequisites` section of `contract.md`). Canonical for *what* the feature requires (Runtime services, Persistent state handles, Static input paths + intrinsic properties, Configuration keys, External dependencies).
2. **Project docs**: `CLAUDE.md` (root and any nested), `harness/` content, `README*`. Canonical for *how* the project wants the environment brought up, reset, and torn down — when the project documents it.
3. **`spec.md` sibling of `contract.md`** (when present): Assumptions / Decisions sections declare project conventions (seeding mechanism, fixture path, test config, ORM, etc.).
4. **Other contracts under `docs/F*-*/`**: paths and handles already declared by sibling features — authoritative for reuse.
5. **Stack inspection**: project manifests (`package.json`, `pyproject.toml`, `Gemfile`, `go.mod`, `Cargo.toml`, etc.), available scripts (in those manifests, `Makefile`, `Taskfile`, `justfile`), DB / ORM configs, container compose files, `.env*` files.
6. **Defaults per detected stack** — apply general-knowledge defaults for the stack the inspection identified.
7. **Abort with diagnostic** — list what was tried and where, suggest the right place to document (typically layer 2).

The skill is permissive about HOW to discover within a layer. It walks down until a usable answer is found.

What the skill needs to know after Step 2 (absent knowledge is recorded and informs pre-flight):

- **How to install project dependencies for the detected stack** (e.g., Node → `npm ci` with `npm install` as fallback; Python → `pip install -r requirements.txt` or `poetry install`; Go → `go mod download`; Rust → `cargo fetch`). Convention by stack first; project-specific overrides discovered from layer 2 (`CLAUDE.md`, `harness/`) or `package.json scripts.setup` win when present.
- How to create and drop an ephemeral database.
- How to run migrations against it.
- How to seed the Persistent state declared in the contract.
- How to start, health-check, and stop each service declared under `Runtime services`.
- How to reset state between items (the project's preferred mechanism, or a sensible default for the detected stack).
- Where Static inputs live and how to verify their intrinsic properties (tools the contract names — `ffprobe`, `file`, size checks, etc.).
- How to drive each surface declared in the contract (HTTP, UI, E2E, Service, CLI, Worker, Event).

### Step 3 — Pre-run cleanup

Before bringing anything up, scan for orphaned resources from previous evaluator runs and remove them. **Only remove resources whose names match the skill's marker** — never anything else.

**Marker definition (pinned).** `<feature-id>` is the leading `F<N>` segment of the feature folder name, lowercased and stripped of non-alphanumeric characters (e.g., folder `F03-video-upload` → `f03`). The skill MUST use this exact form in every marker — DB name, tmpdir path, lockfile path, report file references — so cleanup matches creation byte-for-byte across runs.

**Concurrent-run safety.** Before removing anything, scan candidate `processes.lock` files for live PIDs (any PID listed that responds to a `kill -0` signal is alive). **If any candidate lockfile has at least one live PID, abort the new run** with a message of the form: `concurrent evaluator run detected for <feature-id>: PID <N> alive in <lockfile>. Wait for it to finish or stop it, then re-run.` Do NOT remove that lockfile, its tmpdir, or any DB associated with its run-id — the live run owns them.

After the safety check passes:

- Databases: drop any DB whose name matches `eval_<feature-id>_*`.
- Tmpdirs: `rm -rf` any directory under `<os.tmpdir()>/evaluator-<feature-id>-*/`.
- Processes: scan `<os.tmpdir()>/evaluator-<feature-id>-*/processes.lock` files; kill listed PIDs that are still alive (best-effort — if a PID has been recycled to an unrelated process, skip rather than risk killing a stranger).

Log every removed resource in the report's "Pre-run cleanup" section. If cleanup itself errors (permission, lock), log a warning and proceed — orphans are not blockers.

### Step 4 — Bring-up and pre-flight

1. **Install project dependencies** using the command discovered in Step 2 (e.g., `npm ci`). The command is idempotent — fast on already-installed projects, slow only on a fresh clone. If install exits non-zero, abort the run with status `aborted at step 4` and the install command's stderr in the abort reason.
2. **Create ephemeral DB** named `eval_<feature-id>_<run-id>` (run-id = ISO timestamp normalized for filename safety; `<feature-id>` per the marker definition pinned in Step 3).
3. **Create tmpdir** at `<os.tmpdir()>/evaluator-<feature-id>-<run-id>/`. Create the lockfile `processes.lock` inside it.
4. **Run migrations** against the ephemeral DB.
5. **Seed Persistent state** declared in the contract.
6. **Start runtime services** declared under `Runtime services` (backend, web, queue, etc.). Health-check each before proceeding. Append PIDs to the lockfile.
7. **Pre-flight: verify every entry across the Prerequisites subsections present in the contract** against the live environment. Subsections absent from the contract are skipped (no entries to verify).

   - `Runtime services` — each entry's health endpoint or readiness signal returns success.
   - `Persistent state` — each declared handle exists with its declared attributes (query the DB).
   - `Static inputs` — each declared file path exists AND its intrinsic property holds (run the tool the contract names).
   - `Configuration` — each declared key is set in the running services with a value compatible with the contract's stated meaning.
   - `External dependencies` — each declared tool / library is on PATH or otherwise reachable; version check when the contract specifies.

   Each entry is classified `✓` (passed) or `✗` (failed; record the reason). A `✗` does not abort the run — it produces a `BLOCKED` mark for items consuming that prerequisite (resolved in Step 6). Pre-flight `✗` does **not** skip Step 5 (gates) — gates and prerequisites are orthogonal concerns.

   A declared prerequisite that no item references (no item's `given` / `when` / surface `Common given:` consumes the handle, path, or key) is an **orphan declaration** — a contract-authoring bug. Verify it normally; if `✗`, log it under "Soft-fails" with the note `<entry> declared but no item references it`. The outcome does not block any item; the line surfaces the contract drift for the author to fix.

If any of steps 1–6 fails to complete (install errors, migrations explode, a service refuses to come up after a reasonable wait, etc.), abort the run before Step 5. Report what completed up to the failure under "Abort reason".

### Step 5 — Quality gates

Runs **after** Step 4 (bring-up + pre-flight) finishes successfully, **before** any contract item executes. Reads the contract's `## Quality gates` section and executes each entry in document order.

**If the contract has no `## Quality gates` section, skip this step entirely.** No phase runs, no report section is rendered (it collapses to `*(none)*` per the template). The evaluator is agnostic to contract history — section presence is the only signal.

**When the section exists:**

1. Parse each entry. Each line under the section has the shape `- **<name>** — \`<command>\` — <description>`. The command between backticks is the literal shell command to execute. The name labels the entry in the report. The description is informational.

2. Execute each entry sequentially in document order. For each:
   - Run `<command>` in a shell rooted at the project root, with the **ephemeral environment** of the brought-up run injected (`DATABASE_URL` pointing at `eval_<feature-id>_<run-id>`, service URLs of the started runtime services, etc.). Static gates (lint, typecheck, architecture) ignore the injected vars; DB- or service-dependent gates use them to verify against the just-brought-up env.
   - Capture exit code, stdout, stderr.
   - Mark the entry `✓` (exit 0) or `✗` (exit non-zero).

3. **Fail-fast.** On the first `✗`, stop the gate phase immediately. Do not run remaining gate entries.

4. **On any gate failure:**
   - Run status: `fail (gate <name>)`.
   - All contract items are marked `BLOCKED — run aborted at gates: <name>` (the same vocabulary used for the service-death cascade in Step 6.9).
   - All Coverage Manifest ACs are marked `⊘ undetermined` (every covering item is BLOCKED).
   - Skip Step 6 (execute items) entirely.
   - Step 7 (tear-down) runs normally — env IS up at this point. If the user passed `keep env`, honor it (skip tear-down, print connection details so they can inspect the failing env).
   - Step 8 (report) writes the partial report: Discovery, Pre-run cleanup, Bring-up + pre-flight, Quality gates (with per-gate results up to and including the failure), Coverage Manifest (all ⊘), Items (all BLOCKED), Abort reason (with the failing gate's command, exit code, and a stderr excerpt).

5. **On all gates passing**, proceed to Step 6 normally.

The phase is **immutable**. There is no override to skip it. A run on a contract with `## Quality gates` will always run those gates after bring-up; a developer who wants to bypass them must remove the section from the contract (which is the wrong move — they should fix the gate). The discipline is intentional: a contract that declares quality gates is declaring the project's bar to ship; the evaluator enforces it.

### Step 6 — Execute items

Execute every selected item (after applying input filters) sequentially in **pyramid order**:

```
Service → HTTP API → CLI → Worker → Event → UI → E2E
```

Within a surface, follow the document order of the contract. Do not parallelize; do not shuffle.

For each item:

**6.1 — Selection check.** If the item was filtered out of this run, mark `SKIPPED` with the filter reason and skip to the next.

**6.2 — Subjective check.** If the item's `notes` declares it subjective (e.g., `subjective; manual review only`), mark `MANUAL` and skip exercise. Subjective verdict precedes prerequisite gating because a subjective item is never auto-verified — the state of its prerequisites is irrelevant to its outcome.

**6.3 — Prerequisite gating.** If any Prerequisite this item references (handles in `given`, paths in `when`, configs / tools per the surface's `Common given:`) is `✗` from pre-flight, mark `BLOCKED` with the failing prerequisite identified. Do not exercise.

**6.4 — Reset state.** Run the project's reset mechanism (whatever discovery found): typically truncate ephemeral tables and clear the contents of any filesystem locations the contract declares as "starts empty". After reset, ensure Persistent state is intact; re-seed only if the reset wiped it.

**6.5 — Translate `then` bullets.** Apply `references/assertion-patterns.md` (load lazily on first translation). Each bullet is one of:

- **Matches a recognized pattern** → mechanical translation, executed and recorded with `expected` / `observed`.
- **Does NOT match** → the model interprets the bullet, executes its interpretation, AND **flags the item with `*`**. The interpretation MUST be logged in the item's reasoning ("interpreted as: …") so a reader can audit.
- **Genuinely ambiguous** (no plausible interpretation) → mark the bullet un-verifiable; the item becomes `MANUAL` with `notes: phrasing not auto-verifiable: <quote>`.

**6.6 — Exercise.** Drive the surface using whatever the project provides (discovered in Step 2):

- HTTP API → discovered HTTP client against the running backend.
- UI → the project's idiomatic browser driver.
- E2E → the same browser driver + direct queries on the ephemeral DB.
- Service → invoke the project's runtime to call the named function / class (model figures out the import path from the contract item plus spec.md or codebase).
- CLI / Worker / Event → exec the binary, publish to the queue, or emit the event using the project's idioms.

If the skill cannot drive a surface (e.g., a `Worker` surface for a queue technology discovery did not recognize), mark each item in that surface `BLOCKED — no driver discovered for surface <name>` and continue with other surfaces.

**Visual baseline (UI / E2E only).** Driving the browser is not enough — the rendered state must also be sound. After each `when` that affects the DOM, define a **scope** = the elements named in the item's `then` bullets (their subtree) ∪ any element that became visible as a result of the action — overlays mounted as portals in `document.body`, dropdowns/menus/popovers nested locally inside the trigger's container, tooltips, dialogs, comboboxes, and similar floating surfaces. The mounting location does not matter; visibility-on-action does. When the action opens such a surface, the visual baseline MUST run **between opening the surface and any further click inside it** — open the surface, screenshot, run both passes against the open state, only then proceed to click an item or close. Reaching downstream state (navigation, mutation) is NOT evidence that the surface was visually valid; the open state must be inspected on its own. When the same trigger repeats across many cards/rows/cells, exercise at least one **boundary instance** (the lowest/rightmost visible row, or the one nearest a scroll/overflow edge) in addition to the first; clipping bugs almost always surface only at the periphery. Inside the scope, run two passes:

- **Mechanical (deterministic, no `*`):** media (`<img>`, `<video>`, `<picture>`, `background-image`) must have actually loaded — request 2xx AND `naturalWidth/Height > 0` (or `readyState >= HAVE_CURRENT_DATA` for video). A broken-image icon is not a valid placeholder unless the contract bullet explicitly asserts a fallback. Visible nodes must sit inside the viewport, not be clipped by an ancestor's `overflow`, and be hit-testable at their center via `elementFromPoint` (catches z-index/stacking bugs).
- **LLM-vision (flagged `*`):** take a screenshot of the affected viewport, look only at the scope, and report any clipping, overlap, broken render, layout collapse, or other visual anomaly the mechanical pass missed.

Each finding becomes a synthetic bullet on the item, recorded under Evidence with the screenshot path. Synthetic bullets behave like any contract bullet: failure → item FAIL → AC ✗. They are not transport errors and do not contribute to the service-death threshold.

**6.7 — Assert.** For each bullet, record `expected` (from the contract) and `observed` (from the exercise). Bullet PASS if observed satisfies expected; FAIL otherwise.

**6.8 — Verdict and reasoning.** Item PASS ⇔ every bullet PASS. Item FAIL ⇔ at least one bullet FAIL. For each `✗` bullet, generate a one-line narrative root-cause anchored in observable evidence (HTTP body, log line collected, DB query result, file system state, browser DOM excerpt). When evidence is insufficient to identify a cause, write `→ root cause: unable to determine; see raw evidence` rather than speculating.

**6.9 — Transient errors and service-death detection.** A *transport error* is a TCP- or process-level failure: connection refused, connection reset, request / socket timeout, browser or runtime process crash. **HTTP 4xx and 5xx responses are NOT transport errors** — they are honest item failures and never trigger this path.

A single item hitting a transport error → 1 retry. If still failing, record as `FAIL` with the exception in the failing bullet's `observed`.

**If three or more consecutive items fail with the same transport-error class** (same exception type / same connection failure family), treat it as a service death: attempt one restart of the service whose URL the failing items were targeting; if it does not come back healthy, abort the run. Mark remaining unexercised items `BLOCKED — run aborted at item <ID>: <service> died`.

**6.10 — `pause on first failure`.** When the override is active and an item is `FAIL`, write the partial report and stop. Run status: `aborted at item <ID>: pause-on-first-failure`. Mark remaining unexercised items `BLOCKED — run aborted at item <ID>: pause-on-first-failure`.

### Step 7 — Tear-down

Idempotent. After the last item or on any abort path, in this order:

1. Kill processes listed in `<tmpdir>/processes.lock`.
2. Drop the ephemeral DB (`eval_<feature-id>_<run-id>`).
3. `rm -rf` the tmpdir.

Each step is best-effort — log warnings on failure, do NOT crash the report. Orphans left behind are cleaned on the next run's Step 3.

If `keep env` is active, skip Step 6 entirely. Print the connection details (DB URL, service URLs, tmpdir path) so the user can inspect manually, plus the explicit cleanup command they can run themselves later.

### Step 8 — Report

Project the run's outcomes onto the Coverage Manifest and write both the chat summary and the file report.

**Coverage Manifest projection (tri-state per AC):**

- `✓ verified` — every covering item is `PASS`.
- `✗ failed` — at least one covering item is `FAIL`.
- `⊘ undetermined` — no `FAIL`, but at least one covering item is `BLOCKED`, `MANUAL`, or `SKIPPED` (filtered).

**Run status:**

- `clean` — every AC `✓`, no `BLOCKED`, no `MANUAL` pending, no abort.
- `fail` — at least one AC `✗`.
- `fail (gate <name>)` — Step 5 aborted because gate `<name>` exited non-zero. All ACs `⊘`, all items `BLOCKED — run aborted at gates: <name>`.
- `pending` — zero `✗` ACs but at least one `⊘` AC (and the run was not gate-aborted).
- `aborted at step <N>` — infra-level abort during Steps 1–4 (input resolution, discovery, pre-run cleanup, bring-up failure). Use the step number (e.g., `aborted at step 4`).
- `aborted at item <ID>: <reason>` — execution-level abort during Step 6 (service death, `pause on first failure`). Use the offending item ID and a short reason.

Write the file report following `references/report-template.md` (load lazily). Print the chat summary following the same template's compact projection. Both reference the same run-id.

**Defensive insight (informational only).** If ≥ 80 % of *executed* items (denominator excludes `BLOCKED`, `MANUAL`, and `SKIPPED`) fail with the same root-cause pattern (e.g., 404 on every HTTP item, "ENOENT" on every fixture access), add a single line to the chat header:

> Note: most items fail with `<pattern>`; implementation may not be in place.

Marks remain honest; the line does not change any verdict.

---

## PROGRESS TRACKING

This skill writes the canonical verdict for the target feature into a shared `prd_progress.json` file. The file is the deterministic record of feature state across the `implement-feature` → `evaluator` → `fix-runner` pipeline. Schema is canonical in `prd-writer/SKILL.md`; this section only documents this skill's writes.

**Locating the file:**
- If the input contains `progress-path=<path>`, use it.
- Otherwise, search up from CWD (max 4 levels) for the nearest `prd_progress.json`.
- If not found, log a "Soft-fails" line "progress file not found, status not tracked" in the report and proceed. The verdict, the chat report, and the file report are still produced normally.

**Scope rule:** never touch any feature's entry other than the target feature's. Never modify top-level fields (`schema_version`, `prd_path`, `generated_at`).

**Failure modes — silent continuation:**
- File not found, fails to parse, or feature ID missing as a key under `features` → log "Soft-fails", skip the write.
- Atomic write fails → log "Soft-fails", skip.

The write happens once per run, at the end of Step 8, after the file report has been written. Read → modify the target feature's entry only → atomic write (`.tmp` + rename) of the entire JSON. Timestamps are RFC 3339 UTC.

**Write — At the end of Step 8, branched on Run status:**

- **`clean`** (every AC `✓`, no abort) →
  - `status` ← `"done"`
  - `completed_at` ← now
  - `report_path` ← path to the just-written `eval-report-<ts>.md`
  - `failure_reason` ← `null` (clear any prior failure note)
  - `updated_at` ← now

- **`fail`** OR **`fail (gate <name>)`** OR any **`aborted-at-step-<N>`** OR **`aborted-at-item-<ID>`** →
  - `status` ← `"fail"`
  - `failure_reason` ← short summary ≤200 chars. Suggested templates:
    - `fail` → `"<N> contract item(s) failed; first: <ID> — <one-line reason>"`
    - `fail (gate <name>)` → `"gate <name> failed: <stderr excerpt>"`
    - `aborted-at-step-<N>` → `"evaluator aborted at step <N>: <reason>"`
    - `aborted-at-item-<ID>` → `"evaluator aborted at item <ID>: <reason>"`
  - `report_path` ← path to the just-written `eval-report-<ts>.md` (`null` only if the abort happened before the report could be written, e.g., gate-aborted runs still produce a partial report so this is rarely null).
  - `completed_at` ← unchanged.
  - `updated_at` ← now

- **`pending`** (no `✗` ACs, but `⊘` ACs present from `BLOCKED` / `MANUAL` / `SKIPPED`) →
  - `status` ← unchanged. The verdict is neither success nor terminal failure — typically the orchestrator will dispatch `fix-runner` next, then re-evaluate. Standalone, the user inspects the report and decides.
  - `report_path` ← path to the just-written `eval-report-<ts>.md` (so the user can navigate from `prd_progress.json` to the report describing what's blocked/manual).
  - `failure_reason` ← unchanged.
  - `updated_at` ← now

This single write covers every termination path. No write happens before Step 8 — the pre-flight, bring-up, and item execution are all "in flight" and their interim state is not surfaced in `prd_progress.json`.

---

## RULES

**Always:**

- Treat `contract.md` as the single source of truth for what to verify. Do not consult the spec, plan, or PRD for assertions.
- Run the gate phase (Step 5) after Step 4 (bring-up + pre-flight) succeeds, before any item execution, when the contract has a `## Quality gates` section. Execute each entry in document order, fail-fast on the first non-zero exit, and capture exit code + stderr per entry. Inject the ephemeral environment (`DATABASE_URL` and started service URLs) into the gate command's shell so DB- or service-dependent gates can validate against the brought-up env. Skip the phase silently when the section is absent.
- Run pre-flight on every Prerequisites entry declared in the contract (across whichever of the five subsections are present) before executing any item.
- Execute items sequentially in pyramid order: Service → HTTP API → CLI → Worker → Event → UI → E2E.
- Reset state between every item using the project's discovered reset mechanism.
- Translate `then` bullets via `references/assertion-patterns.md` mechanically when patterns match; flag the item with `*` and log interpretation when they do not.
- For UI/E2E items, run the visual baseline (Step 6.6) — DOM/click success is not enough on its own. A clipped overlay, a broken thumbnail, or a layout that visibly collapsed must FAIL the item even if every contract bullet would otherwise pass.
- Mark items as one of `PASS / FAIL / BLOCKED / MANUAL / SKIPPED`. Project ACs as `✓ / ✗ / ⊘`.
- Persist the report at `<feature-folder>/eval-report-<ISO-timestamp>.md` following `references/report-template.md`. The `<ISO-timestamp>` placeholder is the same run-id used in the DB name and tmpdir, byte-stable across all references.
- Clean up only resources whose names match the skill's markers (`eval_<feature-id>_*` for DBs, `evaluator-<feature-id>-*` for tmpdirs, PIDs in own lockfile). Never touch anything else.
- Tear-down is idempotent; orphans are cleaned by the next run's Step 3.
- When discovery exhausts every layer without an answer, abort with a diagnostic that lists what was tried and where to document.
- Write the verdict to `prd_progress.json` per **PROGRESS TRACKING** at the end of Step 8 (after the file report has been written), modifying only the target feature's entry. Skip the write silently with a "Soft-fails" line if the file is not locatable, unparseable, or the feature ID is absent.

**Never:**

- Modify project code, tests, fixtures, seeds, configs, contracts, specs, or plans. Read-only on the project except for the report file and the target feature's entry in `prd_progress.json`.
- Modify any feature entry in `prd_progress.json` other than the target feature's. Never modify top-level fields (`schema_version`, `prd_path`, `generated_at`).
- Create files the project lacks (a missing seed, a missing fixture, a missing test). Mark dependent items `BLOCKED` or `MANUAL` and report.
- Run the project's existing test suite as a substitute for direct execution of contract items. Items are exercised directly. (Quality gates declared in `## Quality gates` are a separate concern — they run in Step 5 because the contract declares them as preconditions, not as a substitute for item exercise.)
- Skip the gate phase via override. Step 5 is immutable when `## Quality gates` exists; there is no `skip gates` flag.
- Drop a database or `rm -rf` a directory whose name does not match the skill's own marker. Ever.
- Commit, push, or open PRs. Even the report file is not auto-committed.
- Mark an AC `✓` when any covering item is not `PASS`. Use `⊘` for partial coverage (BLOCKED / MANUAL / SKIPPED), `✗` for any FAIL.
- Mark a bullet PASS without recording the observed value. Every PASS and every FAIL has `expected` / `observed` evidence.
- Skip pre-flight to "save time". Pre-flight is immutable — overrides do not disable it.
- Continue the run after a service-death detection (3+ consecutive transport-error failures). Aborting is more honest than stamping FAIL on items that never ran cleanly.
- Speculate root cause when evidence is insufficient. Write `→ root cause: unable to determine; see raw evidence`.
- Hand-edit a generated report. Re-runs produce new timestamped files; old reports are immutable history.
- Resume a previous run. Each invocation is independent.
- Enumerate exhaustive stack-specific heuristics inline. Discovery is permissive; let the model figure tactics from the layer it lands on.

---

## OVERRIDES

Free-form natural-language flags appended to the input override defaults. Recognized:

| Override | Effect |
|---|---|
| `only <surface>` | Run only items in the named surface(s). Multiple surfaces allowed. |
| `only <ITEM-ID>` | Run only the named item(s). |
| `skip <surface>` | Skip the named surface(s). |
| `only failed-last-run` | Read the most recent `eval-report-<ISO-timestamp>.md` for this feature; re-run only items marked `FAIL` or `BLOCKED` (which includes items blocked by run-aborted-mid-Step-5 from the previous run). |
| `keep env` | Skip tear-down; print connection details and the explicit cleanup command. |
| `pause on first failure` | Stop after the first item `FAIL`. |

**Immutable core (cannot be overridden):**

- Quality gates phase (Step 5) when the contract has a `## Quality gates` section. Runs after bring-up + pre-flight, fail-fast on the first non-zero exit; the run skips item execution but still tears down (or honors `keep env`).
- Pre-flight on every Prerequisites entry declared in the contract.
- Tri-state AC projection.
- Report file generated at `<feature-folder>/eval-report-<ISO-timestamp>.md`.
- Anti-scope (no project mutations, no commits, marker-only cleanup).

Unrecognized or contradictory overrides: default wins; log under "Overrides ignored" in the report.

---

## EDGE CASES

- **Contract has no `## Quality gates` section.** Step 5 is skipped silently; the report's Quality gates section renders `*(none)*`. The evaluator does not warn, does not abort — the absence of the section is a valid contract shape.
- **Quality gate command not found / shell parse error.** Treat as exit non-zero: the entry is `✗`, fail-fast triggers, run aborts with `fail (gate <name>)`. The report captures the shell error in the gate's stderr field.
- **Implementation not in place.** Bring-up may succeed even when routes / views are missing — items then FAIL with 404 or similar. The defensive insight at the top of the chat report flags the pattern but does not change item marks.
- **Project documents nothing about evaluation.** Discovery layers 1, 3-5 still produce enough context for most stacks. When they do not, the run aborts with a diagnostic; the message points to layer 2 (`CLAUDE.md` / `harness/`) as the place to document.
- **Static input fixture missing or fails intrinsic check.** Pre-flight marks the entry `✗`; items consuming it become `BLOCKED`. The skill never creates the fixture.
- **Persistent state seed missing.** Same as above — `BLOCKED` items, no auto-creation.
- **Two concurrent evaluator runs on the same feature.** Each run creates a uniquely-named DB and tmpdir. Theoretically safe, but unsupported in practice — port collisions on services may occur. Document under "Soft-fails" if detected, and recommend serializing.
- **Contract with zero items.** Abort: malformed contract.
- **Filter selects zero items.** Abort with explanation.
- **`keep env` and run aborted.** Tear-down still skipped; user inspects the partial state. Document this clearly in the chat output.
- **Transport errors that aren't service death.** Single item retries once, then FAILs. Three-in-a-row → service-death detection.
- **Surface present in contract but unsupported by current discovery.** Mark each item in that surface `BLOCKED — no driver discovered for surface <name>` and continue with other surfaces.
- **Subjective items (`notes: subjective; manual review only`).** Always `MANUAL`, regardless of filter or environment.
- **Coverage Manifest references item IDs that do not appear under any surface section.** Treat as malformed contract; abort.
- **Item references a handle / path / config that is NOT declared in Prerequisites.** Treat as malformed contract; abort with the offending reference quoted.
- **`only failed-last-run` after a `clean` previous run.** No items qualify; abort with explanation ("previous run was clean; nothing to re-run").
- **`only failed-last-run` after an `aborted` previous run.** Items marked `FAIL` or `BLOCKED` qualify and are re-run — this includes items marked `BLOCKED — run aborted at item <ID>: ...` from the prior abort, since they were never honestly exercised. Items still marked `PASS` from before are not re-run. If no items qualify, abort with the same explanation as the `clean` case.
