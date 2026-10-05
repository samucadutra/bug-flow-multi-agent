---
name: fix-runner
description: Targeted corrective pass against a single feature. Use when (1) a contract-driven evaluation report (`eval-report-<ts>.md`) has failed items that need to be turned green — reads each item's expected/observed evidence and edits implementation, fixtures, seeds, tests, or configs to address them; or (2) a merge has produced conflicts in the working tree — resolves them, or if given a PR reference, fetches the PR's base branch, runs the merge itself, and resolves whatever conflicts surface. Validates via the project's quality gates and tests, then produces one commit per run (`fix(F<ID>): cycle <N> — …` for evaluation-driven runs, `merge: …` for conflict-resolution runs).
---

# Fix Runner

Targeted corrective pass for a single feature. Operates in one of two modes, selected automatically by the input shape:

- **Mode A — Fix evaluation failures.** Driven by an `eval-report-<ts>.md` listing failed items.
- **Mode B — Resolve merge conflicts (PR-aware).** Driven either by an in-progress merge already in the working tree, or by a PR reference (in which case the skill fetches the PR's base, runs the merge itself, and resolves whatever conflicts surface).

The skill does not re-run the per-phase implementation work that produced the feature, and does not verify item outcomes itself — the next evaluation cycle is the canonical verifier. Read-only on `contract.md`, `spec.md`, `plan.md`, prior `eval-report-*.md` history, and any sibling feature folders. Mutating only on production code, tests, fixtures, seeds, configs, and the commit object.

## INPUT

Free-form. Mode is selected by the input shape:

- `eval-report=` + `failed-items=` → **Mode A**.
- `pr=` or `conflicted-files=` → **Mode B**.
- Fields from both modes mixed → abort with the offending fields named.

### Mode A fields

- **feature** — feature ID (`F03`), folder, file inside the folder, or fuzzy name. Resolved to a folder containing `contract.md` + `spec.md` + `plan.md`.
- **eval-report** — path to the failing `eval-report-<ts>.md` file. Must exist and live inside the resolved feature folder.
- **failed-items** — comma- or whitespace-separated list of item IDs (`API-UPLOAD-03`, `UI-UPLOAD-01`, etc.). Required, non-empty.
- **cycle** — integer ≥ 1 identifying which retry cycle this is. Used in the commit message. Default 1 if absent.
- **progress-path** (optional) — path to the project's `prd_progress.json`. If omitted, search up from CWD (max 4 levels) for the nearest one. See **PROGRESS TRACKING**.

Examples:

```
feature=F03 eval-report=docs/F03-video-upload/eval-report-2026-05-01T14-22-33Z.md failed-items=API-UPLOAD-03,UI-UPLOAD-01 cycle=2
```

```
Fix F03. Eval report at docs/F03-video-upload/eval-report-2026-05-01T14-22-33Z.md. Items API-UPLOAD-03 and UI-UPLOAD-01 failed. Cycle 2.
```

### Mode B fields

- **feature** — same resolution as Mode A.
- **pr** (optional, mutually exclusive with `conflicted-files`) — `<URL|number|branch-name>`. When present, the skill fetches the PR's metadata via `gh pr view`, requires the current branch to equal the PR's head ref, runs `git merge` of the PR's base ref into the current branch, and resolves whatever conflicts surface. The PR's title and body are kept as context for resolution.
- **conflicted-files** (optional, mutually exclusive with `pr`; required when `pr` is absent) — comma- or whitespace-separated list of paths currently containing `<<<<<<<` / `=======` / `>>>>>>>` markers. Typically obtained via `git diff --name-only --diff-filter=U`.
- **cycle**, **progress-path** — same as Mode A.

Examples:

```
feature=F03 pr=42 cycle=2
```

```
feature=F03 conflicted-files=apps/web/lib/session.ts,apps/backend/src/main.ts cycle=2
```

If any required field for the selected mode is missing or unresolvable → abort naming the field.

## OUTPUT

- 0 or 1 commit on the current branch (commit only on success; on `gates-failed` the working tree stays dirty for inspection).
- **Chat report**:

```
Fix Runner — F<ID> cycle <N>

Status: fixed | gates-failed | aborted

Items targeted: <ID-1>, <ID-2>, ...        (Mode A)
PR: <ref> (<head> ← <base>)                 (Mode B with pr=)
Conflicted files: <list>                    (Mode B)
Files touched: <list>
Commit: <SHA> | (none)

Validation:
  Gates: ✓ | ✗ (attempt <N>/<budget>)
  Tests: ✓ | ✗ (attempt <N>/<budget>)

Soft-fails:
- <issue>

Abort reason (if any): <reason>
```

No files written besides code/tests/fixtures/seeds/configs. The chat report is ephemeral; the commit (when produced) is the durable artifact.

---

## EXECUTION STEPS

### Step 1 — Resolve input

Parse free-form input. Detect mode by the fields present (see **INPUT**). Validate fields for the detected mode and abort with a clear reason if anything is missing, unresolvable, or contradictory across modes.

### Step 2 — Load context (Mode A)

Read in full:

- **`contract.md`** — focus on the bodies of the items in `failed-items`. Items are canonical for boundary behavior the fix must satisfy (status codes, response shape, persisted side-effects, error codes, UI labels). Also read the surface section `Common given:` blocks for items in scope, and the `## Prerequisites` section (BLOCKED items typically reference one of its entries).
- **`spec.md`** — only sections that map to the targeted items: Component Overview entries the items reference, plus matching API Contracts / Data Model / Error Handling slices. Spec is canonical for **internal structure** (file paths, decomposition, naming).
- **The eval-report** at the supplied path — for each failed item ID extract:
  - the item's `**Verdict:**` (FAIL / BLOCKED — anything else is logged as a soft-fail and skipped);
  - each `✗` bullet's `expected` / `observed` and the `→ root cause:` narrative when present;
  - the `Evidence` block (collapsed `<details>`) — read it for HTTP bodies, DB query results, DOM excerpts that pin down the actual behavior.

Do not read `plan.md` — phases are not relevant to the fix-up flow. Do not read sibling feature folders.

### Step 3 — Diagnose (Mode A)

For each failed item, classify by surface (the heading inside `## Items` of the eval-report). The classification points the fix at the most likely layer:

| Surface | Most likely fix site |
|---|---|
| Service | use-case / domain logic — backend |
| HTTP API | route handler, DTO, validation, mapper, repository — backend |
| CLI | command entry — wherever the project hosts CLI |
| Worker | queue handler, job runner — backend |
| Event | listener, dispatcher — backend |
| UI | component, page, form, client — frontend |
| E2E | composition spanning UI + backend |

For BLOCKED items, the failure is usually a missing or malformed Prerequisite. Inspect which subsection it consumed (Persistent state / Static inputs / Configuration / Runtime services / External dependencies) and target that artifact:

- Missing seed / wrong seed attributes → edit the project's seed mechanism (`prisma/seed.*` or equivalent — discover from `spec.md` Assumptions).
- Missing or invalid fixture → write/repair under the path the contract names (typically `apps/backend/tests/fixtures/...`).
- Wrong config default → fix `.env.example` and/or test config.
- Schema drift → edit `prisma/schema.prisma` (note: applying the migration is interactive; see Step 5).

A FAIL with `expected 201 / observed 500` typically points at a runtime exception — read the error body in the Evidence block and trace it to the implementation. A FAIL with `expected 201 / observed 404` points at a missing route or wrong path.

### Step 4 — Edit (Mode A)

Apply the smallest set of edits that would plausibly satisfy the items, honoring `contract.md` items as canonical for observable behavior and `spec.md` for internal structure. When the spec contradicts an item about an externally observable property, follow the item.

**Project conventions are authoritative.** Before editing, honor the rules the project itself documents (in `CLAUDE.md`, `harness/`, `README*`, or any project-doc the project conventionally uses) about which layering rules, design systems, or coding standards apply to which artifact kinds. The fix-runner is project-agnostic — it follows whatever the project declares; it does not enumerate those rules.

**Tests** — only edit existing tests when they are asserting an outdated shape (e.g., a unit test fixed at an old response schema that the contract has since clarified). Do not add new tests in this skill — the canonical assertions live in `contract.md` items and are exercised by the next evaluation cycle.

**Migrations** — if a schema change is required, edit the project's schema source-of-truth (the file or DSL the project uses — discover from `spec.md` Assumptions or the project's docs). Do not run any interactive migration command that would block on user input; log a soft-fail naming the migration command the user (or caller) needs to run after this skill finishes.

