---
name: implement-and-evaluate
description: Orchestrates `implement-feature` + `evaluator` + `fix-runner` in a verify-and-retry loop. Runs the implementer once, then alternates evaluator (canonical verdict) with fix-runner (corrective pass) until the contract is honored, the retry budget is exhausted, or the run hits a circuit-breaker. Persists a per-run journal documenting every cycle and points at the underlying eval-reports.
---

# Implement and Evaluate

End-to-end orchestrator for getting a feature from `spec.md + plan.md + contract.md` to a clean `evaluator` verdict, **without operator hand-holding** between cycles. The orchestrator owns the retry loop and the journaling; the actual work is delegated to three skills, each invoked in a fresh subagent so the orchestrator's own context stays small across many cycles:

1. **`implement-feature`** — invoked once at cycle 0. Walks `plan.md` phases, commits per phase, produces contract Prerequisites as artifacts, emits a preliminary readiness report.
2. **`evaluator`** — invoked at the end of every cycle (including cycle 0). Brings up an ephemeral environment, exercises every in-scope item end-to-end, persists a timestamped `eval-report-<ts>.md`, returns the canonical verdict.
3. **`fix-runner`** — invoked at the start of cycles 1+. Reads the failing items + their evidence from the prior cycle's eval-report, edits code/fixtures/seeds/configs, validates locally, produces a single `fix(F<ID>): cycle <N> — address items …` commit.

The orchestrator never edits code itself. Never invokes any of the three skills inline — every invocation goes through a `general-purpose` subagent so each skill's run lives in its own context window.

Read-only on the project except for the journal file, the lockfile, and the target feature's entry in `prd_progress.json`. Never modifies code, contracts, specs, plans. Never commits inline. Pushes and opens PRs ONLY in Step 7 (PR creation flow), and only when the loop reached `success` and the current branch is not the project's default branch.

## INPUT

Free-form. Same resolution as `implement-feature` and `evaluator`. Accepted shapes:

- Feature ID (`F03`, `F12`).
- Feature folder (`docs/F03-video-upload/`, `./F03/`).
- File inside the feature folder (`docs/F03-video-upload/contract.md`).
- Feature name kebab-cased or fuzzy (`video upload`, `Video Upload`).

Optional natural-language overrides anywhere in the input. Six are interpreted by the orchestrator; the rest pass through to `implement-feature` on cycle 0.

| Override | Effect |
|---|---|
| `max <N> retries` | Set the orchestrator's retry budget (default 3). |
| `no retries` | Set the budget to 0 (one cycle only — initial implement + one evaluator). |
| `unlimited retries` | Disable the budget. The circuit-breaker still applies. |
| `pause between cycles` | Wait for a chat reply containing `ok` / `continue` / `segue` / `yes` between every cycle. |
| `keep eval env` | Append `keep env` to the **last** evaluator invocation's input so the user can inspect the failing environment. |
| `progress-path=<path>` | Path to the project's `prd_progress.json`. Forwarded to every sub-skill invocation so all three (`implement-feature`, `evaluator`, `fix-runner`) write to the same file. If omitted, each sub-skill auto-discovers independently. See **PROGRESS TRACKING**. |

Anything else recognized in the original input is forwarded verbatim to `implement-feature`'s invocation prompt at cycle 0 (e.g., `pause between phases`, `skip lint`, `stub OpenAI`, `only phases 1 and 2`). The orchestrator does NOT forward overrides to the evaluator (other than `keep env` per above) or to fix-runner — both run with their defaults so the verdict and the corrective pass stay reproducible.

If resolution fails:

- Feature folder missing or doesn't contain `spec.md` + `plan.md` + `contract.md` → abort: "feature folder missing required file `<file>`. Regenerate via `spec-writer`."
- Multiple plausible folders → abort and list candidates.

## OUTPUT

Two artifacts per run:

1. **Persisted journal** at `<feature-folder>/orchestration-<ts>.md`. Sibling of `contract.md` and the `eval-report-*.md` files. Format pinned by `references/journal-template.md`. Not gitignored. Captures the full loop: every cycle's invocation, returned status, eval-report path, failed/passed/blocked/manual item IDs, deltas vs. previous cycle, and the final verdict.
2. **Chat report (compact)** at the end:
   - Final status (`success` | `manual-pending` | `stuck` | `exhausted` | `aborted`).
   - Per-cycle one-liner (cycle, who ran, status, fail/pass/blocked counts, eval-report path).
   - Path to the journal.
   - Path to the latest eval-report.
   - Soft-fails / overrides ignored.

No code is written by the orchestrator. No commits inline (the three delegated skills produce their own commits per their own contracts; on `success` the orchestrator pushes those commits and opens the PR).

---

## EXECUTION STEPS

### Step 1 — Resolve input

Parse the input as free-form. Identify the feature reference and apply the override extraction described in **INPUT**:

- Recognize the six orchestrator-level overrides; record their effect.
- Strip them from the input string.
- Whatever remains becomes the **`tail`** that gets appended verbatim to the cycle-0 `implement-feature` invocation.

