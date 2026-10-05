# Assertion Patterns

Recognized phrasings in contract item `then` bullets that the evaluator translates **mechanically** to executable assertions. When a bullet matches one of these patterns, the skill executes the translation directly with no LLM interpretation. When a bullet does NOT match, the model interprets it freely and the item is **flagged with `*`** in the report (the interpretation is logged in the item's reasoning).

This file is the **boundary** between trusted mechanical translation and flagged LLM interpretation. Adding a pattern here graduates a phrasing out of LLM territory and into mechanical execution. Patterns should be added only after seeing them in real contracts at least twice.

The grammar is intentionally informal — a small set of recognizable shapes, not a strict parser. When an evaluator-time judgment finds that a bullet "obviously" matches a pattern even if the wording differs slightly, it may translate mechanically and note the lenient match in evidence. When in doubt, prefer to flag with `*`.

---

## HTTP

### Status code

Phrasings:
- `<N> <Reason>` (`201 Created`, `413 Payload Too Large`, `422 Unprocessable Entity`)
- `responds with status <N>`
- `HTTP <N>`

Translation: `assert response.status === <N>`.

### Body field equality

Phrasings:
- `body.<path> === <literal>`
- `<field>: "<literal>"` inside an inline body shape
- `<field>` set to `<literal>`

Translation: `assert get(response.body, "<path>") === <literal>`.

### Body field type / shape

Phrasings:
- `<field>` (uuid)
- `<field>` (ISO 8601)
- `<field>` is a non-empty string / number / boolean / null
- `<field>` (= <handle>.<attribute>) — equality against a Persistent state handle

Translation: type / shape check matching the named type. The `(= <handle>.<attribute>)` form resolves the handle from Persistent state and asserts equality.

### Body field comparison

Phrasings:
- `<field>` ≈ `<value>` (within a tolerance, default 5 % when not stated; recommended for durations, sizes)
- `<field>` `> | < | >= | <=` `<value>`
- `<field>` matches `<regex>` or matches `/pattern/`

Translation: numeric comparison with the stated tolerance, or regex match.

### Body shape

Phrasings:
- `body { field1, field2, ... }` (anonymous shape — assert each field is present, type-checked when annotated)
- `response body matches { ... }` (named fields with types or values)

Translation: assert each named field is present; assert declared types or values when annotated.

### Headers

Phrasings:
- `Content-Type: <value>`
- header `<name>` is `<value>`
- header `<name>` matches `<regex>`

Translation: assert response header equals or matches.

---

## Persistence (DB)

### Row count

Phrasings:
- `exactly <N> row(s) exist in <table>` [`for <column> = <value>`]
- `<N> rows in <table>`
- `zero rows in <table>` [`for <column> = <value>`]

Translation: `SELECT count(*) FROM <table> [WHERE ...] === <N>`. The `WHERE` clause is built from the `for` predicate (handle resolution allowed: `for owner_id = alice.id` resolves alice's id from Persistent state).

### Row values

Phrasings:
- `the row in <table> has <column> = <value>`
- `the persisted row's <column> equals <handle>.<attribute>`
- `<column> IS NULL` / `<column> IS NOT NULL`
- `whose values match the response body` (cross-check: each column equals the equivalently-named field captured from the response)

Translation: `SELECT * FROM <table> WHERE ...` then assert per-column equality, NULL-ness, or cross-source match.

### Row absence

Phrasings:
- `no row exists in <table>` [`for <column> = <value>`]
- `<table> is empty` [`for <column> = <value>`]

Translation: `SELECT count(*) ... === 0`.

---

## Filesystem

### File existence

Phrasings:
- `the file at <path> exists`
- `<path> is a non-empty <type>` (e.g., `JPEG`, `PNG`, `MP4`)

Translation: `stat(path)` succeeds and `size > 0`. For typed content, a magic-byte sniff or `file <path>` confirms the type.

### File absence

Phrasings:
- `no file is left under <directory>`
- `<directory> is empty`
- `no <kind> was persisted under <directory>`

Translation: `readdir(directory)` returns empty (or filtered for the named kind).

### File size

Phrasings:
- `the file at <path> has the same byte count as <fixture>`
- `size of <path> equals <N>`

Translation: `stat(path).size === stat(fixture).size`, or numeric equality.

### Indirect path (path discovered from a row)

Phrasings:
- `the file referenced by that row's <column>`

Translation: read `<column>` from the previously-asserted row, then apply file existence / size checks at the resulting path.

---

## UI / DOM (surfaces `UI` and `E2E` driving a browser)

### Element presence

Phrasings:
- `the page contains a <region | element> with the heading text "<text>"`
- `a "<label>" button is rendered and enabled`
- `a queue row appears whose label includes <quoted text>`

Translation: query selector or accessible-name lookup; assert presence and (for buttons) the `disabled` attribute is absent.

### Element text

Phrasings:
- `the row's <element> reads "<text>"`
- `<region> displays "<text>"`
- contains tokens `<token1>` and `<token2>`

Translation: text extraction; equality, substring, or all-tokens-present match.

### Element absence

Phrasings:
- `no <region> is rendered`
- `no <element> outside of <other element> accepts <kind> drops on <route>`

Translation: query returns empty.

### URL navigation

Phrasings:
- `the URL becomes <path>`
- `navigate to <path>`

Translation: assert browser location.

### Network observed

Phrasings:
- `no network request is made to <pattern>`
- `the navigation succeeds without canceling the in-flight request (no aborted XHR)`

Translation: capture network log during the action and assert absence / presence.

### Progress / dynamic value

Phrasings:
- `progress percentage advances from 0 to 100`
- `bytes transferred alongside total bytes (e.g., "X.X MB / X.X MB")`

Translation: poll the relevant DOM element across a time window; assert monotonic progression with a final value at or near the upper bound.

---

## Service (surface `Service`)

### Function call result

Phrasings:
- `<function>(<args>) returns <value>`
- `<function>(<args>) throws <error type>`

Translation: invoke the function in the project's runtime (model figures out the import path from the contract item plus spec.md or codebase); assert return value or thrown error type.

---

## Cross-cutting

### Error envelope

Phrasings:
- `body { code: "<CODE>", message }` — common error envelope
- `body.code === "<CODE>"`
- `details.<field>: <value>`

Translation: assert `body.code === "<CODE>"`; when `message` is named without a value, assert it is a non-empty string; assert nested `details.<field>` per its annotation.

### Time and ordering

Phrasings:
- `createdAt (ISO 8601)`
- `<field>` happens before `<field>`

Translation: ISO 8601 parse + monotonic comparison.

### Cross-source match (response ↔ DB ↔ filesystem)

Phrasings:
- `the persisted row's values match the response body`
- `the file at <path> has the same byte count as <fixture>`

Translation: capture the response body / fixture stats first; then assert the named row / file matches the captured source.

---

## Anti-patterns (do NOT translate mechanically)

These phrasings cannot be auto-verified reliably. Items containing only such bullets are `MANUAL`. Items mixing them with mechanical bullets are partially mechanical + the unverifiable bullet is logged as un-verifiable, pushing the item to `MANUAL` overall.

- "feels right", "looks correct", "matches the design system" without a concrete selector or color spec — subjective.
- "eventually" / "after some time" without a bound — non-deterministic.
- "the user understands" / "is clear to the user" — subjective.
- references to performance characteristics (latency, throughput) without a measurable threshold.
- "approximately" with no tolerance and no reference value the evaluator can compute against.
