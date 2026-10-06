# Implementation Plan: F07. Report Rendering

**Prerequisites:**
- F01 to F05 delivered: settings, logging, the F02 models and enums, the F03 services, run recorder and CLI registry, the F04 client and stand-in, and the F05 triage service with its result-hook registry
- `uv` (0.12 or newer), Python 3.12, Docker Engine with Compose v2 for the database used by integration tests
- New direct dependency approved for this feature (Auto-Accept, spec assumption 1): `jinja2` (3.1.x, already installed through `crewai`). No other dependency is added. Verify the Jinja2 APIs against the installed version before use, since the spec is a sketch
- No new environment variable and no schema change. The report command needs no API key; verification uses the local OpenAI stand-in only where a triage run is involved
- Quality gate, run from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest`. Integration tests run only on request with `uv run pytest -m integration`. Tests described in spec section 7 are written first, alongside each step
- `backend/src/bugflow/services/triage.py` must not be modified; F07 only uses its public hook registry

### Stage 1: Foundations

**1. Dependency Declaration** - Declare the template engine as a direct dependency, refresh the lock file and confirm the existing suite still passes before any F07 code is written. Record the resolved version for the report.

**2. Escaping Helpers** - Create the reports package and implement the Markdown text escaping, the fenced-block builder and the Mermaid label encoder with its decoding helper, following spec assumptions 10, 11 and 14.

**3. Flow Diagram Builder** - Implement the fixed-shape Mermaid diagram generated from structured data and canonical enum labels (spec assumptions 14 and 15), together with the strict structural validator used by the tests over the full enum cross product.

**4. Report Data Loader** - Implement the structured report model and its loader that reads only stored rows through the supplied session, including the completion date and the deadline (spec assumptions 5 and 6, section 5.1).

### Stage 2: Templates and Renderer

**5. Markdown Template** - Write the English Markdown template with the section order, table rows and wording rules of spec assumptions 7 to 11, using only the escaping filters for every value.

**6. HTML Template** - Write the standalone HTML template with auto-escaping, preformatted description and steps, the diagram block and the single pinned Mermaid loader (spec assumptions 12 and 13).

**7. Renderer** - Implement the cached strict template environments and the two render functions, with the pinned Mermaid version constant and templates located relative to the module.

### Stage 3: Services, Hook and CLI

**8. Report Services** - Implement `render_report` and `get_report` with the typed models, not-found messages and render error of spec assumptions 4, 16 and 17, flushing and never committing.

**9. Result Hook and Installation** - Implement the hook that plugs into the F05 registry and the idempotent installation function with the replaceable renderer, without editing the triage module (spec assumption 3).

**10. Report Command** - Add `bugflow report` with the format and output options, exit codes and messages of spec assumption 18, and register it in the command registry so `--help` lists it.

**11. Bootstrap Installation** - Make the CLI bootstrap install the report hook so every CLI process that triages also renders, and confirm the existing F05 CLI and pipeline tests still pass unchanged.

### Stage 4: Readiness

**12. Test Support and Quality Gate** - Add the helper that creates the processed-bug states through the F02 models and the integration fixtures in their own files, then run the full quality gate and the integration suite from `backend/`. Run `triage --bug` for one seeded bug through the CLI against the compose database and the stand-in, then `report` for that bug in both formats, confirm the file output, open the HTML in a browser to see the diagram, paste the Markdown diagram into a Mermaid viewer, and confirm that no secret appears in any output. Record any deviation from the spec so it can be reported.