Resolve the feature reference to a folder containing `spec.md` + `plan.md` + `contract.md`. Compute `<feature-id>` as the leading `F<N>` segment of the folder name (lowercased, alphanumeric only — same marker definition the evaluator uses).

Determine `<run-id>` = ISO 8601 timestamp normalized for filename safety (e.g., `2026-05-01T17-32-04Z`). The same string is used in the journal filename, the journal's `**Run:**` line, and any references the orchestrator emits to the run.

**Pre-run state check (best-effort).** Locate `prd_progress.json` (use `progress-path=<path>` if provided, else search up from CWD max 4 levels). When the file exists and the target feature's entry is reachable, inspect its current `status` and emit a one-line warning to chat for the four states below before proceeding. Do NOT abort; do NOT prompt — the orchestrator stays autonomous. The warning surfaces the state for human awareness; the run continues normally and the sub-skills overwrite the status per their own contracts. When the file is unreachable (missing, unparseable, feature ID absent), skip silently — pre-run check is not allowed to block the run.

| Current `status` | Warning to emit |
|---|---|
| `done` | `"feature already 'done' (last eval clean); re-running will re-verify and may regress to 'fail' / 'pr-blocked'"` |
| `pr-blocked` | `"feature is 'pr-blocked' (prior merge-conflict unresolvable); re-running may overwrite this state"` |
| `removed` | `"feature is 'removed' from the current PRD; re-running will resurrect it without applying the prd-writer Case B reset (cycles, started_at, etc. carry over). Consider regenerating the PRD via prd-writer first"` |
| `implementing` | `"feature is 'implementing' (a prior implement-feature run never reached terminal state); re-running is safe — Write 1 will refresh the entry"` |

The four states above are the only ones that warrant a warning. `pending` / `implemented` / `fail` are normal entry points for the orchestrator and produce no warning.

Aborts:

- Triple missing → abort, suggest `spec-writer`.
- Override pattern parsed but value invalid (e.g., `max five retries` instead of `max 5`) → abort with the offending text and the expected shape.

### Step 2 — Acquire run lock

The orchestrator's lockfile lives at `<feature-folder>/.orchestrate.lock`. It is a one-line file:

```
<PID> <run-id>
```

**Lock acquisition:**

1. If the lockfile does not exist → write it with the current PID and `<run-id>`. Proceed.
2. If the lockfile exists, read the PID. Check liveness with `kill -0 <pid>`:
   - PID alive → abort: "concurrent /implement-and-evaluate run for `<feature-id>`: PID `<N>` alive. Wait for it to finish or stop it, then re-run."
   - PID dead → the prior run crashed; overwrite the lockfile and proceed. Log under `Soft-fails`: "stale lockfile from PID `<dead-pid>`; overwrote".

**Lock release:** delete the file at the very end of the run (Step 6) or on any abort path. The release is idempotent — silently succeed if the file is already gone.

### Step 3 — Initialize journal

Write `<feature-folder>/orchestration-<run-id>.md` from the template at `references/journal-template.md`. Pre-populate header (run-id, branch, feature ID, started-at, retry budget, overrides applied/ignored). Leave the per-cycle table and final-verdict block empty — they are filled as cycles complete.

The orchestrator updates the journal **after each cycle** so a partial journal is informative if the run is interrupted (Ctrl-C, crash, etc.).

### Step 4 — Cycle 0: invoke `implement-feature`

Spawn a fresh subagent via the Agent tool with `subagent_type: general-purpose`. The prompt MUST instruct the subagent to invoke the skill via the Skill tool and return a structured summary the orchestrator can act on without re-reading the implementer's full chat report.

Prompt template:

```
Invoke the `implement-feature` skill with this input:

<feature-folder> <tail>

After the skill finishes, return ONLY a fenced JSON block matching this schema:

{
  "status": "success | completed-with-regressions | incomplete | aborted-at-phase-<N> | aborted-pre-phase",
  "phases_committed": <int>,
  "phases_total": <int>,
  "abort_reason": "<text or null>",
  "report_summary": "<the implementer's verbatim chat report>"
}

Map status as follows:
- "success" or "completed with regressions" or "incomplete" → take the verbatim status string (lowercase, dashes for spaces).
- "aborted at phase N" → "aborted-at-phase-<N>".
- Pre-phase aborts (Step 4 of the implementer: missing dependency, missing PRD, missing contract section, etc.) → "aborted-pre-phase".

Do not interpret or summarize the report — copy it verbatim into report_summary.
```

Receive the JSON. Append the parsed fields to the journal under "Cycle 0" with the implementer's status, phases committed, and abort reason if any.

**Decide:**

- `aborted-pre-phase` → orchestrator finalizes with status `aborted` (Step 6). Skip the verification loop entirely. The implementer hit a structural problem (deps missing, contract empty, PRD not found, etc.); retry won't fix it.
- Any other status → proceed to Step 5. Even `incomplete` and `completed-with-regressions` go to the verifier — the canonical verdict comes from the evaluator, not the implementer's preliminary readiness signal.

If the user's overrides included `pause between cycles`, wait for a chat reply containing `ok` / `continue` / `segue` / `yes` before continuing.

### Step 5 — Verification loop

Initialize:

- `cycle = 0` (cycle 0 = cycle just completed, when implementer ran).
- `last_failed_set = ∅`, `last_passed_set = ∅`.

Loop:

#### 5.1 — Invoke `evaluator`

Spawn a `general-purpose` subagent. If this is the **last** evaluator invocation expected (i.e., the cycle that will hit the budget OR a clean signal is anticipated) AND the user passed `keep eval env`, append `keep env` to the evaluator's input. (In practice, since the orchestrator can't predict the future, only honor `keep eval env` on the run that ends up being the last — apply it when finalizing in Step 6 instead. Skip the `keep env` injection here.)

Prompt template:

```
Invoke the `evaluator` skill with this input:

<feature-folder>

After the skill finishes, return ONLY a fenced JSON block matching this schema:

{
  "status": "clean | fail | fail-gate-<name> | pending | aborted-at-step-<N> | aborted-at-item-<ID>",
  "report_path": "<absolute or workspace-relative path to eval-report-*.md>",
  "items": {
    "passed": ["<ID>", ...],
    "failed": ["<ID>", ...],
    "blocked": ["<ID>", ...],
    "manual": ["<ID>", ...],
    "skipped": ["<ID>", ...]
  },
  "acs": {
    "verified": <int>,
    "failed": <int>,
    "undetermined": <int>,
    "total": <int>
  },
  "abort_reason": "<text or null>"
}

Status mapping:
- "clean", "fail", "pending" → verbatim.
- "fail (gate <name>)" → "fail-gate-<name>" (kebab-case the gate name).
- "aborted at step <N>" → "aborted-at-step-<N>".
- "aborted at item <ID>: <reason>" → "aborted-at-item-<ID>". Put the reason in abort_reason.

Read the items lists from the eval-report's "## Items" section grouped by Verdict.
```

Receive the JSON. Compute:

- `failed_set = set(items.failed)`
- `blocked_set = set(items.blocked)`
- `manual_set = set(items.manual)`
- `passed_set = set(items.passed)`
- `passed_delta = passed_set − last_passed_set` (items that flipped to PASS this cycle)

Append to the journal: cycle number, kind = `evaluator`, status, report path, item counts, and the deltas vs. `last_failed_set` / `last_passed_set`.

#### 5.2 — Decide: stop or continue

Apply this decision tree, in order:

1. **`status == "clean"`** → terminal. Final orchestrator status: `success`. Go to Step 6.

2. **`status == "pending"` AND `failed_set == ∅` AND `blocked_set == ∅`** (i.e., only `manual` items keep the run from being clean) → terminal. Final status: `manual-pending`. Manual items are subjective and no fix cycle resolves them — the user must review them by hand. Go to Step 6.

3. **`status == "aborted-at-item-<ID>"`** with reason `pause-on-first-failure` (only possible if a stray override leaked through — orchestrator should never have set it) → terminal `aborted`. Go to Step 6.

4. **Circuit breaker (S2):** if `cycle ≥ 1` AND `failed_set == last_failed_set` AND `len(passed_delta) == 0` AND `len(failed_set) > 0` → terminal `stuck`. Go to Step 6. The implementer + fixer are not converging; further cycles waste budget.

5. **Retry budget check:** if `cycle == retry_budget` → terminal `exhausted`. Go to Step 6.

6. **Otherwise** (status is `fail`, `fail-gate-<name>`, `pending` with BLOCKED items, `aborted-at-step-<N>`, `aborted-at-item-<ID>` with service death) → continue to Step 5.3 to dispatch a fix cycle.

Special-case for `aborted-at-step-<N>`: the evaluator could not bring up the environment (broken migration, app refuses to start, etc.). Fix-runner is invoked with the eval-report path and an empty `failed-items` list **plus** a synthesized failure note ("evaluator aborted at step N: <reason>"); fix-runner will diagnose from the report's `## Abort reason` section and the project state. If `failed_set` is empty AND `aborted_at_step` is the only signal, set `failed-items=[]` for fix-runner; the skill recognizes this and operates from the abort reason.

Update `last_failed_set = failed_set`, `last_passed_set = passed_set`.

#### 5.3 — Invoke `fix-runner`

`cycle += 1`.

Spawn a `general-purpose` subagent. Prompt:

```
Invoke the `fix-runner` skill with this input:

feature=<feature-folder>
eval-report=<report_path>
failed-items=<comma-separated IDs from failed_set ∪ blocked_set>
cycle=<cycle>

After the skill finishes, return ONLY a fenced JSON block matching this schema:

{
  "status": "fixed | gates-failed | aborted",
  "commit_sha": "<SHA or null>",
  "files_touched": ["<path>", ...],
  "items_targeted": ["<ID>", ...],
  "soft_fails": ["<line>", ...],
  "abort_reason": "<text or null>",
  "report_summary": "<verbatim chat report>"
}
```

Notes on the failed-items list:

- Concatenate `failed_set` and `blocked_set`. BLOCKED items are exactly what the fix-runner is for (missing seeds, fixtures, configs).
- MANUAL items are NEVER passed to fix-runner — they are subjective and the run already terminates on them via decision-tree branch 2.
- If both sets are empty (the `aborted-at-step-<N>` case from 5.2), pass `failed-items=` (empty list); fix-runner will fall back to the abort reason and the report.

