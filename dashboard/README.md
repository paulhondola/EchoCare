# dashboard: the DAS web dashboard

The dispatch team's view (spec G15): a React + Vite single-page app that calls the FastAPI JSON API and signs people in with Firebase phone sign-in. On Railway it is the `dashboard` service: Node builds it and Caddy serves the result, both in this folder's [Dockerfile](Dockerfile).

## Run it

**In Docker, with the rest of the stack** (from the repository root). Vite reloads on save:

```bash
docker compose up --watch
```

**On the host**, with the API still in Compose. From `dashboard/`:

```bash
npm ci
```

```bash
npm run dev
```

Either way it is at http://localhost:5173.

## Configuration

Vite writes `VITE_*` variables into the bundle **at build time**, so a change needs a rebuild, not a restart. Locally they come from `dashboard/.env`:

```bash
cp .env.example .env
```

| Variable | Value |
|---|---|
| `VITE_API_URL` | `http://localhost:8000` locally. It is read by the browser, so it is never Compose's service name `api` |
| `VITE_FIREBASE_API_KEY`, `VITE_FIREBASE_AUTH_DOMAIN`, `VITE_FIREBASE_PROJECT_ID`, `VITE_FIREBASE_APP_ID` | Firebase console → Project settings → Your apps → the web app. Public identifiers, not secrets |

The same Firebase values are set for staging and production in [.railway/railway.ts](../.railway/railway.ts).

**Firebase phone sign-in works only on authorized domains** (Firebase console → Authentication → Settings → Authorized domains). Add each Railway dashboard domain there. Firebase's docs say `localhost` is not allowed for phone sign-in; if reCAPTCHA fails locally, add `127.0.0.1` and open http://127.0.0.1:5173. Use the Firebase test phone numbers for development, so no real SMS is sent.

## Build and check

`build` type-checks with `tsc` and then builds with Vite. CI runs it ([dashboard.yml](../.github/workflows/dashboard.yml)):

```bash
npm run build
```

```bash
npm run preview
```

## The production image

The last stage of the Dockerfile is the one Railway builds: Caddy serving `dist/` on `$PORT` (3000 when unset). Keep that stage last. The `dev` stage exists only for Compose. To try the production image locally, from the repository root:

```bash
docker build -t sentinela-dashboard --build-arg VITE_API_URL=http://localhost:8000 dashboard
```

```bash
docker run --rm -p 3000:3000 sentinela-dashboard
```

The [Caddyfile](Caddyfile) sends every unknown path to `index.html`, so a reload on a route like `/incidents/42` works. It caches hashed files under `/assets/` for a year and revalidates `index.html` on every load, so a deploy shows at once.

Logs from a deployment:

```bash
railway logs -s dashboard -e staging
```