### Step 5 — Validate

Run quality gates and tests. **Discover both commands from the project — do not hardcode them.**

- **Gates** — read the contract's `## Quality gates` section and execute every entry's literal command. If the contract has no `## Quality gates` section, fall back to whatever the project's docs (`CLAUDE.md`, `harness/`, `README*`) name as the gate runner; if nothing is declared anywhere, log a soft-fail "no gates declared in contract or project docs; skipping gate validation" and proceed to tests.
- **Tests** — discover the command from the project's manifests/scripts (`package.json`, `Makefile`, `Taskfile`, `pyproject.toml`, etc.).

**Internal retry budget: 3 attempts on red gates or red tests.** Each attempt: read the failure, adjust the edit, re-run. The budget is shared across gates and tests.

If the budget is exhausted with gates or tests still red:
- Status = `gates-failed`.
- No commit. Working tree stays dirty for inspection.
- Report what was tried.

If gates and tests are green within budget, proceed to commit.

**Pre-existing failures** (red on entry, not attributable to this run's edits) do not count against the budget. Log under `Soft-fails`. Proceed to commit if everything else is green.

### Step 6 — Commit

Stage **only the files this run touched**. Commit with:

```
fix(F<ID>): cycle <N> — address items <ID-1>, <ID-2>, ...
```

Match the project's recent commit-message style by inspecting the last ~10 commit messages (capitalization, scope conventions). Adjust the template if the project deviates.

Constraints: stage by filename only (never `git add -A` / `git add .`); do not skip hooks (`--no-verify`); do not amend prior commits; do not push; do not create or switch branches. One commit per invocation. If a commit hook fails, fix the underlying issue and re-stage; do not bypass.

### Step 7 — Report

Output the chat report shown in OUTPUT, populated with this run's actual values. Status:

- `fixed` — gates green, tests green, commit produced.
- `gates-failed` — internal budget exhausted with gates or tests red; no commit; working tree dirty.
- `aborted` — pre-flight failed or an EDGE CASE handler triggered an abort; working tree clean; no commit.

---

### Step 8 — Mode B (resolve merge conflicts)

When Step 1 detects Mode B, follow this flow instead of Steps 2–7.

**Initiate the merge if needed.** When `pr=<ref>` was provided:

1. Fetch PR metadata via `gh pr view <ref> --json baseRefName,headRefName,state,title,body,url`. Abort if `gh` is not authenticated, the PR doesn't exist, or its state isn't `OPEN`.
2. Verify the current branch equals the PR's `headRefName`. If not, abort with `"PR head is <X>; current branch is <Y> — refusing to switch branches"`.
3. Verify the working tree is clean. If dirty, abort with the offending paths in the reason.
4. `git fetch origin <baseRefName>` and `git merge origin/<baseRefName>`.
5. If the merge completed cleanly (no markers in the working tree), jump to **Commit** with the clean variant.

When `conflicted-files=<list>` was provided instead, verify `.git/MERGE_HEAD` exists and that every input path is currently in `git diff --name-only --diff-filter=U`. If the merge state doesn't match, abort describing the inconsistency.

**Load context.** Read `contract.md` items (focused on the surfaces the conflicted files belong to) and the relevant `spec.md` Component Overview / Architecture sections. Discover the canonical conflict set from `git diff --name-only --diff-filter=U` — this is authoritative; if `conflicted-files=` was provided and disagrees, soft-fail and proceed with the discovered set. Read each conflicted file with markers in place; read both sides of every `<<<<<<< / ======= / >>>>>>>` block. When `pr=` was used, the PR's title and body are part of this context — they describe the intent of the side coming in.

**Resolve.** For each conflicted file, edit to remove markers and produce a coherent merged version. Resolution rules, in order:

1. **Spec/contract intent wins.** When the two sides disagree about something the spec or contract pins down (a function signature, a route path, a schema column), follow whatever spec/contract say.
2. **Additive merges combine.** When both sides add to a list (imports, route definitions, schema fields) without overlapping entries, take the union — both additions, deduplicated.
3. **Conflicting changes to the same line:** prefer the side from the feature branch (the side this skill's caller is working on). Document the choice in the commit body.
4. **Genuinely irreconcilable** (incompatible intent, contract doesn't pin it down): abort with reason `"unresolvable conflict in <file>: <one-line description>"`. Do not produce a half-resolution.

**Project conventions are authoritative** — same rule as Mode A's Step 4. The merged result must be conformant by construction (architecture rules for backend artifacts, design-system rules for frontend artifacts, etc.), not retroactively patched after gates fail.

After resolving every file, `git add` each one.

**Validate** the same way as Step 5 (gates + tests with 3-attempt budget). If validation can't be made green within budget, report `gates-failed`; do not commit; merge stays in progress for human inspection.

**Commit.** Two variants:

- **Conflicts resolved:**
  ```
  merge: resolve conflicts from <base> into <head> (cycle <N>)

  Resolved files:
  - <path>
  - <path>
  ```
- **Clean PR merge** (no conflicts arose):
  ```
  merge: bring <base> into <head> (cycle <N>) — clean
  ```

For the clean variant, `git merge` already produced a default merge commit before this step ran — adjust its message to the form above (e.g., `git commit --amend`).

**Report** the same chat shape as Step 7, with `Items targeted` replaced by `Conflicted files: <list>` (and the optional `PR:` line when `pr=` was used). `fixed` means the merge was completed and committed.

---

## PROGRESS TRACKING

This skill increments the `cycles` counter in a shared `prd_progress.json` file each time it runs, scoped to the target feature's entry. The file's schema is documented alongside its producer; this section only describes this skill's writes.

**Locating the file:**
- If the input contains `progress-path=<path>`, use it.
- Otherwise, search up from CWD (max 4 levels) for the nearest `prd_progress.json`.
- If not found, log a `Soft-fails` line "progress file not found, cycles not tracked" and proceed. The fix work is never blocked on this.

**Scope rule:** never touch any feature's entry other than the target feature's. Never modify top-level fields (`schema_version`, `prd_path`, `generated_at`). Never modify `status` — that field is written by other steps in the workflow; this skill is status-neutral.

**Failure modes — silent continuation:**
- File not found, fails to parse, or feature ID missing as a key under `features` → log `Soft-fails`, skip the write.
- Atomic write fails → log `Soft-fails`, skip.

**Write — once per run, after Step 1 succeeds for whichever mode is active:**

- `cycles` ← prior `cycles` + 1 (read first, increment, write back)
- `updated_at` ← now (RFC 3339 UTC)
- All other fields untouched (including `status`, `failure_reason`, `report_path`, `started_at`, `completed_at`).

The increment is at the **start** of work, not at the end. A run that has resolved its inputs has committed to attempting the work; cycle resources are considered consumed even if validation later fails (`gates-failed`) or an edge case aborts the run.

**Note on the `cycle` input vs the JSON `cycles` field:** they are independent. The input `cycle` is a label for the commit message (`fix(F<ID>): cycle <N> — ...`), passed by the caller and reflecting their loop count. The JSON `cycles` is the cumulative count of fix-runner runs ever performed against this feature, maintained by this skill regardless of what was passed in `cycle`. They typically agree under orchestrated use but may diverge under standalone use; that is intentional.

---

## RULES

**Always:**

- Resolve the feature reference by ID, folder, file inside the folder, or fuzzy name.
- For Mode A, require an `eval-report-<ts>.md` path that exists and lives under the resolved feature folder.
- Read `contract.md` items for the failed IDs in full before editing — items are canonical for boundary behavior.
- Apply the items-vs-spec tie-break: items win on observable behavior; spec wins on internal structure.
- Honor the project's documented governance for the artifact kinds being edited.
- Discover validation commands at runtime: gates from the contract's `## Quality gates` section (or the project's docs if absent), tests from the project's manifests/scripts.
- Stage specific files only when committing.
- Produce exactly one commit per successful invocation, on the current branch.
- Stop at the internal retry budget (default 3) and report `gates-failed` rather than commit a red tree.
- Increment `cycles` in `prd_progress.json` per **PROGRESS TRACKING** once per run.

**Never:**

- Modify `contract.md`, `spec.md`, or `plan.md`. They are inputs.
- Modify `status`, `failure_reason`, `report_path`, `started_at`, or `completed_at` in `prd_progress.json`. Only `cycles` and `updated_at` are written.
- Modify any feature entry in `prd_progress.json` other than the target feature's. Never modify top-level fields.
- Modify other features' folders. The skill is feature-scoped.
- Modify any prior `eval-report-*.md` file.
- Create / switch / delete branches. Push. Open PRs.
- Skip git hooks (`--no-verify`) or bypass signing.
- Add new tests. New assertions belong to the contract.
- Stub external services in production code. Test stubs are acceptable when the project's test infra already supports them.
- Run a full evaluation cycle or full e2e suite as a substitute for direct gates+tests validation.
- Use `git add -A` or `git add .`.

---

## OVERRIDES

Recognized free-form overrides:

- `max <N> retries` — adjust the internal gate-retry budget. Default 3.
- `dry-run` — apply edits but skip the commit step. Working tree dirty for human review.
- `skip gates` — skip the gate phase; only tests run. Use only when gates are pre-existing red and the caller wants a fix attempt anyway.

Unrecognized or contradictory overrides → default wins, log under `Overrides ignored` in the chat report.

---

## EDGE CASES

- **Eval-report path points to a different feature than the resolved `feature`** — abort: "eval-report belongs to `<other-feature>`; refusing to mix".
- **An item in `failed-items` is not present in the eval-report** — log `Soft-fails` ("item `<ID>` not in report; skipped"), continue with the others. Don't abort unless the entire list becomes empty.
- **All targeted items are `MANUAL`** — abort: "all targeted items are subjective (`MANUAL`); fix-runner can't auto-fix manual items".
- **All `failed-items` are BLOCKED on the same Prerequisite** — fix the Prerequisite once; the fix likely unblocks all of them in one edit.
- **The fix would require modifying `contract.md` / `spec.md` / `plan.md`** — abort: "the fix would require contract/spec/plan changes; that is a feature-triple revision, not a corrective pass. Re-author the triple and re-invoke."
- **Schema change required** — edit `prisma/schema.prisma`, log soft-fail directing the user to run `./scripts/migrate-dev.sh -- --name <change>` after this skill finishes. Do not attempt the migrate script (it is interactive).
- **Working tree was dirty at start (Mode A)** — proceed; commit stages only files this run touched. Pre-existing dirty files stay dirty. Log "pre-existing dirty files: `<list>`" under `Soft-fails`.
- **No code changes appear necessary** (e.g., the failure was flaky) — abort with status `aborted` and reason "no edits identified; the failure may be flaky. Re-invoke evaluation without a fix cycle."
- **Validation commands not discoverable** — log each missing command under `Soft-fails`. If both gates and tests are missing, abort: "no validation commands available; can't verify the fix would not regress".
- **Pre-existing test failures** — log under `Soft-fails`; do not count against the retry budget; do not block the commit.
- **A failed item's evidence is a network/transport error** rather than an HTTP failure — service likely failed to start during the prior eval run. Look at the implementation as if the service is broken (likely an exception during startup or in a route).
- **The eval-report is older than HEAD** — log a soft-fail "eval-report is older than HEAD; some failures may already be resolved", but continue.
