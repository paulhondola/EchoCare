# Design: Dashboard Migration to Svelte 5 and SvelteKit 3 (ADR-003)

**Status:** Approved design  
**Date:** 2026-10-13  
**Reference:** [ADR-003](../../adr/ADR-003-dashboard-svelte.md), [ADR-001](../../adr/ADR-001-monorepo-and-delivery.md), [ADR-002](../../adr/ADR-002-git-hooks.md)

---

## 1. Overview & Objectives

This design details the implementation for porting the DAS web dashboard (`dashboard/`) from React 19 to Svelte 5 and SvelteKit 3 in single-page application (SPA) mode, executing the decisions recorded in [ADR-003](../../adr/ADR-003-dashboard-svelte.md).

### 1.1 Goals
- Replace React component boilerplate (`useState`, `useEffect`, `useRef`, StrictMode guards) with Svelte 5 runes (`$state`, `$derived`, `$effect`, `bind:value`) and snippets.
- Centralize timed polling in a reusable, resilient utility (`src/utils/poll.svelte.ts`) to serve existing and upcoming screens.
- Introduce client-side routing via SvelteKit (`/`, `/enrollments`, `/staff`) ensuring URL persistence on reload.
- Preserve 100% functional and visual parity: Romanian copy, DaisyUI 5 styling, Tailwind v4 classes, and API interactions remain identical.
- Maintain a single-command local check workflow leveraging `vp check` and `svelte-check --tsgo --fail-on-warnings`.

### 1.2 Non-Goals (Out of Scope)
- No UI redesigns or new screens (active seniors list, campaign simulation, temperature cards remain future work).
- No reduction of the 15-second polling interval (5-second cadence will be a separate change).
- No SSR, server-side data loaders, or prerendering; Firebase auth is client-only.
- No third-party state management libraries (e.g. TanStack Query, Pinia/Zustand equivalents).

---

## 2. Architecture & File Layout

### 2.1 File Organization

```
dashboard/
├── src/
│   ├── app.html                     replaces index.html: lang="ro", title, %sveltekit.head%, %sveltekit.body%
│   ├── styles.css                   imported by +layout.svelte; Tailwind v4 + DaisyUI 5
│   ├── routes/
│   │   ├── +layout.ts               export const ssr = false;
│   │   ├── +layout.svelte           Root auth gate, header navigation, and screen shell
│   │   ├── +page.svelte             / : IncidentBoard
│   │   ├── enrollments/
│   │   │   └── +page.svelte         /enrollments : Enrollments
│   │   └── staff/
│   │       └── +page.svelte         /staff : Staff
│   ├── features/
│   │   ├── auth/
│   │   │   ├── SignIn.svelte
│   │   │   └── index.ts
│   │   ├── incidents/
│   │   │   ├── IncidentBoard.svelte
│   │   │   ├── IncidentCard.svelte
│   │   │   ├── IncidentDetails.svelte
│   │   │   └── index.ts
│   │   ├── enrollments/
│   │   │   ├── Enrollments.svelte
│   │   │   └── index.ts
│   │   └── staff/
│   │       ├── Staff.svelte
│   │       └── index.ts
│   ├── services/                    api.ts, firebase.ts (unchanged)
│   └── utils/                       labels.ts, phone.ts, phone.test.ts (unchanged)
│       └── poll.svelte.ts           shared reactive timer utility
├── vite.config.ts
├── tsconfig.json
├── package.json
└── package-lock.json
```

- **No `#lib` or `$lib`**: All component and utility imports use relative paths (`./services/api`, `../../utils/poll.svelte`).
- **No `App.tsx` or `main.tsx`**: Removed; SvelteKit mounts the application tree into `%sveltekit.body%`.
- **Framework-free files**: `services/api.ts`, `services/firebase.ts`, `utils/phone.ts`, `utils/labels.ts`, and `styles.css` remain unchanged.

---

## 3. Toolchain & Dependencies

### 3.1 `dashboard/package.json`

