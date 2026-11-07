# ADR-003: The dashboard moves to Svelte 5 and SvelteKit 3

**Status:** Proposed
**Date:** 2026-10-13
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Builds on:** [ADR-001](ADR-001-monorepo-and-delivery.md) §1 and §2.4; amends [ADR-002](ADR-002-git-hooks.md) for `dashboard/`

## Context

The dashboard is the DAS desk (G15). Today it has four screens: sign-in, incidents, enrollment requests and staff. The specification asks it for much more (UC-12, UC-05, 01 §5, 06 §1 and §3):

| Still to build | Endpoint | What it is on screen |
|---|---|---|
| All active seniors, red first, with code, reason, since when and a "call in progress" badge | `GET /seniors` | Another list re-read on a timer |
| Per senior: call history, full transcripts, address and access details | `GET /seniors/{id}`, `/seniors/{id}/calls`, `/calls/{id}/transcript` | The first screen that wants its own address |
| „Simulează avertizare”, heat or cold | `POST /campaigns` | One form; the demo's trigger |
| Who is on duty | `PUT /staff/on-duty` | One button |
| An audible cue on a new red, the „Pornește alertele sonore” click, a "nobody on duty" warning | none | Derived from the incident list, by comparing each read with the last |
| The home node's room temperature, live on every screen (P20–P22, proposed) | added fields | More data on the same timer |

The forces at play:

1. **The coming screens are timed re-reads and forms.** Every new list repeats the pattern that `IncidentBoard.tsx` and `Enrollments.tsx` already copy line for line: a re-read every few seconds with an `AbortController`, a `Load` union, the last good list kept when a read fails, and a ref so a card can ask for a re-read.
2. **React's wiring is most of the component code.** Measured on 2026-10-13: 36 `useState`, 13 `useEffect`, 9 `useRef`, 8 controlled inputs, and two workarounds that exist only because StrictMode runs effects twice (the `<dialog>` guard, and the reCAPTCHA verifier created on press, auth-layer §7.1).
3. **The code is small now.** About 1,170 lines of components. The other 315 lines (`services/api.ts`, `services/firebase.ts`, `utils/`) use no React and move unchanged. Porting gets more expensive with every screen above.
4. **The team knows Svelte.** Confirmed on 2026-10-13.
5. **UniHack is on 13–15 November (G1).** The port must not change what a dispatcher sees, so the screens above can be built straight after it.
6. **ADR-002 gave the dashboard one command on TypeScript 7.** `vp check` formats, lints and type-checks. Svelte templates are their own language: only `svelte-check` reads them, and it still needs TypeScript 6's JavaScript API.
7. **Sign-in is known only in the browser, after the page loads.** `onAuthStateChanged` decides what `App` shows (auth-layer §7.1), and `apiFetch` needs a signed-in user. Any read that starts before that moment fails.
8. **A dashboard-only change redeploys only `dashboard`** (ADR-001 §1). One component per pull request keeps the other workflows out of its way (§2.4). `api` and its live calls are untouched.

## Decision

**The dashboard moves to Svelte 5 and SvelteKit 3 in single-page mode, with the same screens, Romanian text, DaisyUI classes and API calls.** DaisyUI 5 and Tailwind v4 stay. The framework-free files do not move. `svelte-check` joins `vp check` as a second check command.

### Versions

Current releases on 2026-10-13. `package-lock.json` pins them.

| Package | Version | Note |
|---|---|---|
| `svelte` | 5.57 | |
| `@sveltejs/kit` | 3.0 | Released 2026-10-01. Needs Node 22.17 (the Dockerfile and CI use 26), Vite 8.0.12 and TypeScript 6 |
| `@sveltejs/adapter-static` | 4.0 | |
| `@sveltejs/vite-plugin-svelte` | 7.3 | Vite 8 |
| `svelte-check` | 4.7 | |
| `typescript` | ~6.0 | For `svelte-check`, SvelteKit and the editor. Vite+ accepts 5, 6 or 7 |
| `@typescript/native` | `npm:typescript@7` | The compiler `svelte-check --tsgo` checks with |

Removed: `react`, `react-dom`, `@types/react`, `@types/react-dom`, `@vitejs/plugin-react`.

### Layout

