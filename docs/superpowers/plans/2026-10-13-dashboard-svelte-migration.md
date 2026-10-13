# Dashboard Svelte 5 and SvelteKit 3 Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate the Sentinela DAS web dashboard from React 19 to Svelte 5 and SvelteKit 3 in single-page mode with 100% functional and visual parity.

**Architecture:** SvelteKit 3 in client-only SPA mode with `@sveltejs/adapter-static` handles file-based routing (`/`, `/enrollments`, `/staff`). Svelte 5 runes (`$state`, `$derived`, `$effect`, `bind:value`) replace React hooks, and a custom reactive poller (`poll.svelte.ts`) drives all live API list polling.

**Tech Stack:** Svelte 5.57, @sveltejs/kit 3.0, @sveltejs/adapter-static 4.0, @sveltejs/vite-plugin-svelte 7.3, svelte-check 4.7, typescript ~6.0, @typescript/native npm:typescript@7, DaisyUI 5, Tailwind v4, Vite+, Firebase 13.

**Spec:** [docs/superpowers/specs/2026-10-13-dashboard-svelte-migration-design.md](../specs/2026-10-13-dashboard-svelte-migration-design.md)

## Global Constraints

- Svelte 5.57, SvelteKit 3.0, @sveltejs/adapter-static 4.0, typescript ~6.0, @typescript/native npm:typescript@7.
- Single-page application mode only: `export const ssr = false;` in `src/routes/+layout.ts` and fallback to `index.html` in `adapter-static`.
- No `#lib` or `$lib` aliases; all imports use relative paths.
- No `load` functions; data fetching happens inside components via `poll.svelte.ts` due to client-side Firebase auth.
- Class strings must remain whole literals in quotes (e.g. `class={["tab", active && "tab-active"]}`) for Tailwind v4 static detection.
- All Romanian UI strings and error messages remain verbatim.
- Every commit must pass git hooks (`npx vp check` and `npx svelte-check --tsgo --fail-on-warnings`).

## Review Focus

1. In-flight poll cancellation: Unmounting a view or switching routes aborts pending fetches without error logging.
2. 409 conflict handling: Claiming an incident already claimed by another dispatcher shows the error notice and refreshes data.
3. Access denial for unlisted phone: Signs out and shows `"Numărul nu este înregistrat. Contactați medicul de familie."`.
4. Access denial for medic role: Signs out and shows `"Acest număr nu are acces la dispecerat."`.
5. Caddy caching: `/_app/immutable/*` sets `Cache-Control: public, max-age=31536000, immutable`, and missing hashed assets return 404 instead of `index.html`.

---

### Task 1: Toolchain & SvelteKit 3 Scaffold Verification (Action Item 1)

**Files:**
- Create: `dashboard/src/app.html`
- Create: `dashboard/src/routes/+layout.ts`
- Create: `dashboard/src/routes/+layout.svelte`
- Create: `dashboard/src/routes/+page.svelte`
- Modify: `dashboard/package.json`
- Modify: `dashboard/vite.config.ts`
- Modify: `dashboard/tsconfig.json`

**Interfaces:**
- Consumes: Existing Vite+ runner and Tailwind v4 setup.
- Produces: Working SvelteKit 3 build pipeline generating static output to `dist/`.

- [ ] **Step 1: Update `dashboard/package.json` dependencies and scripts**
  Add Svelte devDependencies (`svelte`, `@sveltejs/kit`, `@sveltejs/adapter-static`, `@sveltejs/vite-plugin-svelte`, `svelte-check`, `typescript@~6.0`, `@typescript/native@npm:typescript@7`) and scripts (`check: vp check && svelte-check --tsgo --fail-on-warnings`, `prepare: svelte-kit sync || echo ''`).

- [ ] **Step 2: Install dependencies**
  Run: `npm ci` in `dashboard/`
  Expected: Clean install resolving Vite+ core override.

- [ ] **Step 3: Configure `dashboard/vite.config.ts`, `dashboard/tsconfig.json`, and `dashboard/src/app.html`**
  Update `vite.config.ts` with `sveltekit({ adapter: adapter({ pages: "dist", assets: "dist", fallback: "index.html" }) })` and `fmt: { svelte: true }`. Update `tsconfig.json` extending `.svelte-kit/tsconfig.json`. Create `src/app.html` with `%sveltekit.head%` and `%sveltekit.body%`.