Receive the JSON. Append to the journal: cycle number, kind = `fix-runner`, status, commit SHA (if any), files touched, items targeted, soft-fails.

**Sub-decisions:**

- `fixed` (commit produced) → loop back to 5.1 with the same `cycle` (the next evaluator run is part of cycle `cycle`).
- `gates-failed` (no commit; working tree dirty) → the cycle is a "wasted" retry. Counts against the budget. Skip the next evaluator run — there is nothing new to verify — and go straight to the next iteration's Step 5.2 with the same `last_failed_set` (no eval was run, so no new data; the budget check or circuit breaker may end the run here).
  - Implementation note: model this as an immediate re-application of Step 5.2's logic with synthetic data: pretend evaluator status was unchanged, and let branch 4 (circuit breaker — same `failed_set`, no `passed_delta`) trigger if applicable, otherwise branch 5 (budget check) eventually ends the run as `exhausted`.
- `aborted` (e.g., MANUAL-only items, or fix would require contract changes) → terminal `aborted`. Append the fix-runner's abort reason to the journal and go to Step 6.

If the user's overrides included `pause between cycles`, wait for `ok` / `continue` / `segue` / `yes` before looping back to 5.1.

### Step 6 — Compute final status

Compute the final status from how the loop terminated:
- `success` — `clean` reached.
- `manual-pending` — only MANUAL items left.
- `stuck` — circuit-breaker tripped.
- `exhausted` — budget consumed without success.
- `aborted` — pre-phase abort, fix-runner abort, or evaluator override abort.

If the final status is `success`, proceed to **Step 7 — PR creation flow**. For any other status, skip Step 7 and go directly to Step 8.

### Step 7 — PR creation flow (only on `success`)

Triggered exclusively when Step 6 computed `success`. Goal: open a pull request from the current feature branch to the project's default branch, with the feature integrated against the latest default-branch state.

**7.1 — Safety check.** Determine the project's default branch via `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` (e.g., `main`). If the current branch (`git branch --show-current`) equals the default branch, abort PR creation and finalize with status `success` plus a chat-report warning: `"Cannot open PR from default branch <main> to itself. Re-invoke from a feature branch if you want a PR."`. The work itself is still done; only the PR step is skipped.

**7.2 — Sync with the default branch.** Fetch and merge the latest default branch into the current feature branch. Operates on whatever branch is checked out — works correctly inside a `git worktree`.

```
git fetch origin <default-branch>
git merge origin/<default-branch>
```

Three outcomes:

- **Already up to date** (nothing to merge) → proceed to Step 7.5.
- **Clean merge** (auto-merged, possibly with a merge commit) → proceed to Step 7.4 (re-eval).
- **Conflicts** (`git status` shows unmerged paths) → proceed to Step 7.3.

If any other git failure happens (e.g., merge tool exits non-zero unrelated to conflicts, network drops mid-fetch), abort PR creation and finalize with status `success` plus a chat-report warning naming the git failure. The user can resolve manually and re-invoke or open the PR by hand.

**7.3 — Resolve conflicts via `fix-runner` (Mode B).**

Capture the conflicted files: `git diff --name-only --diff-filter=U`. Spawn a `general-purpose` subagent with this prompt:

```
Invoke the `fix-runner` skill with this input:

feature=<feature-folder>
mode=resolve-conflict
conflicted-files=<comma-separated paths from git diff>
cycle=<current cycle + 1>

After the skill finishes, return ONLY a fenced JSON block matching this schema:

{
  "status": "fixed | gates-failed | aborted",
  "commit_sha": "<SHA or null>",
  "files_touched": ["<path>", ...],
  "abort_reason": "<text or null>"
}
```

Outcomes:
- `fixed` → merge commit produced by fix-runner. Proceed to Step 7.4 (re-eval against the merged state).
- `gates-failed` or `aborted` → fix-runner could not produce a clean resolution. Finalize with terminal status `pr-blocked` and `failure_reason="unresolvable merge conflict in <files>: <fix-runner abort_reason>"`. Working tree is left as fix-runner left it (markers may still be present for `aborted`; clean for `gates-failed` but uncommitted). The user resolves manually, commits, and either pushes + opens PR by hand OR re-invokes the orchestrator.

**7.4 — Re-run evaluator.** Because the merge changed code on the feature branch, validate the post-merge state. Spawn a `general-purpose` subagent and run the evaluator (same prompt template as Step 5.1, with `cycle += 1`).

- `clean` → the merge did not break anything; proceed to Step 7.5.
- Anything other than `clean` → re-enter the normal verification loop at Step 5.2 (decision tree: stop or continue). The merge counts as a code change, so the regular fix-runner / re-eval cycles apply. After the loop terminates, recompute Step 6's final status. If it still ends up as `success`, do NOT re-do Step 7.2 (only one merge per orchestrator run — avoids race conditions when main advances during the cycle); jump straight to Step 7.5. If status is no longer `success`, skip Step 7.5–7.7 and go to Step 8.

**7.5 — Push the branch.**

```
git push -u origin <branch>
```

