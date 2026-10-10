# AGENTS.md: dashboard

The DAS web dashboard (spec G15): a React + Vite single-page app that calls the FastAPI JSON API and signs people in with Firebase phone sign-in. On Railway it is the `dashboard` service, built by Node and served by Caddy. Setup details: [README.md](README.md).

## Layout

```
dashboard/
├── src/
│   ├── main.tsx       React root
│   ├── App.tsx        header with the API health check, then the board
│   ├── IncidentBoard.tsx  incidents by status, re-read every 15 s (04 §6)
│   ├── api.ts         typed API calls
│   └── styles.css     plain CSS, light and dark
├── index.html         Vite entry
├── vite.config.ts     dev server on 5173
├── tsconfig.json
├── Dockerfile         stages: deps → dev (Compose) → build → Caddy (Railway; keep it last)
├── Caddyfile          SPA fallback to index.html, cache headers
└── package.json       package-lock.json is committed
```

## Scope

- The DAS team's screens: incidents, the red hand-over, live updates. What they show and do is in [02-use-cases.md](../docs/specs/sentinela/02-use-cases.md) and [04-interfaces.md](../docs/specs/sentinela/04-interfaces.md).
- All data comes from the API at `import.meta.env.VITE_API_URL`. No database access and no business rules here; permissions are enforced by FastAPI.
- No router, state library or UI kit yet. Add one with the first feature that needs it, and say so.

## Commands

From `dashboard/`. CI ([dashboard.yml](../.github/workflows/dashboard.yml)) runs `npm ci` and `npm run build`.

| Task | Command |
|---|---|
| Install | `npm ci` |
| Dev server, http://localhost:5173 (API from Compose) | `npm run dev` |
| Type-check and build to `dist/` | `npm run build` |
| Serve the built `dist/` | `npm run preview` |
| Build the production image (from the repo root) | `docker build -t sentinela-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard` |

`npm run build` is the only check: `tsc --noEmit`, then `vite build`. There is no linter or test runner yet.

## Rules

- **`VITE_*` variables are compiled into the bundle.** A change needs a rebuild. Each new one must also be an `ARG` in the Dockerfile's `build` stage and a variable in [.railway/railway.ts](../.railway/railway.ts), or Railway builds without it.
- **`VITE_API_URL` is read by the browser**, so locally it is `http://localhost:8000`, never Compose's `api`.
- **Firebase web config is public**, not a secret. Phone sign-in works only on authorized domains; test with Firebase test numbers, never real SMS.
- **The Caddy stage stays last** in the Dockerfile; Railway builds the last stage.
- Any change under `dashboard/`, this file included, redeploys staging's `dashboard` after merge.