- [ ] **Step 4: Create initial SvelteKit scaffold routes**
  Create `dashboard/src/routes/+layout.ts` (`export const ssr = false;`), minimal `dashboard/src/routes/+layout.svelte` importing `../styles.css`, and minimal `dashboard/src/routes/+page.svelte`.

- [ ] **Step 5: Run toolchain proofs 1.1 through 1.7**
  Run: `npx vp dev` and `npx vp build` (verify `dist/index.html` and `dist/_app/immutable/`).
  Run: `npx vp check` and `npx svelte-check --tsgo --fail-on-warnings`.
  Run: `npx vp test`.
  Expected: All checks pass cleanly.

- [ ] **Step 6: Verify Docker build with prepare script**
  Run: `docker build -t sentinela-dashboard-proof --build-arg VITE_API_URL=http://localhost:8000 dashboard`
  Expected: PASS

- [ ] **Step 7: Commit toolchain setup**
  Run: `git add dashboard/package.json dashboard/package-lock.json dashboard/vite.config.ts dashboard/tsconfig.json dashboard/src/app.html dashboard/src/routes`
  Run: `git commit -m "build(dashboard): scaffold svelte 5 and sveltekit 3 toolchain"`

---

### Task 2: Reactive Polling Utility (`poll.svelte.ts`)

**Files:**
- Create: `dashboard/src/utils/poll.svelte.ts`
- Create: `dashboard/src/utils/poll.test.ts`

**Interfaces:**
- Consumes: Svelte 5 runes (`$state`, `$effect`).
- Produces: `poll<T>(read: (signal: AbortSignal) => Promise<T>, ms: number, describe: (e: unknown) => string)` returning `{ load, reload, update }`.

- [ ] **Step 1: Write unit tests for `poll.svelte.ts`**
  In `dashboard/src/utils/poll.test.ts`, test initial loading state, successful read resolution, interval scheduling, background error preservation of previous data, and `reload`/`update` mutations.

- [ ] **Step 2: Verify tests fail before implementation**
  Run: `npx vp test src/utils/poll.test.ts`
  Expected: FAIL with module not found.

- [ ] **Step 3: Implement `poll.svelte.ts`**
  Implement `poll<T>` in `dashboard/src/utils/poll.svelte.ts` matching Section 4 of the design spec with AbortController handling and automatic timer clearance.

- [ ] **Step 4: Verify tests pass**
  Run: `npx vp test src/utils/poll.test.ts`
  Expected: PASS

- [ ] **Step 5: Type check and lint**
  Run: `npx vp check && npx svelte-check --tsgo --fail-on-warnings`
  Expected: PASS

- [ ] **Step 6: Commit**
  Run: `git add dashboard/src/utils/poll.svelte.ts dashboard/src/utils/poll.test.ts`
  Run: `git commit -m "feat(dashboard): add reactive poll utility in svelte"`

---

### Task 3: Auth Feature & Root Layout (+layout.svelte)

**Files:**
- Create: `dashboard/src/features/auth/SignIn.svelte`
- Modify: `dashboard/src/features/auth/index.ts`
- Modify: `dashboard/src/routes/+layout.svelte`
- Delete: `dashboard/src/features/auth/SignIn.tsx`
- Delete: `dashboard/src/App.tsx`
- Delete: `dashboard/src/main.tsx`

**Interfaces:**
- Consumes: `services/api.ts` (`getMe`), `services/firebase.ts` (`auth`), `SignIn.svelte`.
- Produces: Root auth gating and header tabs (`/`, `/enrollments`, `/staff`).

- [ ] **Step 1: Implement `SignIn.svelte`**
  Port `SignIn.tsx` to `SignIn.svelte` using `$state` for phone, verification code, step, loading, and error. Bind inputs using `bind:value`. Retain plain variable for `RecaptchaVerifier` with cleanup in `onDestroy()`.

- [ ] **Step 2: Update `features/auth/index.ts` barrel**
  Re-export `SignIn.svelte` as `SignIn`.

- [ ] **Step 3: Implement `+layout.svelte`**
  Port `App.tsx` logic to `+layout.svelte`. Subscribe to `onAuthStateChanged` in `onMount`. Implement DAS role verification with Romanian messages:
  - `"Numărul nu este înregistrat. Contactați medicul de familie."`
  - `"Acest număr nu are acces la dispecerat."`
  - `"Autentificarea nu este disponibilă acum. Încercați din nou."`
  Render `<nav class="tabs tabs-box tabs-sm">` with links to `/`, `/enrollments`, and `/staff`, using `aria-current="page"` and `class={["tab", active && "tab-active"]}`. Render children via `{@render children()}`.