```
dashboard/
├── src/
│   ├── app.html                     replaces index.html: lang="ro", the title, %sveltekit.head% and %sveltekit.body%
│   ├── styles.css                   unchanged; imported by +layout.svelte
│   ├── routes/
│   │   ├── +layout.ts               export const ssr = false
│   │   ├── +layout.svelte           App.tsx: the sign-in gate and the header navigation
│   │   ├── +page.svelte             / : the incident board, today's first tab
│   │   ├── enrollments/+page.svelte
│   │   └── staff/+page.svelte
│   ├── features/                    each .tsx becomes a .svelte in the same folder; index.ts barrels stay
│   ├── services/                    api.ts, firebase.ts: unchanged
│   └── utils/                       labels.ts, phone.ts, phone.test.ts: unchanged; new poll.svelte.ts
├── vite.config.ts
├── tsconfig.json                    extends "$app/tsconfig", include ["src"]
└── package.json
```

- **No `src/lib`.** SvelteKit 3 replaced the `$lib` alias with `#lib`, which needs subpath imports in `package.json` and file extensions on every import. Relative imports, as today, need neither.
- **No `load` functions.** SvelteKit runs `load` before the layout renders, so before sign-in is known (force 7). Screens read from inside their components, as they do now.
- **The incident details stay a modal.** The first page with its own address arrives with the per-senior screen.
- **`main.tsx` and `App.tsx` go away.** SvelteKit owns the root, and `+layout.svelte` holds `App`'s states.

### `vite.config.ts`

```ts
import adapter from "@sveltejs/adapter-static";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { defineConfig } from "vite-plus";

export default defineConfig({
  plugins: [
    tailwindcss(),
    // Single-page mode (ADR-003): dist/index.html serves every route, and the Caddyfile falls back to it.
    // index.html is safe as the fallback because nothing is prerendered.
    sveltekit({ adapter: adapter({ pages: "dist", assets: "dist", fallback: "index.html" }) }),
  ],
  server: { port: 5173 },
  // type checking through tsgolint replaces tsc --noEmit (ADR-002); svelte-check covers .svelte files
  lint: { options: { typeAware: true, typeCheck: true } },
  // Markdown keeps the repository's compact tables; .svelte goes through oxfmt's bundled Svelte printer
  fmt: { ignorePatterns: ["*.md"], svelte: true },
});
```

`pages: "dist"` keeps the Dockerfile's `COPY --from=build /app/dist /srv`. `import.meta.env.VITE_*` works unchanged under SvelteKit, so the Dockerfile's `ARG`s, `.env.example` and `.railway/railway.ts` stay as they are.

### How the React code maps

| React today | Svelte |
|---|---|
| `useState` | `$state` |
| A controlled input: `value` plus `onChange` | `bind:value` |
| The timed re-read, written out in two screens, and the `reload` ref | `poll()` in `utils/poll.svelte.ts`, below |
| The `<dialog>` ref with the StrictMode guard | `bind:this`, and `showModal()` in `onMount` |
| `onAuthStateChanged` in `App`'s effect | The same call in `+layout.svelte`'s `onMount`, which returns the unsubscribe |
| The `RecaptchaVerifier`, created on press and kept in a ref | Created on press and kept in a plain variable; `.clear()` on failure and in `onDestroy` |
| Inner components: `Field`, `Details`, `EnrollmentCard`, `Registration` | Snippets in the same file |
| Callback props: `onChanged`, `onStale`, `onClose` | Unchanged |
| A class built from a template string | `class={["tab", active && "tab-active"]}`, with full class names in quotes. Not the `class:` directive: Tailwind finds only class names it can read whole in the source (dashboard/AGENTS.md) |
| The header's tab buttons | Links in `<nav>`, with `aria-current="page"` on the current one and DaisyUI's `tabs` and `tab` classes for the look. A link is not a `role="tab"` |

### The timed re-read

Written once, for the two screens that re-read today and every list still to come:

```ts
// src/utils/poll.svelte.ts
export type Load<T> =
  | { kind: "loading" }
  // error: the last read failed; the screen keeps the last good data
  | { kind: "ok"; data: T; at: number; error?: string }
  | { kind: "error"; message: string };

/** Reads now and every `ms` until the component goes away (04 §6). Call it while the component is set up. */
export function poll<T>(
  read: (signal: AbortSignal) => Promise<T>,
  ms: number,
  describe: (e: unknown) => string,
): {
  readonly load: Load<T>;
  /** Re-reads at once: after a refused command the data is out of date */
  reload(): void;
  /** Applies a command's answer without waiting for the next read */
  update(change: (data: T) => T): void;
};
```