If push fails (auth denied, remote rejected, network), finalize with status `success` plus a chat-report warning naming the failure. Print the explicit manual command the user can run to push: `git push -u origin <branch>`.

**7.6 — Check for an existing PR.**

```
gh pr list --head <branch> --json url,number --limit 1
```

If an existing PR is returned: skip creation; record its URL in the chat report ("Existing PR updated: `<url>`"). The previous push (Step 7.5) already updated the PR's diff and triggers any CI bound to it.

If no existing PR: proceed to 7.7.

**7.7 — Create the PR.**

Sources for the placeholders the orchestrator does not already have in memory:

- **`<Feature Name>`** — derive from the feature folder name. Strip the `F<ID>-` prefix, replace hyphens with spaces, title-case each word. Example: `F03-video-upload` → `Video Upload`. Do NOT open the PRD just for this.
- **`<verbatim AC text>` for the AC checklist** — read from the **latest `eval-report-<ts>.md`** of this run (path is in the journal). Its `## Coverage Manifest` table has every in-scope AC verbatim in the first column with a tri-state mark; since Step 6 reached `success` here, every row is `✓ verified`. Copy each first-column cell as a checklist line. This avoids re-parsing the PRD or contract.
- **`<2–3 sentence summary>`** — read the target feature's section in the PRD's Section 6 (Functionalities). Pull the first 1–2 sentences of the `Capabilities` block and, if needed, one sentence of `Experience`. Trim aggressively — this is a PR summary, not a spec. If the PRD is not locatable for any reason, fall back to a one-liner: `"Implements F<ID> per its contract; see Acceptance Criteria below."` Do NOT block PR creation on PRD reading.
- **`<Closes #N>` (optional auto-link)** — query GitHub for an open tracking issue created earlier by `spec-writer`:
  ```
  gh issue list --search "[F<ID>] in:title" --state open --json number,url --limit 5
  ```
  - Zero matches → omit the `## Closes` section entirely from the body. This is the expected case when the user did not opt into issue creation at spec time.
  - Exactly one match → set `<N>` to that issue's `number` and include the `## Closes` section.
  - Multiple matches → use the **first** result's `number`, log a soft-fail in the journal naming all matched issue URLs (so the user can manually consolidate), and include the `## Closes` section with the first.
  - `gh` failure → omit the `## Closes` section, log a soft-fail in the journal, and continue. PR creation is never blocked on issue lookup.

Build the title:
```
feat(F<ID>): <Feature Name>
```

Build the body using this template:

````markdown
## Summary

Implements **F<ID>: <Feature Name>**.

<2–3 sentence summary derived from the PRD's Capabilities and Experience for this feature>

## Acceptance Criteria

All in-scope ACs verified end-to-end by the contract evaluator:

- ✓ <verbatim AC text>
- ✓ <verbatim AC text>
...

## Implementation Cycle

- Phases committed: <N> (by `implement-feature`)
- Fix cycles: <M> (by `fix-runner`)
- Final eval: clean — every contract item PASS

## Artifacts

- Spec: `docs/F<ID>-<name>/spec.md`
- Plan: `docs/F<ID>-<name>/plan.md`
- Contract: `docs/F<ID>-<name>/contract.md`
- Latest eval-report: `docs/F<ID>-<name>/eval-report-<ts>.md`
- Orchestration journal: `docs/F<ID>-<name>/orchestration-<run-id>.md`

## Closes

Closes #<N>

---

🤖 Auto-generated. Every acceptance criterion above was exercised end-to-end against the contract.
````

The `## Closes` section in the template above is **conditional**: emit the section header AND its `Closes #<N>` line only when the `gh issue list` lookup matched at least one open issue. When the lookup returned zero matches (or `gh` failed), strip the entire `## Closes` block from the body — do NOT emit an empty section.

Invoke:

```
gh pr create --title "<title>" --body "$(cat <<'EOF'
<body content above>
EOF
)"
```

Capture the returned PR URL. If `gh pr create` fails, finalize with status `success` plus a chat-report warning naming the failure and the manual command to retry.

### Step 8 — Finalize

1. **Last-evaluator `keep env` (if user requested it AND the final status is not `success`)** — re-invoke evaluator one more time with `keep env` appended, so the user has a live environment to inspect. Log this re-invocation in the journal as a special "post-finalize" entry; its status is informational only (does not change the final orchestrator status).

2. **Write the journal's final block** with: final status, total cycles, total commits across cycles (sum of phase commits + fix commits), paths to all eval-reports produced (one per evaluator invocation), aggregate failed/blocked items left, journal soft-fails, plus PR section: PR URL (when opened), or "PR not opened: <reason>" (when blocked or skipped due to default-branch / push failure / gh failure).

3. **Release the lockfile** at `<feature-folder>/.orchestrate.lock`. Idempotent.

4. **Emit chat report:**