- [ ] **Step 4: Remove legacy React auth files**
  Delete `SignIn.tsx`, `App.tsx`, `main.tsx`.

- [ ] **Step 5: Verify checks**
  Run: `npx vp check && npx svelte-check --tsgo --fail-on-warnings`
  Expected: PASS

- [ ] **Step 6: Commit**
  Run: `git add dashboard/src/features/auth dashboard/src/routes/+layout.svelte dashboard/src/App.tsx dashboard/src/main.tsx`
  Run: `git commit -m "feat(dashboard): port sign-in and root layout to svelte"`

---

### Task 4: Feature Components Port (Incidents, Enrollments, Staff) & Routes

**Files:**
- Create: `dashboard/src/features/incidents/IncidentCard.svelte`
- Create: `dashboard/src/features/incidents/IncidentDetails.svelte`
- Create: `dashboard/src/features/incidents/IncidentBoard.svelte`
- Modify: `dashboard/src/features/incidents/index.ts`
- Create: `dashboard/src/features/enrollments/Enrollments.svelte`
- Modify: `dashboard/src/features/enrollments/index.ts`
- Create: `dashboard/src/features/staff/Staff.svelte`
- Modify: `dashboard/src/features/staff/index.ts`
- Modify: `dashboard/src/routes/+page.svelte`
- Create: `dashboard/src/routes/enrollments/+page.svelte`
- Create: `dashboard/src/routes/staff/+page.svelte`
- Delete: `dashboard/src/features/incidents/IncidentCard.tsx`
- Delete: `dashboard/src/features/incidents/IncidentDetails.tsx`
- Delete: `dashboard/src/features/incidents/IncidentBoard.tsx`
- Delete: `dashboard/src/features/enrollments/Enrollments.tsx`
- Delete: `dashboard/src/features/staff/Staff.tsx`
- Delete: `dashboard/index.html`
- Modify: `dashboard/package.json` (remove react, react-dom, @types/react, @types/react-dom, @vitejs/plugin-react)

**Interfaces:**
- Consumes: `services/api.ts`, `utils/poll.svelte.ts`, `utils/labels.ts`, `utils/phone.ts`.
- Produces: Complete DAS dashboard screens mounted on `/`, `/enrollments`, `/staff`.

- [ ] **Step 1: Port Incidents feature**
  Port `IncidentCard.svelte`, `IncidentDetails.svelte` (modal `<dialog>` with `onMount(() => dialogEl.showModal())`), and `IncidentBoard.svelte` using `poll(getIncidents, 15000, describe)`. Update `features/incidents/index.ts`. Mount `IncidentBoard` in `src/routes/+page.svelte`.

- [ ] **Step 2: Port Enrollments feature**
  Port `Enrollments.svelte` using `poll(getEnrollments, 15000, describe)` and Svelte 5 snippets for cards/details. Update `features/enrollments/index.ts`. Mount in `src/routes/enrollments/+page.svelte`.

- [ ] **Step 3: Port Staff feature**
  Port `Staff.svelte` using `poll(getStaff, 15000, describe)` with role assignment form. Update `features/staff/index.ts`. Mount in `src/routes/staff/+page.svelte`.

- [ ] **Step 4: Remove all React components, index.html, and dependencies**
  Remove React `.tsx` files and `index.html`. In `package.json`, remove `react`, `react-dom`, `@types/react`, `@types/react-dom`, and `@vitejs/plugin-react`. Run `npm install` to update `package-lock.json`.

- [ ] **Step 5: Run full checks and build**
  Run: `npx vp check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npx vp build`
  Expected: All checks pass; `dist/` built successfully.

- [ ] **Step 6: Commit**
  Run: `git add dashboard/`
  Run: `git commit -m "feat(dashboard): port incidents, enrollments and staff to svelte 5"`

---

### Task 5: Infrastructure, Git Hooks, and CI Workflows

**Files:**
- Modify: `dashboard/Caddyfile`
- Modify: `dashboard/.dockerignore`
- Modify: `.gitignore`
- Modify: `lefthook.yml`
- Modify: `.github/workflows/dashboard.yml`