- **Remove:** `react`, `react-dom`, `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`.
- **Add DevDependencies:**
  - `svelte`: `^5.57.0`
  - `@sveltejs/kit`: `^3.0.0`
  - `@sveltejs/adapter-static`: `^4.0.0`
  - `@sveltejs/vite-plugin-svelte`: `^7.3.0`
  - `svelte-check`: `^4.7.0`
  - `typescript`: `~6.0.0` (required for SvelteKit and `svelte-check`)
  - `@typescript/native`: `npm:typescript@7` (referenced by `svelte-check --tsgo`)
- **Scripts:**
  - `"dev"`: `"vp dev"`
  - `"build"`: `"vp build"`
  - `"preview"`: `"vp preview"`
  - `"check"`: `"vp check && svelte-check --tsgo --fail-on-warnings"`
  - `"prepare"`: `"svelte-kit sync || echo ''"`

### 3.2 `dashboard/vite.config.ts`

```ts
import adapter from "@sveltejs/adapter-static";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite-plus";

export default defineConfig({
  plugins: [
    tailwindcss(),
    sveltekit({ adapter: adapter({ pages: "dist", assets: "dist", fallback: "index.html" }) }),
  ],
  server: { port: 5173 },
  lint: { options: { typeAware: true, typeCheck: true } },
  fmt: { ignorePatterns: ["*.md"], svelte: true },
});
```

*Note on type checking:* If tsgolint cannot resolve `.svelte` barrel exports, `typeCheck: false` is configured for `vp check` while `svelte-check` serves as the authoritative type checker.

### 3.3 `dashboard/tsconfig.json`

```json
{
  "extends": "./.svelte-kit/tsconfig.json",
  "compilerOptions": {
    "allowJs": true,
    "checkJs": true,
    "esModuleInterop": true,
    "forceConsistentCasingInFileNames": true,
    "resolveJsonModule": true,
    "skipLibCheck": true,
    "sourceMap": true,
    "strict": true,
    "moduleResolution": "bundler"
  },
  "include": ["src/**/*"]
}
```

### 3.4 `dashboard/src/app.html`

```html
<!doctype html>
<html lang="ro">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <link rel="icon" type="image/svg+xml" href="/vite.svg" />
    <title>Sentinela DAS</title>
    %sveltekit.head%
  </head>
  <body class="min-h-screen bg-base-200 text-base-content antialiased">
    <div style="display: contents">%sveltekit.body%</div>
  </body>
</html>
```

---

## 4. Polling Utility Specification (`src/utils/poll.svelte.ts`)

```ts
export type Load<T> =
  | { kind: "loading" }
  | { kind: "ok"; data: T; at: number; error?: string }
  | { kind: "error"; message: string };

export function poll<T>(
  read: (signal: AbortSignal) => Promise<T>,
  ms: number,
  describe: (e: unknown) => string,
): {
  readonly load: Load<T>;
  reload(): void;
  update(change: (data: T) => T): void;
} {
  let load = $state<Load<T>>({ kind: "loading" });
  let controller: AbortController | null = null;
  let timer: ReturnType<typeof setTimeout> | null = null;
  let active = true;

  async function execute() {
    if (timer) clearTimeout(timer);
    if (controller) controller.abort();
    controller = new AbortController();

    try {
      const data = await read(controller.signal);
      if (!active) return;
      load = { kind: "ok", data, at: Date.now() };
    } catch (err) {
      if (!active || (err instanceof DOMException && err.name === "AbortError")) return;
      const message = describe(err);
      if (load.kind === "ok") {
        load = { ...load, error: message };
      } else {
        load = { kind: "error", message };
      }
    } finally {
      if (active) {
        timer = setTimeout(execute, ms);
      }
    }
  }

  $effect(() => {
    active = true;
    void execute();
    return () => {
      active = false;
      if (timer) clearTimeout(timer);
      if (controller) controller.abort();
    };
  });

  return {
    get load() {
      return load;
    },
    reload() {
      void execute();
    },
    update(change: (data: T) => T) {
      if (load.kind === "ok") {
        load = { ...load, data: change(load.data) };
      }
    },
  };
}
```

---

## 5. Screen & Feature Specifications

### 5.1 Root Layout (`src/routes/+layout.svelte`)
- Implements `onMount` registering `onAuthStateChanged(auth, ...)`.
- Verifies DAS access via `getMe()`:
  - If unregistered (`"not_registered"`), signs out and displays `"Numărul nu este înregistrat. Contactați medicul de familie."`.
  - If missing DAS role (e.g. medic only), signs out and displays `"Acest număr nu are acces la dispecerat."`.
  - If network or API unavailable, displays `"Autentificarea nu este disponibilă acum. Încercați din nou."`.