```
implement-and-evaluate — F<ID> <Feature Name>

Status: success | manual-pending | stuck | exhausted | aborted | pr-blocked
Cycles: <N> (1 implement + <N-1> fix)
Branch: <git branch>
Run: <run-id>

Cycle log:
  0  implement-feature  <impl status>     phases <X>/<Y>
  0  evaluator          <eval status>     P=<P> F=<F> B=<B> M=<M>   eval-report-<ts1>.md
  1  fix-runner         <fix status>      commit <sha or none>
  1  evaluator          <eval status>     P=<P> F=<F> B=<B> M=<M>   eval-report-<ts2>.md
  ...

Pull request:
  ✓ Opened: <url>
  OR  ✓ Updated existing: <url>
  OR  ❌ Not opened — <reason>: <one-line + manual command to retry>

Latest eval-report: <path>
Journal: <path>

Soft-fails:
- <line>

Overrides applied:
- <line>

Overrides ignored:
- <line>

Abort reason (if any): <one-paragraph>
```

If `keep eval env` was honored, add a final block listing the live env's connection details (DB URL, service URLs, tmpdir) plus the explicit cleanup command for the user to run later.

---

## PROGRESS TRACKING

This orchestrator delegates most `prd_progress.json` writes to the three sub-skills:

- `implement-feature` writes `status="implementing"` (transient, Step 5 start), `status="implemented"` (on Step 7 success-path completion), or `status="fail"` on a phase / pre-phase abort.
- `evaluator` writes `status="done"` on clean, `status="fail"` on fail / fail-gate / abort, plus `report_path`.
- `fix-runner` increments `cycles` once per cycle. Status untouched.

The orchestrator's direct writes are limited to two cases:
1. **Setting `status="pr-blocked"`** — a status only the orchestrator can produce, when Step 7's merge with the default branch produces conflicts that `fix-runner` (Mode B) cannot resolve. This is the orchestrator's only `status` write.
2. **Augmenting `failure_reason`** in terminal-failure cases (`exhausted`, `stuck`, `aborted`) to surface orchestrator-level context the sub-skills cannot know on their own.

**Locating the file:**
- If the input contains `progress-path=<path>`, use it AND forward it verbatim into every sub-skill prompt the orchestrator dispatches (so `implement-feature`, `evaluator`, and `fix-runner` all write to the same file deterministically).
- Otherwise, search up from CWD (max 4 levels) for the nearest `prd_progress.json`. Do NOT forward to sub-skills in this branch — let them auto-discover independently. (They will land on the same path under normal conditions, since they share CWD.)
- If not found, log a `Soft-fails` line "progress file not found, orchestrator-level write skipped" and proceed. The journal still captures everything; the JSON simply lacks the orchestrator's annotation.

**Scope rule:** never modify any feature's entry other than the target feature's. Never modify top-level fields. The orchestrator may write `status`, `failure_reason`, and `updated_at` — and only in the cases below. Status writes are restricted to the `pr-blocked` case; every other status comes from sub-skills.

**Failure modes — silent continuation:**
- File not found, fails to parse, or feature ID missing → log `Soft-fails`, skip the write.
- Atomic write fails → log `Soft-fails`, skip.

**Writes — at Step 8 finalize, branched on the orchestrator's terminal status:**

- **`success`** → no write. The last evaluator already set `status="done"`; nothing to add.
- **`manual-pending`** → no write. Manual items are subjective; status from the last evaluator stands; the user reviews via the journal and the report.
- **`exhausted`** (retry budget consumed without success) →
  - `failure_reason` ← `"cycle budget exhausted (<N> cycles); last: <prior failure_reason or "no prior failure_reason">"` (≤200 chars; truncate the prior reason if needed)
  - `updated_at` ← now
  - Status untouched (already `fail` from the last evaluator).
- **`stuck`** (circuit-breaker S2: same FAIL set, zero PASS delta) →
  - `failure_reason` ← `"circuit breaker: same FAIL set across cycles <N-1> and <N>, no PASS delta"`
  - `updated_at` ← now
  - Status untouched (already `fail` from the last evaluator).
