# AGENTS.md: dashboard

The DAS web dashboard (spec G15): a Svelte 5 + SvelteKit 3 single-page app ([ADR-003](../docs/adr/ADR-003-dashboard-svelte.md)) that calls the FastAPI JSON API and signs people in with Firebase phone sign-in. On Railway it is the `dashboard` service, built by Node and served by Caddy. Setup details: [README.md](README.md).

## Layout

```
dashboard/
├── src/
│   ├── app.html                     SvelteKit root template
│   ├── styles.css                   Tailwind v4 + DaisyUI 5 entry, light and dark themes
│   ├── routes/
│   │   ├── +layout.ts               export const ssr = false;
│   │   ├── +layout.svelte           Root auth gate (auth-layer §7.1) and header navigation
│   │   ├── +page.svelte             / : IncidentBoard
│   │   ├── enrollments/
│   │   │   └── +page.svelte         /enrollments : Enrollments (UC-04)
│   │   └── staff/
│   │       └── +page.svelte         /staff : Staff (UC-14)
│   ├── features/                    domain feature components
│   │   ├── auth/                    SignIn.svelte: phone step, code step; invisible reCAPTCHA
│   │   ├── incidents/               IncidentBoard, IncidentCard, IncidentDetails modal
│   │   ├── enrollments/             Enrollments: review and Acceptă
│   │   └── staff/                   Staff: member list and adding medic or DAS
│   ├── services/                    apiFetch, getMe, Firebase auth
│   │   ├── api.ts
│   │   └── firebase.ts
│   ├── utils/                       formatting and helpers
│   │   ├── phone.ts                 typed number → E.164, with phone.test.ts
│   │   ├── labels.ts                shared Romanian labels, date format and address line
│   │   └── poll.svelte.ts           shared reactive timer utility (04 §6), with poll.test.ts
│   └── vite.config.ts               Vite+: SvelteKit SPA adapter, Tailwind v4, lint, fmt
├── tsconfig.json                    extends "$app/tsconfig"
├── Dockerfile                       stages: deps → dev (Compose) → build → Caddy (Railway; keep it last)
├── Caddyfile                        SPA fallback to index.html, immutable asset cache
└── package.json                     package-lock.json is committed
```

## Scope

- The DAS team's screens: incidents, the red hand-over, live updates. What they show and do is in [02-use-cases.md](../docs/specs/sentinela/02-use-cases.md) and [04-interfaces.md](../docs/specs/sentinela/04-interfaces.md).
- All data comes from the API at `import.meta.env.VITE_API_URL`. No database access and no business rules here; permissions are enforced by FastAPI.
- Styling is Tailwind v4 (`@tailwindcss/vite`) with DaisyUI 5 components (`btn`, `card`, `badge`, `alert`). Use DaisyUI's semantic colours (`error`, `warning`, `success`, `base-*`) so both themes work, and write full class names in quotes (e.g. `class={["tab", active && "tab-active"]}`): Tailwind only finds classes it can read whole in the source.
- Single-page application mode with SvelteKit 3: no `load` functions; all reads run client-side inside components after sign-in via `poll()` in `src/utils/poll.svelte.ts`. Relative imports are used instead of `#lib` or `$lib`.

## Commands

From `dashboard/`. CI ([dashboard.yml](../.github/workflows/dashboard.yml)) runs `npm ci`, `npx vp check`, `npx svelte-check --tsgo --fail-on-warnings` and `npm run build`.

| Task | Command |
|---|---|
| Install | `npm ci` |
| Dev server, http://localhost:5173 (API from Compose) | `npm run dev` |
| Format, lint and type-check / fix | `npm run check` / `npx vp check --fix` |
| Svelte diagnostics check | `npx svelte-check --tsgo --fail-on-warnings` |
| Unit tests | `npx vp test` |
| Build to `dist/` | `npm run build` |
| Serve the built `dist/` | `npm run preview` |
| Build the production image (from the repo root) | `docker build -t sentinela-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard` |

The toolchain is Vite+ ([ADR-002](../docs/adr/ADR-002-git-hooks.md), [ADR-003](../docs/adr/ADR-003-dashboard-svelte.md)): `vp check` runs oxfmt, oxlint and a type check through tsgolint, while `svelte-check --tsgo` covers `.svelte` template types and accessibility warnings.

## Rules

- **`VITE_*` variables are compiled into the bundle.** A change needs a rebuild. Each new one must also be an `ARG` in the Dockerfile's `build` stage and a variable in [.railway/railway.ts](../.railway/railway.ts), or Railway builds without it.
- **`VITE_API_URL` is read by the browser**, so locally it is `http://localhost:8000`, never Compose's `api`.
- **Firebase web config is public**, not a secret. Phone sign-in works only on authorized domains; test with Firebase test numbers, never real SMS.
- **The Caddy stage stays last** in the Dockerfile; Railway builds the last stage.
- **Lefthook owns the Git hooks**, for the whole repository. Run `vp config` and `vp migrate` only with `--no-hooks`: Vite+'s hooks set `core.hooksPath`, which silently turns lefthook off. To undo that, run `npx vp hooks disable`, then `lefthook install`.
- **`vite` is Vite+'s build of it** (`npm:@voidzero-dev/vite-plus-core`), forced by `overrides` in `package.json`. Keep both entries on the same version as `vite-plus`.
- Any change under `dashboard/`, this file included, redeploys staging's `dashboard` after merge.