The incident board's `now`, which ages the "acum N min" labels, is the time of the last good read, `load.at`, as it is today. The interval stays 15 seconds in this change (see "Not in this change").

### Checks

| Check | Tool | Covers |
|---|---|---|
| Format | `vp check`: oxfmt, with `fmt.svelte` | `.ts`, `.css`, `.json`, `.html`, `.svelte` |
| Lint | `vp check`: oxlint, type-aware rules through tsgolint | `.ts`, and the `<script>` of each `.svelte`. No template rules |
| Types | `vp check`: tsgolint | `.ts` files |
| Types, Svelte compiler warnings, accessibility warnings | `svelte-check --tsgo --fail-on-warnings` | `.svelte` and `.ts`. Svelte's own a11y warnings stand in for the template lint rules oxlint lacks |
| Unit tests | `vp test` | `phone.test.ts`, unchanged |

- **Scripts:** `check` becomes `vp check && svelte-check --tsgo --fail-on-warnings`. A new `prepare: svelte-kit sync || echo ''` writes SvelteKit's generated types after `npm ci`. The `|| echo ''` is needed because the Dockerfile's `deps` stage runs `npm ci` before the sources are copied in.
- **Lefthook,** the dashboard job: the glob becomes `*.{ts,js,json,css,html,svelte}`. The job becomes a piped group, like the backend's: `npx --no vp check --fix` with `stage_fixed`, then `npx --no svelte-check --tsgo --fail-on-warnings`.
- **CI,** `dashboard.yml`: one step, `npx svelte-check --tsgo --fail-on-warnings`, after `npx vp check`.
- **No ESLint.** `eslint-plugin-svelte` would bring back typescript-eslint, which ADR-002 force 4 kept out.

### Build and deploy

| File | Change |
|---|---|
| `Dockerfile` | None. `npm run build` writes `dist/` as before |
| `Caddyfile` | The year-long cache moves from `/assets/*` to `/_app/immutable/*`, where SvelteKit puts its hashed files. Without this, those files fall through to `try_files … /index.html`: a missing script would get `index.html` back, which the Caddyfile's own comment rules out |
| `.dockerignore`, root `.gitignore` | Add `.svelte-kit` |
| `compose.yaml` | None. The sync of `./dashboard/src` covers `routes/` and the rest of `src/` |
| `.railway/railway.ts` | None |

### Documents

| File | Change |
|---|---|
| `dashboard/AGENTS.md`, `dashboard/README.md` | Svelte and SvelteKit in place of React; the layout; `svelte-check` in the commands; the Caddy cache path; the class-name rule |
| Root `AGENTS.md`, root `README.md` | The dashboard rows |
| `docs/specs/echocare/01-architecture.md` | The diagram's „DAS desk, React” and the parts table |
| `docs/adr/ADR-002-git-hooks.md` | One line under the header: amended by ADR-003 for `dashboard/` |

The decision log (README G15, the v3 comparison), ADR-001 and auth-layer §7 record what was true when they were written, and stay as they are.

### Not in this change

- The screens and features in the Context table.
- Re-reading every 5 seconds, 2 in demo mode, as 06 §3 asks. The code says 15 today; changing it is its own commit, after this one.
- TanStack Query, a state library, component tests and end-to-end tests.
- The incident details as a page of their own.

## Options considered

### Framework

| Option | Assessment |
|---|---|
| **Svelte 5 (chosen)** | `$state`, `bind:value` and `$effect` cleanups remove most of the wiring in force 2. Reactive state can live in a `.svelte.ts` module and be shared between screens without a library. The team knows it (force 4) |
| Stay on React and extract a `usePoll` hook | Removes the duplication in force 1 with about 30 lines and no port. The forms keep their setter pairs, and shared state still needs context or a library |

### Router

| Option | Assessment |
|---|---|
| **SvelteKit 3 in single-page mode (chosen)** | Official and released with Svelte. File routes. Its config now lives in `vite.config.ts`, next to Vite+'s. It is twelve days old: most examples online still show SvelteKit 2 |
| Plain Vite with `vite-plugin-svelte` and a community router (`@mateothegreat/svelte5-router`, `@keenmate/svelte-spa-router`) | Lighter, with no generated types and no `svelte-kit sync`. Mostly projects with one maintainer each |
| Plain Vite, no router | The header picks a screen from state, as today. Postpones the router to the per-senior screen, but a reload loses the screen |

### UI