- **`aborted`** (any termination via Step 4 pre-phase, fix-runner abort, or evaluator override abort) →
  - `failure_reason` ← `"orchestrator aborted: <reason>"` (reason from the journal's abort entry; ≤200 chars)
  - `updated_at` ← now
  - Status untouched (whatever the last sub-skill set; for pre-phase aborts, `implement-feature` already wrote `fail` with its own failure_reason — the orchestrator overwrites it to add orchestrator framing).
- **`pr-blocked`** (Step 7's merge with the default branch produced conflicts that `fix-runner` Mode B could not resolve) →
  - `status` ← `"pr-blocked"` (the only status the orchestrator writes directly; overwrites the `done` left by the last evaluator because the integration step revealed the work is not yet shippable)
  - `completed_at` ← `null` (the prior evaluator's `clean` verdict had set this; clearing it keeps the schema invariant `completed_at` ≠ null ⇔ status == `done`. The work isn't completed-shipped — only completed-locally — so the field must reset)
  - `failure_reason` ← `"unresolvable merge conflict in <files>: <fix-runner abort_reason>"` (≤200 chars)
  - `updated_at` ← now

The orchestrator's annotation is purely for forensic clarity in the JSON. The journal at `<feature-folder>/orchestration-<run-id>.md` remains the canonical narrative record; the JSON's job is the deterministic terminal status + a one-line breadcrumb.

---

## RULES

**Always:**

- Resolve the feature reference using the same rules as `implement-feature` and `evaluator`.
- Run the Step 1 pre-run state check against `prd_progress.json` (best-effort): emit the documented one-line warning when the target feature's current `status` is `done`, `pr-blocked`, `removed`, or `implementing`. Never abort or prompt on the warning — the orchestrator stays autonomous and lets the sub-skills overwrite per their own contracts.
- Acquire `<feature-folder>/.orchestrate.lock` with PID-aliveness check before any subagent dispatch.
- Initialize and continuously update `<feature-folder>/orchestration-<run-id>.md` per `references/journal-template.md`.
- Delegate the three skills via fresh `general-purpose` subagents — one subagent per skill invocation, one skill invocation per subagent. Never invoke the skills inline.
- Demand structured JSON returns from each subagent so the orchestrator never parses markdown.
- Run `evaluator` after every code-modifying step (cycle 0 implement, cycle ≥ 1 fix). The evaluator is canonical; the implementer's preliminary readiness is not.
- Aggregate `failed_set ∪ blocked_set` as the input list to fix-runner. Never include MANUAL items.
- Apply circuit-breaker S2 strictly: same FAIL set + zero PASS delta = stop, no further retry.
- Honor the orchestrator-level overrides exactly (`max N retries`, `no retries`, `unlimited retries`, `pause between cycles`, `keep eval env`, `progress-path=<path>`) and forward everything else into the cycle-0 implementer prompt.
- Release the lockfile on any termination path, including aborts.
- Forward `progress-path=<path>` to every sub-skill subagent prompt when received as input, so `implement-feature`, `evaluator`, and `fix-runner` all write to the same `prd_progress.json`. Append orchestrator-level `failure_reason` per **PROGRESS TRACKING** at Step 8 in `exhausted` / `stuck` / `aborted` cases; write `status="pr-blocked"` plus `failure_reason` in the `pr-blocked` case.
- When Step 6 computes `success`, run Step 7 (PR creation flow): safety-check the current branch is not the default branch, fetch + merge `origin/<default>`, dispatch `fix-runner` Mode B if conflicts arise, re-evaluate after the merge, push the branch, then `gh pr create` with the canonical title (`feat(F<ID>): <Feature Name>`) and the body template documented in Step 7. Skip Step 7 cleanly (warn in chat report, status stays `success`) when the branch is the default branch, push fails, or `gh pr create` fails — the work is done; only the announcement step couldn't complete.
- Detect existing PRs via `gh pr list --head <branch>` before `gh pr create`; if present, push only and report the existing URL.
- Look up the matching open `[F<ID>]` issue (created by `spec-writer`) via `gh issue list --search "[F<ID>] in:title" --state open --json number,url --limit 5` immediately before composing the PR body in Step 7.7. When a match exists, inject `## Closes\n\nCloses #<N>` into the body so GitHub auto-closes the issue on merge; when none exists or `gh` fails, omit the section entirely and continue.

**Never:**

- Edit code, contracts, specs, plans, eval-reports, or any prior `orchestration-*.md`. Read-only on the project except for the current run's journal, lockfile, and the target feature's `status` / `failure_reason` / `updated_at` fields in `prd_progress.json` (status writes only in the `pr-blocked` case per **PROGRESS TRACKING**).
- Override `status` in `prd_progress.json` outside the `pr-blocked` case. Status is otherwise owned by the sub-skills (`implement-feature` / `evaluator` / `fix-runner`); the orchestrator only annotates `failure_reason` in terminal-failure cases.
- Push or open PRs outside Step 7. No push during the verification loop, no PR opened on `manual-pending` / `stuck` / `exhausted` / `aborted` / `pr-blocked`.
- Force-push (`git push --force` or `--force-with-lease`). Step 7 uses plain `git push` only — the merge approach was chosen specifically to avoid history rewrites that would require force-push.
- Open a PR from the project's default branch to itself. Step 7's safety check aborts PR creation when the current branch equals the default branch.
- Modify any feature entry in `prd_progress.json` other than the target feature's. Never modify top-level fields.
- Skip the lockfile check. Concurrent runs on the same feature are unsafe and the lockfile is the cheap insurance.
- Forward orchestrator-level overrides to the implementer (they are consumed by the orchestrator). Forward non-orchestrator overrides to evaluator or fix-runner — they have their own override grammars and the orchestrator doesn't translate. The single exception is `progress-path=<path>`: although it is orchestrator-level, it IS forwarded verbatim to all three sub-skills so they all write to the same `prd_progress.json` (per **PROGRESS TRACKING**).
- Pass MANUAL items to fix-runner. They are subjective and terminate the run via decision-tree branch 2.
- Re-invoke `implement-feature` after cycle 0. The implementer's design is greenfield (one phase per commit); retries are owned by `fix-runner`.
- Continue the loop after the circuit-breaker trips. Stuck-on-same-failures is a signal that further fix cycles waste budget; surface it, stop.
- Mark the run `success` when the journal still has unaddressed failures of any kind.

---

## OVERRIDES

| Override | Effect | Default |
|---|---|---|
| `max <N> retries` | Sets the retry budget. `N` is a non-negative integer. | 3 |
| `no retries` | Equivalent to `max 0 retries`. | — |
| `unlimited retries` | Disables the budget. The circuit-breaker still applies. | — |
| `pause between cycles` | Wait for `ok`/`continue`/`segue`/`yes` between every cycle (cycle 0 → 1, 1 → 2, etc.). | autonomous |
| `keep eval env` | After finalizing, re-invoke evaluator once with `keep env` so the user can inspect a live failing environment. Skipped on `success`. | off |

Anything else recognized in the input string is **forwarded verbatim** to the cycle-0 `implement-feature` invocation as part of its `tail`. The orchestrator does not interpret those overrides; the implementer does. Examples that pass through:

- `pause between phases` (interpreted by implementer)
- `skip lint`, `skip tests`, `skip typecheck` (interpreted by implementer)
- `stub OpenAI`, `assume empty response for missing APIs` (interpreted by implementer)
- `only phases 1 and 2` (interpreted by implementer)

Unrecognized text is left in the `tail`. If the implementer ignores it, that's the implementer's concern — the orchestrator logs nothing.

**Immutable core (cannot be overridden):**

- The verification loop runs after every code-modifying step.
- The lockfile is acquired and released.
- The journal is persisted.
- The circuit-breaker S2 trips on stuck runs.
- The fix-runner receives `failed_set ∪ blocked_set`, never MANUAL.

---

## EDGE CASES

- **No `spec.md` / `plan.md` / `contract.md` triple** → abort at Step 1; instruct the user to run `spec-writer`.
- **PRD missing** → propagate the implementer's pre-phase abort directly. The orchestrator does not look for a PRD itself; the implementer does.
- **Implementer aborts pre-phase (deps missing, contract empty, etc.)** → terminal `aborted`. No evaluator. No fix cycle. Journal records the abort with the implementer's reason.
- **Evaluator aborts at step 1 (input resolution)** when called from the orchestrator → unexpected (orchestrator already resolved input). Treat as `aborted` and log the evaluator's diagnostic.
- **Evaluator aborts at step 4 (bring-up failure)** → fix-runner is dispatched with `failed-items=` (empty) and the report path; fix-runner reads the report's `## Abort reason` to diagnose. This is a common case (broken migration introduced by the implementer).
- **Fix-runner returns `gates-failed`** → no eval re-run this iteration; cycle counts as consumed; loop continues only if budget remains AND circuit-breaker hasn't tripped. If neither budget nor passed-delta has changed, the next iteration's circuit-breaker will trip (same failed_set, zero passed delta).
- **Fix-runner returns `aborted` because the fix would require contract changes** → terminal `aborted`. The journal logs the reason. The user must regenerate the spec/contract via `spec-writer`.
- **Multiple eval-reports written in a single cycle** (e.g., the user re-runs evaluator manually mid-cycle) → orchestrator uses only the report path returned by its own evaluator subagent; foreign reports in the folder are ignored.
- **Stale lockfile (process crashed mid-run)** → orchestrator overwrites and proceeds; logs under `Soft-fails`. The prior journal is left intact (re-runs produce a new timestamped journal — old journals are immutable history).
- **`pause between cycles` and the user types something other than the recognized resumption tokens** → orchestrator interprets the text as additional overrides for the *next* fix cycle and appends to the next subagent's prompt. (E.g., user types `skip tests` between cycle 1 and 2; that goes into the cycle-2 fix-runner prompt.)
- **`keep eval env` on a `success` run** → ignored (no failing env to keep). Logged under `Overrides ignored` in the chat report.
- **Run interrupted (Ctrl-C, machine reboot)** → the lockfile is left behind; the partial journal is left as-is. Next invocation detects the stale lockfile via PID-aliveness, overwrites it, and starts a fresh run-id (it does not resume).
- **Branch changed mid-run** (`git checkout` between cycles) → all commits and the new run-id are pinned to the branch the orchestrator started on; switching branches mid-run is undefined and the orchestrator does not detect it. Documented behavior: do not switch branches between cycles.
- **Feature is already in a clean state when invoked** (implementer says all phases committed, evaluator says clean) → terminal `success` after one cycle. Journal records "0 phases newly committed; 0 fix cycles".
- **Implementer's `tail` contains an orchestrator-level token** (e.g., `max 5 retries` shows up in the user's input but the orchestrator missed it) → the implementer will see it but won't interpret it, since `max N retries` is in the implementer's grammar too (it's the implementer's hard-fail retry, not the orchestrator's). This is acceptable double-counting — the implementer applies it within its hard-fail loop; the orchestrator already extracted its own copy at Step 1.
- **Evaluator returns `aborted-at-item-<ID>` with `service died`** → fix-runner is dispatched with the failing item ID (the run was aborted partway, so `failed_set` may be partial; include the aborted item plus everything explicitly FAIL or BLOCKED in the partial report).
- **No items at all are returned by the evaluator** (clean and zero items, e.g., a contract with empty surfaces) → the evaluator should already have aborted on a malformed contract; if not, treat as `success` (vacuous truth) and surface a soft-fail "evaluator returned zero items; verify contract has any items".