**Interfaces:**
- Consumes: SvelteKit immutable assets path, lefthook toolchain.
- Produces: Immutable caching for SvelteKit assets and automated verification in Git hooks and GitHub Actions.

- [ ] **Step 1: Update `dashboard/Caddyfile`**
  Change cache block path from `@assets path /assets/*` to `@assets path /_app/immutable/*`.

- [ ] **Step 2: Update `.dockerignore` and `.gitignore`**
  Add `.svelte-kit` to `dashboard/.dockerignore` and root `.gitignore`.

- [ ] **Step 3: Update `lefthook.yml`**
  Update `dashboard` glob to `*.{ts,js,json,css,html,svelte}` and change execution to a piped group running `npx --no vp check --fix` (with `stage_fixed: true`) followed by `npx --no svelte-check --tsgo --fail-on-warnings`.

- [ ] **Step 4: Update `.github/workflows/dashboard.yml`**
  Add step: `- run: npx svelte-check --tsgo --fail-on-warnings` after `npx vp check`.

- [ ] **Step 5: Test Git hook execution locally**
  Run: `lefthook run pre-commit`
  Expected: All checks succeed.

- [ ] **Step 6: Commit**
  Run: `git add dashboard/Caddyfile dashboard/.dockerignore .gitignore lefthook.yml .github/workflows/dashboard.yml`
  Run: `git commit -m "ci(dashboard): update caddy cache, lefthook and github actions for svelte"`

---

### Task 6: Documentation Updates

**Files:**
- Modify: `dashboard/AGENTS.md`
- Modify: `dashboard/README.md`
- Modify: `AGENTS.md`
- Modify: `README.md`
- Modify: `docs/specs/sentinela/01-architecture.md`
- Modify: `docs/adr/ADR-002-git-hooks.md`

**Interfaces:**
- Consumes: ADR-003 and completed implementation details.
- Produces: Updated repository documentation reflecting the Svelte 5 stack.

- [ ] **Step 1: Update dashboard documentation**
  Update `dashboard/AGENTS.md` and `dashboard/README.md` with the new Svelte 5 / SvelteKit 3 layout, `poll()` utility, `svelte-check` commands, and Tailwind class rules.

- [ ] **Step 2: Update repository root documentation**
  Update root `AGENTS.md` and `README.md` table rows for the dashboard.

- [ ] **Step 3: Update architectural specifications**
  Update `docs/specs/sentinela/01-architecture.md` and append amendment reference in `docs/adr/ADR-002-git-hooks.md`.

- [ ] **Step 4: Verify lint/formatting**
  Run: `npx vp check`
  Expected: PASS

- [ ] **Step 5: Commit**
  Run: `git add dashboard/AGENTS.md dashboard/README.md AGENTS.md README.md docs/specs/sentinela/01-architecture.md docs/adr/ADR-002-git-hooks.md`
  Run: `git commit -m "docs: document dashboard migration to svelte 5 and sveltekit 3"`

---

### Task 7: Full Verification & Parity Acceptance Testing

**Files:**
- Test: Local Docker Compose stack and production image

**Interfaces:**
- Consumes: Running backend API, Postgres DB, and Firebase test authentication.
- Produces: Verified end-to-end functionality across all DAS flows.

- [ ] **Step 1: Build production Docker image**
  Run: `docker build -t sentinela-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard`
  Expected: Image builds successfully.

- [ ] **Step 2: Verify production image asset caching**
  Run container locally and inspect HTTP headers:
  Verify requests to `/_app/immutable/*` return `Cache-Control: public, max-age=31536000, immutable`.
  Verify nonexistent assets return 404.

- [ ] **Step 3: Verify local dev server against Docker Compose**
  Start `docker compose up -d db` and run backend API if needed.
  Verify `http://localhost:5173` with Firebase test numbers:
  - `+40700000001` signs in to DAS, sees navigation tabs and user name; *Ieșire* signs out.
  - `+40700000009` shows unregistered notice.
  - Medic-only number shows "Acest număr nu are acces la dispecerat."
  - Incidents: three columns, claim incident, resolve modal with outcome and note.
  - Enrollments: review and accept.
  - Staff: view roster and add medic/DAS member.
  - Direct reload on `/staff` stays on Staff screen.

- [ ] **Step 4: Final verification check**
  Run: `git status`
  Expected: Working tree clean; all tests and checks passing.
