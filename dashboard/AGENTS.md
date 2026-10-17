# AGENTS.md: dashboard

The DAS web dashboard (spec G15): a Svelte 5 + SvelteKit 3 single-page app ([ADR-003](../docs/adr/ADR-003-dashboard-svelte.md)) that calls the FastAPI JSON API and signs people in with Firebase phone sign-in. On Railway it is the `dashboard` service, built by Node and served by Caddy. Setup details: [README.md](README.md).

## Layout

```
dashboard/
├── src/
│   ├── app.html                     SvelteKit root template
│   ├── styles.css                   Tailwind v4 + DaisyUI 5 entry: the dark `echocare` theme, spec 07 tokens, sn-* classes, @font-face
│   ├── fonts/                       Archivo and JetBrains Mono, self-hosted woff2 cut from the Android app's fonts, with their OFL licences
│   ├── routes/
│   │   ├── +layout.ts               export const ssr = false;
│   │   ├── +layout.svelte           Root auth gate (auth-layer §7.1); signed in, renders the Shell
│   │   ├── +page.svelte             / : IncidentBoard
│   │   ├── seniors/
│   │   │   └── +page.svelte         /seniors : Seniors, Monitorizare seniori
│   │   ├── enrollments/
│   │   │   └── +page.svelte         /enrollments : Enrollments (UC-04)
│   │   ├── staff/
│   │   │   └── +page.svelte         /staff : Staff (UC-14)
│   │   └── campaigns/
│   │       └── +page.svelte         /campaigns : Campaigns, Campanii meteo
│   ├── features/                    domain feature components
│   │   ├── shell/                   Shell (Cod Roșu banner and incident dossier over every page), Sidebar, PageHeader; live.svelte.ts polls once for every page; siren.ts
│   │   ├── auth/                    SignIn.svelte: phone step, code step; invisible reCAPTCHA
│   │   ├── incidents/               IncidentBoard (board and table), IncidentCard, RedAlert (the Cod Roșu banner), IncidentDetails slide-over
│   │   ├── seniors/                 Seniors table with CSV export, SeniorDetails slide-over
│   │   ├── enrollments/             Enrollments: review and Acceptă
│   │   ├── staff/                   Staff: member list, who is on duty, adding medic or DAS
│   │   ├── campaigns/               Campaigns: start a weather campaign, progress per campaign, Încheie
│   │   └── system/                  SystemHealthIndicator: the sidebar's system line
│   ├── ui/                          presentational pieces with no data: Icon.svelte (Lucide), Brand.svelte, CopyButton.svelte
│   ├── services/                    apiFetch, getMe, Firebase auth
│   │   ├── api.ts
│   │   └── firebase.ts
│   ├── utils/                       formatting and helpers
│   │   ├── phone.ts                 typed number → E.164 and back for display, with phone.test.ts
│   │   ├── labels.ts                shared Romanian labels, tones, date formats and address line
│   │   ├── incidents.ts             board columns, filter, relative times, with incidents.test.ts
│   │   ├── campaigns.ts             campaign labels and progress counts, with campaigns.test.ts
│   │   ├── csv.ts                   CSV text and download, with csv.test.ts
│   │   └── poll.svelte.ts           shared reactive timer utility (04 §6), with poll.test.ts
│   └── vite.config.ts               Vite+: SvelteKit SPA adapter, Tailwind v4, lint, fmt
├── tsconfig.json                    extends "$app/tsconfig"
├── Dockerfile                       stages: deps → dev (Compose) → build → Caddy (Railway; keep it last)
├── Caddyfile                        SPA fallback to index.html, immutable asset cache
└── package.json                     package-lock.json is committed
```

## Scope

- The DAS team's screens: incidents, the red hand-over, live updates. What they show and do is in [02-use-cases.md](../docs/specs/echocare/02-use-cases.md) and [04-interfaces.md](../docs/specs/echocare/04-interfaces.md).
- All data comes from the API at `import.meta.env.VITE_API_URL`. No database access and no business rules here; permissions are enforced by FastAPI.
- Styling is Tailwind v4 (`@tailwindcss/vite`) on the design in [07-dashboard-stitch-spec.md](../docs/specs/echocare/07-dashboard-stitch-spec.md): one dark theme, square corners, 2px section rules, flush-left button labels, Archivo with JetBrains Mono for ids, times and numbers. Take colours from the tokens in `styles.css` (`canvas`, `subtle`, `card`, `line`, `fg-muted`, `link`, and `rosu`, `galben`, `verde` for the codes), buttons from `sn-btn` and its variants, and icons from `ui/Icon.svelte`. DaisyUI 5 stays for inputs, spinners and modals, themed to match. Write full class names in quotes (e.g. `class={["tab", active && "tab-active"]}`): Tailwind only finds classes it can read whole in the source.
- Single-page application mode with SvelteKit 3: no `load` functions; all reads run client-side after sign-in. The Shell polls incidents, seniors, enrollments, staff and health once through `poll()` (`src/utils/poll.svelte.ts`) and pages read them with `getLive()`, so the sidebar's counters and the pages share each read. Relative imports are used instead of `#lib` or `$lib`.

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
| Build the production image (from the repo root) | `docker build -t echocare-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard` |

The toolchain is Vite+ ([ADR-002](../docs/adr/ADR-002-git-hooks.md), [ADR-003](../docs/adr/ADR-003-dashboard-svelte.md)): `vp check` runs oxfmt, oxlint and a type check through tsgolint, while `svelte-check --tsgo` covers `.svelte` template types and accessibility warnings.

## Rules

- **`VITE_*` variables are compiled into the bundle.** A change needs a rebuild. Each new one must also be an `ARG` in the Dockerfile's `build` stage and a variable in [.railway/railway.ts](../.railway/railway.ts), or Railway builds without it.
- **`VITE_API_URL` is read by the browser**, so locally it is `http://localhost:8000`, never Compose's `api`.
- **Firebase web config is public**, not a secret. Phone sign-in works only on authorized domains; test with Firebase test numbers, never real SMS.
- **The Caddy stage stays last** in the Dockerfile; Railway builds the last stage.
- **Lefthook owns the Git hooks**, for the whole repository. Run `vp config` and `vp migrate` only with `--no-hooks`: Vite+'s hooks set `core.hooksPath`, which silently turns lefthook off. To undo that, run `npx vp hooks disable`, then `lefthook install`.
- **`vite` is Vite+'s build of it** (`npm:@voidzero-dev/vite-plus-core`), forced by `overrides` in `package.json`. Keep both entries on the same version as `vite-plus`.
- Any change under `dashboard/`, this file included, redeploys staging's `dashboard` after merge.
