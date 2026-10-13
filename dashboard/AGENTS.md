# AGENTS.md: dashboard

The DAS web dashboard (spec G15): a React + Vite single-page app that calls the FastAPI JSON API and signs people in with Firebase phone sign-in. On Railway it is the `dashboard` service, built by Node and served by Caddy. Setup details: [README.md](README.md).

## Layout

```
dashboard/
├── src/
│   ├── main.tsx       React root
│   ├── App.tsx        what to show, from the Firebase user and GET /api/me (auth-layer §7.1)
│   ├── features/      domain feature components and screens
│   │   ├── auth/          SignIn: phone step, code step; invisible reCAPTCHA
│   │   ├── incidents/     IncidentBoard, IncidentCard, IncidentDetails modal
│   │   ├── enrollments/   Enrollments: review and Acceptă (UC-04)
│   │   └── staff/         Staff: member list and adding medic or DAS (UC-14)
│   ├── services/      apiFetch, getMe, Firebase auth
│   │   ├── api.ts
│   │   └── firebase.ts
│   ├── utils/         formatting and helpers
│   │   ├── phone.ts       typed number → E.164, with phone.test.ts
│   │   └── labels.ts      shared Romanian labels, date format and address line
│   └── styles.css     Tailwind v4 + DaisyUI 5 entry, light and dark themes
├── index.html         Vite entry
├── vite.config.ts     Vite+: dev server on 5173, lint (with type check), fmt
├── tsconfig.json
├── Dockerfile         stages: deps → dev (Compose) → build → Caddy (Railway; keep it last)
├── Caddyfile          SPA fallback to index.html, cache headers
└── package.json       package-lock.json is committed
```

## Scope

- The DAS team's screens: incidents, the red hand-over, live updates. What they show and do is in [02-use-cases.md](../docs/specs/sentinela/02-use-cases.md) and [04-interfaces.md](../docs/specs/sentinela/04-interfaces.md).
- All data comes from the API at `import.meta.env.VITE_API_URL`. No database access and no business rules here; permissions are enforced by FastAPI.
- Styling is Tailwind v4 (`@tailwindcss/vite`) with DaisyUI 5 components (`btn`, `card`, `badge`, `alert`). Use DaisyUI's semantic colours (`error`, `warning`, `success`, `base-*`) so both themes work, and write full class names: Tailwind only finds classes it can read in the source.
- No router or state library yet. Add one with the first feature that needs it, and say so.

## Commands

From `dashboard/`. CI ([dashboard.yml](../.github/workflows/dashboard.yml)) runs `npm ci`, `npx vp check` and `npm run build`.

| Task | Command |
|---|---|
| Install | `npm ci` |
| Dev server, http://localhost:5173 (API from Compose) | `npm run dev` |
| Format, lint and type-check / fix | `npx vp check` / `npx vp check --fix` |
| Build to `dist/` | `npm run build` |
| Serve the built `dist/` | `npm run preview` |
| Build the production image (from the repo root) | `docker build -t sentinela-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard` |

The toolchain is Vite+ ([ADR-002](../docs/adr/ADR-002-git-hooks.md)): `vp check` runs oxfmt, oxlint and a type check through tsgolint, all configured in `vite.config.ts`. `npm run build` no longer type-checks. Vitest is bundled (`npx vp test`); CI does not run it yet.

## Rules

- **`VITE_*` variables are compiled into the bundle.** A change needs a rebuild. Each new one must also be an `ARG` in the Dockerfile's `build` stage and a variable in [.railway/railway.ts](../.railway/railway.ts), or Railway builds without it.
- **`VITE_API_URL` is read by the browser**, so locally it is `http://localhost:8000`, never Compose's `api`.
- **Firebase web config is public**, not a secret. Phone sign-in works only on authorized domains; test with Firebase test numbers, never real SMS.
- **The Caddy stage stays last** in the Dockerfile; Railway builds the last stage.
- **Lefthook owns the Git hooks**, for the whole repository. Run `vp config` and `vp migrate` only with `--no-hooks`: Vite+'s hooks set `core.hooksPath`, which silently turns lefthook off. To undo that, run `npx vp hooks disable`, then `lefthook install`.
- **`vite` is Vite+'s build of it** (`npm:@voidzero-dev/vite-plus-core`), forced by `overrides` in `package.json`. Keep both entries on the same version as `vite-plus`.
- Any change under `dashboard/`, this file included, redeploys staging's `dashboard` after merge.
