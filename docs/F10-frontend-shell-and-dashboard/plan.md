# Implementation Plan: Frontend Shell and Dashboard

**Prerequisites:**
- F01 to F09 delivered. The F09 API is the only backend dependency: `/api/v1` endpoints, error envelope, enums, stats, runs and SSE. `NEXT_PUBLIC_API_BASE_URL` already exists in the root `.env.example`.
- Node.js 24 LTS (recorded in `frontend/.nvmrc`; `engines` `>=22.12.0`) and npm 11 or newer. Docker Engine with Compose v2, `uv` and the backend dependencies are needed only for the browser tests against the real API.
- **New npm dependencies, to be approved by the user before the first step (AGENTS.md section 5):** runtime `next`, `react`, `react-dom`; development `typescript`, `@types/node`, `@types/react`, `@types/react-dom`, `eslint`, `eslint-config-next`, `vitest`, `@vitejs/plugin-react`, `jsdom`, `@testing-library/react`, `@testing-library/dom`, `@testing-library/jest-dom`, `@testing-library/user-event`, `@playwright/test`. There is no frontend manifest today, so all of them are new. Nothing else is added (no data-fetching, styling, state, SSE or mock-server package). Playwright downloads a Chromium binary on `npx playwright install chromium`.
- Re-check the current stable Next.js with `npm view next dist-tags.latest` and pin that exact version (spec time: 16.4.0). Verify the plan against the installed Next.js, React, ESLint, Vitest and Playwright versions; the spec is a sketch (for example, Next.js 16 has no `next lint`, so the lint script runs ESLint directly).
- No new environment variable. `NEXT_PUBLIC_API_BASE_URL` defaults to `http://localhost:8000/api/v1`; `PORT` selects the dev server port. The frontend reads no secret.
- Quality gate. Backend, from `backend/`: `uv run ruff format .`, `uv run ruff check .`, `uv run pytest` (integration tests only on request with `uv run pytest -m integration`). Frontend, from `frontend/`: `npm run lint`, `npm run typecheck`, `npm test`, `npm run check:enums`, `npm run build`. Browser tests run on request with `npm run test:e2e`. Tests described in spec section 7 are written first, alongside each step.

### Stage 1: Scaffold and Tooling

**1. Dependency Approval and Project Scaffold** - After approval, create `frontend/` with the Next.js App Router, TypeScript and ESLint, pin the framework version exactly, commit the lockfile and record the Node version. Remove generated demo content and set the port, scripts and ignore rules described in spec section 4.

**2. Quality Tooling** - Configure strict TypeScript, the ESLint flat config, Vitest with jsdom and a test setup file, and the typecheck, test and build scripts so that the full frontend gate passes on the empty shell before any feature code exists (spec decisions 2, 7 and assumption 7).

**3. Configuration Module** - Add the single module that reads the environment and exposes the API base URL with its default and trailing-slash handling (spec decision 10, assumptions 11 and 20).

**4. Stand-in API and Fixtures** - Build the standard-library stand-in server with its scenarios, scripted live run, event stream, request record and control endpoints, together with the JSON fixtures listed in spec section 4. Add the `mock:api` script (spec decision 9, assumption 17).

### Stage 2: Shared Foundations

**5. Typed API Client** - Mirror the F09 response models as types and implement one client function per F09 operation, with query building, JSON and text handling and the typed error mapping for envelope, network and non-envelope failures (spec section 5, decision 5, assumption 18).

**6. Data Hook and Formatting** - Add the generic resource hook with loading, success, error and reload behavior, and the duration formatter (spec assumptions 13 and 15).

**7. Enum Provider** - Implement the provider that loads the enums once, exposes label and value lookups with code fallback, and reports load errors with retry. Add the enum duplication check script and its `check:enums` script (spec decisions 12 and 13).

**8. Run-Progress Hook** - Implement the hook that follows a run over the event stream, falls back to one-second polling, merges entries without duplicates, stops at a terminal status and cleans up on unmount (spec decision 11, assumption 19).

**9. Shared State Components** - Create the loading, empty and error components with the roles, wording and Retry behavior of the spec (spec assumption 15).

### Stage 3: Shell and Dashboard

**10. Application Shell and Navigation** - Build the root layout with the header, the enum provider, the primary navigation with current-page marking and the narrow-screen Menu toggle, plus the not-found page, the error boundary and the three placeholder routes (spec assumptions 10 and 16).

**11. Dashboard Page** - Compose the Dashboard from the count groups and the recent-runs list, fetching on every visit, applying the empty rule, the single error banner with Retry and the loading state, with run links to `/runs/<id>` (spec decision 14, assumptions 12 to 14).

**12. Responsive Styling** - Write the global tokens and component styles so that the layout works from 375 px up, with the breakpoint behavior of the spec and no horizontal page scroll (spec decision 6, assumption 16).

### Stage 4: Readiness

**13. Browser Tests** - Add the Playwright configuration and the browser tests that run against the stand-in API (shell, Dashboard states and content, 375 px layout) and against the real API (counts and labels equal the API values), behind `npm run test:e2e` (spec section 7, decision 8).

**14. Quality Gate and Handoff Check** - Run the backend and frontend gates listed in the prerequisites. Then start the compose database and `uv run bugflow serve`, seed the sample data through the API, start `npm run dev` and confirm in a browser that the Dashboard shows the same counts, labels and runs as the API, that the empty database and API-down states show their messages, and that the layout works at 375 px. Confirm no secret appears in the browser bundle and record any deviation from the spec so it can be reported.