| Option | Assessment |
|---|---|
| **DaisyUI 5 on Tailwind v4 (chosen)** | Plain CSS classes: nothing to port, and both themes already work |
| shadcn-svelte (Bits UI) | Accessible headless parts, copied into the repository. Worth it for comboboxes or date pickers, which no screen in the specification needs |
| Skeleton, Flowbite-Svelte | Svelte component kits on Tailwind. A second look to learn, with no gain over DaisyUI for these screens |

### Template checks

| Option | Assessment |
|---|---|
| **`svelte-check --tsgo` (chosen)** | Types and the compiler's a11y warnings in `.svelte` files. Needs TypeScript 6 installed next to 7 |
| `eslint-plugin-svelte` | Template lint rules, but through typescript-eslint, which does not support TypeScript 7 (ADR-002 force 4) |
| Nothing beyond `vp check` | Type errors in templates would surface only in the browser |

## Consequences

**Easier**
- A new list is a `poll()` call and its markup. Forms bind their inputs directly.
- Screens have addresses: `/`, `/enrollments`, `/staff`. A reload keeps the screen, and a link can point to one.
- State that several screens share, such as the incident list the audible cue will watch, can live in a `.svelte.ts` module.

**Harder**
- Two check commands instead of one, and two TypeScript packages in `package.json`.
- oxlint does not read templates. Template mistakes surface through `svelte-check`'s warnings only.
- SvelteKit 3 is new. Examples, answers and AI assistants often show SvelteKit 2 or Svelte 4 syntax; check against svelte.dev.
- `.svelte` formatting runs on oxfmt's Prettier-based path, slower than its native one.

**To revisit**
- A single `--tsgo` mode without TypeScript 6, once `svelte-check` no longer needs its JavaScript API.
- Template lint rules in oxlint, once it reads Svelte templates.
- Reading through SvelteKit's `load` and `invalidate`, if sign-in moves to a step that settles before the first page loads.

## Action items

One pull request from `svelte-migration` to `main`. Every commit passes the hooks.

1. [ ] **Prove the toolchain** before porting anything. Stop and report if one of these fails without a clean fix:
   1. `npm ci` resolves SvelteKit's `vite ^8.0.12` against Vite+'s `vite` package, as it already does for `@vitejs/plugin-react`'s `^8.0.0`.
   2. `npx vp dev` serves the app on 5173. `npx vp build` writes `dist/index.html` and `dist/_app/immutable/`.
   3. `npx vp check` passes with `typeAware` and `typeCheck` on, with an `index.ts` barrel that re-exports a `.svelte` component. **If tsgolint cannot resolve the `.svelte` import,** set `typeCheck: false`: `svelte-check`, which also checks `.ts` files, becomes the only type checker.
   4. `npx vp check --fix` reformats a misformatted `.svelte` file.
   5. `npx svelte-check --tsgo --fail-on-warnings` fails on a type error in a `.svelte` file, and on an accessibility warning.
   6. `npx vp test` runs `phone.test.ts`.
   7. `docker build dashboard` succeeds: `prepare` runs in the `deps` stage with no sources. `docker compose up --watch dashboard` serves on 5173 and reloads on save.
2. [ ] **Port the screens:** the layout with the sign-in gate, `SignIn`, the incident board, card and details, enrollments, staff, and `poll()`. Then remove React.
3. [ ] **Build and deploy files:** the Caddyfile and the ignore files.
4. [ ] **Hooks and CI:** `lefthook.yml` and `dashboard.yml`.
5. [ ] **Documents,** as listed above.
6. [ ] **Check that nothing changed for a dispatcher,** on `localhost:5173` against Compose, signing in with the test numbers of auth-layer §5. A local senior and incident are made through the API and SQL in the local database only:
   - auth-layer §7.2 in full: `+40700000001` signs in; *Ieșire* signs out; `+40700000009` sees the not-registered text; a medic-only number sees „Acest număr nu are acces la dispecerat.”; a reload stays signed in;
   - the incident board: three columns, *Preiau*, *Rezolvă* with an outcome and a note, the message for an incident someone else took, and the details dialog closing on Esc, on the backdrop and on ✕;
   - enrollments: *Vezi cererea*, *Acceptă*, and the message for a second accept;
   - staff: the list, adding a medic and a DAS employee, and the message for a number that already has the role;
   - a reload on `/staff` stays on Personal;
   - the production image (`docker build`, then `docker run`): `/_app/immutable/*` answers with `immutable`, `/staff` loads, and a missing asset is a 404.