- Renders header tab navigation using DaisyUI `tabs tabs-box tabs-sm` and `class={["tab", active && "tab-active"]}`:
  - `/` (Incidente)
  - `/enrollments` (Cereri de înrolare)
  - `/staff` (Personal)
- Body renders route content using `{@render children()}`.

### 5.2 Sign In (`src/features/auth/SignIn.svelte`)
- State variables managed via `$state`: `step`, `phone`, `code`, `loading`, `error`, `confirmationResult`.
- Inputs bound with `bind:value`.
- `RecaptchaVerifier` stored in local variable; cleanup executed on error and inside `onDestroy()`.

### 5.3 Incident Management (`src/features/incidents/`)
- **`IncidentBoard.svelte`**:
  - Uses `poller = poll(getIncidents, 15000, describe)`.
  - Calculates relative time elapsed against `poller.load.at`.
  - Groups items into three visual columns: *Deschise*, *În lucru*, *Rezolvate*.
- **`IncidentCard.svelte`**:
  - Emits `onTake` and `onSelect` callback events.
- **`IncidentDetails.svelte`**:
  - Native `<dialog bind:this={dialogEl} class="modal">` opened via `dialogEl.showModal()` in `onMount`.
  - Dispatches `onClose` when dismissed via backdrop, Esc, or close button.
  - Submits resolution via `resolveIncident(id, { outcome, note })` and triggers `onResolved`.

### 5.4 Enrollments (`src/features/enrollments/Enrollments.svelte`)
- Uses `poll(getEnrollments, 15000, describe)`.
- Cards and detail views implemented via Svelte 5 snippets (`{#snippet card(item)}`).
- "Acceptă" action invokes `acceptEnrollment(id)` and updates poller.

### 5.5 Staff (`src/features/staff/Staff.svelte`)
- Uses `poll(getStaff, 15000, describe)`.
- Renders table with role badges and an inline form to add members with roles (`das`, `medic`).
- Form handles conflict error responses with matching Romanian text and triggers `poller.reload()`.

---

## 6. Build, Deployment, CI & Hooks

1. **Caddy Cache:**
   - In `dashboard/Caddyfile`, update `@assets path /assets/*` to `@assets path /_app/immutable/*`.
2. **Git Ignore:**
   - Append `.svelte-kit` to `dashboard/.dockerignore` and root `.gitignore`.
3. **Lefthook (`lefthook.yml`):**
   - Update `dashboard` glob to `*.{ts,js,json,css,html,svelte}`.
   - Run piped group: `npx --no vp check --fix` (with `stage_fixed: true`) followed by `npx --no svelte-check --tsgo --fail-on-warnings`.
4. **CI Workflow (`.github/workflows/dashboard.yml`):**
   - Add step: `run: npx svelte-check --tsgo --fail-on-warnings` after `npx vp check`.
5. **Documentation:**
   - Update `dashboard/AGENTS.md`, `dashboard/README.md`, root `AGENTS.md`, root `README.md`, `docs/specs/sentinela/01-architecture.md`, and `docs/adr/ADR-002-git-hooks.md`.

---

## 7. Verification & Acceptance Criteria

1. **Toolchain Gates (ADR-003 Action Item 1):**
   - `npm ci` installs clean dependencies.
   - `npx vp dev` and `npx vp build` complete without errors.
   - `npx vp check` and `npx svelte-check --tsgo --fail-on-warnings` pass cleanly.
   - `npx vp test` runs `phone.test.ts` successfully.
   - `docker build dashboard` produces a working production image.
2. **Dispatcher Workflow Acceptance:**
   - Auth flows match `auth-layer §7.2` for test numbers (`+40700000001`, unregistered numbers, and medic-only numbers).
   - Incidents, Enrollments, and Staff screens function with live API mutations.
   - Direct navigation and reloads on `/`, `/enrollments`, and `/staff` maintain proper active screen state.
   - Static assets under `/_app/immutable/` serve with `Cache-Control: public, max-age=31536000, immutable`.
