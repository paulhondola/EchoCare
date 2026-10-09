# ADR-001: One repository, native toolchains, two Railway environments

**Status:** Proposed
**Date:** 2026-10-09
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Builds on:** [Sentinela specification](../specs/sentinela/README.md), mainly G1, G2, G3, G5, G9, G15 and spike S8

## Context

The repository holds only the specification today. Before code is written (G1 allows it before UniHack 8, 13–15 November 2026), the team must decide where each part lives and how it reaches its users.

There are four deliverables, in three ecosystems, reaching people by three different routes:

| Part | Ecosystem | Reaches its users by | Spec |
|---|---|---|---|
| FastAPI service | Python, uv, SQLAlchemy, Alembic | Railway deploy from Git, automatic | 01 §9 |
| DAS web dashboard | TypeScript, React, Vite | Railway static-site service, automatic | G15 |
| Android app, four roles | Kotlin, Gradle | An APK installed on each demo device by a person | G3 |
| Wear OS app | Kotlin, Gradle | An APK installed on the watch by a person | G5 |

The forces at play:

1. **One contract, three clients.** The dashboard and the Android app call the same JSON API (04 §0). A change to the API affects both.
2. **Two delivery speeds.** Railway redeploys the API minutes after a merge. An Android device keeps running its old APK until someone installs the new one. For a few hours or days, an old app will be talking to a new API.
3. **The phone and the watch must match.** The Wear OS Data Layer (channel 1) delivers messages only between apps with the **same package name and the same signing certificate**. Firebase phone sign-in on Android checks the **SHA fingerprints of the signing key**. Installing a new build over an old one also needs the same key.
4. **Deploys drop live calls** (01 §9, 06 §1). Anything that deploys the API by accident, such as a dashboard change or an Android change, costs calls.
5. **Four people, five weeks.** Each tool added is one more thing that can break on Friday night.
6. **Course reuse (G1).** Two courses want a mobile app that uses hardware sensors. They may ask for the Android code on its own.

## Decision

**One Git repository with one folder per deliverable, each built by its own native tool. No monorepo build orchestrator.** Each part has its own GitHub Actions workflow, which runs only when that part's files change. Railway has two persistent environments, `staging` following `main` and `production` following `release`. Android builds are tied to those environments by build type, and all of them are signed with one shared key.

### Layout

```
sentinela/
├── backend/                     FastAPI service. Railway root directory /backend
│   ├── app/
│   │   ├── engine/              rules and status engine, pure (01 §8)
│   │   └── …                    identity, api, intake, voice, session, scheduler, notifier, store
│   ├── alembic/
│   ├── scripts/grant_das.py     the setup script (G6), run inside the api container
│   ├── tests/
│   ├── openapi.json             committed snapshot of the contract
│   ├── Dockerfile
│   ├── pyproject.toml, uv.lock
│   └── railway.toml
├── dashboard/                   React + Vite. Railway root directory /dashboard
│   ├── src/api/schema.d.ts      generated from backend/openapi.json, committed
│   ├── package.json
│   ├── Dockerfile               Node build stage, Caddy serve stage
│   ├── Caddyfile
│   └── railway.toml
├── android/                     ONE Gradle build for phone and watch
│   ├── settings.gradle.kts      include(":app", ":wear", ":shared")
│   ├── gradle/libs.versions.toml
│   ├── app/                     phone and tablet, four roles; google-services.json
│   ├── wear/                    Wear OS app
│   └── shared/                  plain Kotlin: Data Layer paths, event and check-in types,
│                                watch threshold logic (no Android imports)
├── docs/
├── compose.yaml                 local Postgres, API, dashboard dev server, tunnel; Railway ignores it
├── .github/
│   ├── CODEOWNERS
│   └── workflows/  backend.yml  dashboard.yml  android.yml  android-release.yml
└── README.md
```

Three choices in this layout are deliberate:

- **`android/` is one Gradle build containing both apps.** The phone and the watch share `applicationId`, the signing config, `versionCode` and the `:shared` message types in one place, so they cannot drift apart (force 3).
- **The threshold logic and the message types live in `:shared`, as plain Kotlin.** The watch tests in 06 §5 ("the threshold logic fed synthetic readings") then run as JVM unit tests in CI, with no emulator.
- **The generated TypeScript types are committed inside `dashboard/`.** Railway's dashboard service pulls only `/dashboard`, so its build cannot read `../backend/openapi.json`.

## Options considered

### Option A: One repository, native toolchains, path-filtered workflows (proposed)

| Dimension | Assessment |
|---|---|
| Complexity | Low. Each folder is a normal Python, Vite or Gradle project. The only shared parts are the workflows and CODEOWNERS |
| Cost | Free on GitHub Actions at this size. Path filters keep backend-only changes from paying for a Gradle build |
| Scalability | Enough for a team of four and a pilot rewrite (G1). Railway supports this "isolated monorepo" shape directly |
| Team familiarity | High. Gradle for the Android people, uv or pip for the backend, npm for the dashboard. Nothing new to learn |

**Pros:** an API change, the client changes it needs and the spec change go in one pull request. One place for issues and the decision log. `openapi.json` changes show up in the diffs the client owners review. `git subtree split --prefix android` produces a standalone repository, with history, for the courses.
**Cons:** the Actions setup needs care, since path filters interact badly with required checks and with Wait for CI (see the trade-off analysis). One repository means one permission set for everyone.

### Option B: Separate repositories (backend, dashboard, android)

| Dimension | Assessment |
|---|---|
| Complexity | Low per repository, higher overall: three CI setups, three issue lists, and the spec in a fourth place or copied |
| Cost | Same |
| Scalability | Suits separate teams with separate release schedules, which this project does not have |
| Team familiarity | High |

**Pros:** the CI of each repository is trivial, with no path filters. Course submission is just the android repository.
**Cons:** the contract lives in one repository and its clients in two others, so a breaking API change is invisible to the people it breaks. A feature like "add an incident outcome" becomes three coordinated pull requests during a 48-hour event. The decision log drifts away from the code.

### Option C: One repository with a build orchestrator (Nx, Turborepo, moon, Bazel)

| Dimension | Assessment |
|---|---|
| Complexity | High. Turborepo and Nx are JavaScript-centric. Bazel can build Python, Node and Android, but nobody on the team runs it |
| Cost | Setup time measured in days |
| Scalability | Best in class for large monorepos, which this is not |
| Team familiarity | Low |

**Pros:** caching across tasks and "only build what changed", worked out from the dependency graph.
**Cons:** the three ecosystems share no build graph, so the orchestrator would mostly run `./gradlew` and `uv run` with extra steps. Path filters give the "only what changed" benefit for free.

## Trade-off analysis

### 1. Railway in a monorepo

Each Railway service is one folder of the repository:

| Service | Root directory | Watch paths | Config file |
|---|---|---|---|
| `api` | `/backend` | `/backend/**` | `/backend/railway.toml` |
| `dashboard` | `/dashboard` | `/dashboard/**` | `/dashboard/railway.toml` |
| `postgres` | n/a (Railway's database) | n/a | n/a |

Watch paths are what make the monorepo safe for live calls (force 4). Without them, any commit, including an Android one or a change to a `.md` file, redeploys the API and drops every call in progress. Two details matter. Watch paths match from the repository root even when a root directory is set. The config file path must be absolute, because it does not follow the root directory.

**Environments.**

| Environment | Follows branch | Who uses it | Database |
|---|---|---|---|
| `staging` | `main` | Developers, team test calls, Android debug builds | Its own Postgres, test data |
| `production` | `release` | The demo, Android release builds | Its own Postgres, the demo's fictitious seniors |

Promoting is a fast-forward: `git push origin main:release`. The Sunday-morning freeze (06 §8) becomes a rule on the `release` branch: nobody pushes to it after the freeze, and a GitHub ruleset can enforce that.

**Why not Railway PR environments, for now.** They would give each pull request its own API, dashboard and empty database. Three things get in the way:
- The dashboard's Firebase phone sign-in only works on domains authorized in Firebase, and PR environments get a new random domain each time.
- Android builds are tied to a fixed address, so they cannot reach a PR environment.
- Every PR environment that runs a test campaign dials real phones from the shared Twilio number.

Revisit after the hackathon, if needed, with "Focused PR environments" so that only the changed services deploy.

**Twilio works with both environments without changing the number's configuration.** Every call is outbound, and each call carries its own answer and status addresses (04 §4.1), so each environment receives its own callbacks.

**Variables tie the services together**, using Railway's references to other services:

| Variable | On | Value |
|---|---|---|
| `DATABASE_URL` | `api` | `${{postgres.DATABASE_URL}}`, private network |
| `ALLOWED_ORIGIN` | `api` | `https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}` (the single CORS origin, 01 §4 channel 3) |
| `PUBLIC_BASE_URL` | `api` | `https://${{api.RAILWAY_PUBLIC_DOMAIN}}`, used for Twilio addresses and for checking Twilio's signature |
| `VITE_API_URL` | `dashboard` | `https://${{api.RAILWAY_PUBLIC_DOMAIN}}`. Vite writes it into the bundle at build time, so changing it means rebuilding |
| `DEMO_MODE` | `api` | On in every environment for the hackathon (06 §3); per-environment values are in "Three environments" below |

**Twilio's signature check behind Railway's proxy.** Twilio signs the public `https://…` address. Inside the container, the request arrives as plain `http` on an internal host, so a check against the address the request arrived at fails on every callback. Build the address from `PUBLIC_BASE_URL` plus the path, and run uvicorn with `--proxy-headers`. Test this in spike S1.

#### Where each Railway service comes from

Two services are built from this repository and one is not:

| Service | Source | Railway builds it with | Runs as |
|---|---|---|---|
| `api` | GitHub repository, root directory `/backend` | `backend/Dockerfile` | One container: uvicorn on `$PORT`, public domain, `/health` |
| `dashboard` | GitHub repository, root directory `/dashboard` | `dashboard/Dockerfile`: a Node stage builds, a Caddy stage serves | One container: Caddy serving `dist/` on `$PORT`, public domain |
| `postgres` | **Not the repository.** Railway's PostgreSQL database service (canvas: New → Database → PostgreSQL, or `railway add -d postgres`) | Nothing: Railway runs its Postgres image on a volume | Private only, `postgres.railway.internal`. Railway generates the credentials and `DATABASE_URL` |

```mermaid
flowchart LR
    subgraph REPO["GitHub repository"]
        B["/backend<br/>Dockerfile, railway.toml"]
        D["/dashboard<br/>Dockerfile, Caddyfile, railway.toml"]
    end

    subgraph ENV["One Railway environment, staging or production"]
        API["api<br/>uvicorn"]
        DASH["dashboard<br/>Caddy"]
        PG[("postgres<br/>Railway image + volume")]
    end

    B -->|"pull /backend only, docker build"| API
    D -->|"pull /dashboard only, docker build"| DASH
    API -->|"pre-deploy: alembic upgrade head"| PG
    API <-->|"DATABASE_URL, private network"| PG
    DASH -.->|"browser calls VITE_API_URL, public HTTPS"| API
```

Railway looks for a file named `Dockerfile` in the root directory and uses it, so setting the root directory is enough; no `RAILWAY_DOCKERFILE_PATH` is needed. **The root directory is also the build context:** Railway pulls only that folder, so a Dockerfile cannot `COPY ../anything`. Each part must build from its own folder alone. This is the same reason the dashboard's generated types are committed.

The `staging` and `production` environments each have their own copy of all three services. Postgres in particular is two separate databases on two separate volumes.

**`backend/Dockerfile`** (indicative):

```dockerfile
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
WORKDIR /app
# dependencies first, so code changes reuse this layer
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev
ENV PATH="/app/.venv/bin:$PATH"
# shell form so $PORT expands; Railway sets PORT, 8000 for local docker run
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
```

The start command lives only in `CMD`, so a local `docker run` behaves the same as Railway. `alembic` is on `PATH` through the virtual environment, and the pre-deploy command runs it in this same image.

**`backend/railway.toml`** (indicative; check field names against Railway's config reference):

```toml
[build]
builder = "DOCKERFILE"
watchPatterns = ["/backend/**"]

[deploy]
preDeployCommand = ["alembic upgrade head"]
healthcheckPath = "/health"
numReplicas = 1
sleepApplication = false
drainingSeconds = 200
```

**`dashboard/Dockerfile`** (indicative):

```dockerfile
FROM node:22-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci

# local only: Compose builds this stage (target: dev) for the Vite dev server
FROM deps AS dev
COPY . .
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]

FROM deps AS build
COPY . .
# Railway passes service variables to the build only when declared as ARG
ARG VITE_API_URL
ARG VITE_FIREBASE_API_KEY
ARG VITE_FIREBASE_AUTH_DOMAIN
ARG VITE_FIREBASE_PROJECT_ID
ARG VITE_FIREBASE_APP_ID
RUN npm run build

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/dist /srv
```

Railway builds the **last** stage of a multi-stage Dockerfile, so the Caddy stage must stay last. The `dev` stage exists only for Compose, which picks it by name.

**`dashboard/Caddyfile`**, following Railway's single-page-app guide:

```caddyfile
{
    admin off
    persist_config off
    # Railway terminates TLS at its edge
    auto_https off
    servers {
        trusted_proxies static 0.0.0.0/0 ::/0
    }
}

:{$PORT:3000} {
    root * /srv
    encode gzip

    # Vite puts a content hash in these names, so a changed file gets a new URL: cache for a year.
    # No fallback here: a missing asset is a 404, never index.html cached under a script's URL.
    @assets path /assets/*
    handle @assets {
        header Cache-Control "public, max-age=31536000, immutable"
        file_server
    }

    # Everything else, index.html included, is revalidated on every load, so a deploy shows at once.
    handle {
        header Cache-Control "no-cache"
        try_files {path} /index.html
        file_server
    }

    # Never cache an error: during a deploy's overlap, an asset can 404 on the old copy for a moment.
    handle_errors {
        header Cache-Control "no-store"
        respond "{err.status_code} {err.status_text}" {err.status_code}
    }
}
```

**`dashboard/railway.toml`:**

```toml
[build]
builder = "DOCKERFILE"
watchPatterns = ["/dashboard/**"]
```

Four details of the dashboard build matter:
- **`ARG` is required.** Vite reads `VITE_*` variables while it builds, and Railway passes service variables into a Docker build only when the Dockerfile declares them with `ARG`. Without the `ARG` lines, the bundle is built with an empty API address.
- **`auto_https off`** because Railway terminates TLS at its edge.
- **`try_files … /index.html`** so a reload on a client-side route such as `/incidents/42` does not return 404.
- **Cache headers.** Hashed files under `/assets/` are cached for a year, because a changed file gets a new name. Everything else, `index.html` included, is `no-cache`, so a deploy shows on the next load. Errors are `no-store`, so a 404 during a deploy's overlap is never remembered.

Railpack, Railway's builder without a Dockerfile, can detect a Vite project and serve it without either file. The Dockerfile is proposed anyway because it makes the build-time variables explicit and runs the same way on a laptop.

**Connecting the API to Postgres.**
- **URL scheme.** Railway's `DATABASE_URL` starts with `postgresql://`. SQLAlchemy's async engine with asyncpg needs `postgresql+asyncpg://`. Swap the prefix once, in the settings module, rather than keeping a second variable that can drift.
- **No public access.** The database stays private (Railway's default), so only services in the same environment reach it.
- **Running the setup script** (`grant_das.py`, G6). `railway run` injects the variables into a process *on the laptop*, which cannot resolve `postgres.railway.internal`. Run it inside the `api` container (`railway ssh`, then `python scripts/grant_das.py …`), or turn on Postgres's public TCP proxy for the duration and use `DATABASE_PUBLIC_URL`.
- **Backups.** The demo data is fictitious and the seed and grant scripts can recreate it, so backups are not needed for the MVP. A pilot needs Railway's volume backups or a scheduled `pg_dump`.

#### Three environments: local, staging, production

**One codebase, one Dockerfile, three environments that differ only in their variables.** Code never checks "am I on Railway" to decide what to do. Every difference is a variable read once at start-up into one settings object, with `APP_ENV` naming the environment.

| | `local` | `staging` | `production` |
|---|---|---|---|
| API runs | On the laptop, in Compose: `docker compose up --watch` | Railway, follows `main` | Railway, follows `release` |
| Database | Postgres in Docker on the laptop | Railway Postgres, staging environment | Railway Postgres, production environment |
| Public address, for Twilio | A tunnel to port 8000 | Railway domain | Railway domain |
| Data | Seed script plus your own phone as a senior. Wiped whenever you like | Seed script plus the team's test phones | The demo cast only, seeded once before the freeze |
| Who uses it | One backend developer | The whole team: Android debug builds, the staging dashboard, S1 and S8 | The demo: Android release builds, the production dashboard |
| Migrated by | You: `alembic upgrade`, `downgrade`, or a fresh volume | Its pre-deploy command, on push to `main` | Its pre-deploy command, on push to `release` |
| Public access to the database | n/a | Off. On only while debugging (see the last subsection) | **Never** |

```mermaid
flowchart LR
    subgraph L["local, one per backend developer"]
        LAPI["api, uvicorn --reload<br/>+ dashboard dev server"]
        LDB[("Docker Postgres<br/>sentinela + sentinela_test")]
        TUN["tunnel<br/>static domain"]
        LAPI --- LDB
        TUN --> LAPI
    end

    subgraph S["staging, Railway"]
        SAPI["api"] --- SDB[("postgres")]
    end

    subgraph P["production, Railway"]
        PAPI["api"] --- PDB[("postgres")]
    end

    TW["Twilio<br/>one account, one number"]
    FB["Firebase<br/>one project"]

    L -->|"git push origin main"| S
    S -->|"git push origin main:release"| P
    TW -->|"callbacks to the address<br/>each call was placed with"| TUN & SAPI & PAPI
    LAPI & SAPI & PAPI --> FB
```

**Variables per environment**

| Variable | `local` (`backend/.env`, not committed) | `staging` (Railway) | `production` (Railway) |
|---|---|---|---|
| `APP_ENV` | `local` | `staging` | `production` |
| `DATABASE_URL` | `postgresql://sentinela:sentinela@localhost:5432/sentinela` | `${{postgres.DATABASE_URL}}` | `${{postgres.DATABASE_URL}}` |
| `PUBLIC_BASE_URL` | `https://<your static domain>`, the tunnel | `https://${{api.RAILWAY_PUBLIC_DOMAIN}}` | `https://${{api.RAILWAY_PUBLIC_DOMAIN}}` |
| `ALLOWED_ORIGIN` | `http://localhost:5173`, Vite's dev server | `https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}` | `https://${{dashboard.RAILWAY_PUBLIC_DOMAIN}}` |
| `SCHEDULER_ENABLED` | `true` | `true` | `true` |
| `DEMO_MODE` | `true` | `true` | `true` for the demo; `false` is the pilot setting |
| Twilio credentials and number | Same account and number in all three | ← | ← |
| Firebase service account | Same project in all three | ← | ← |
| Model provider key | A personal key, so local spending shows separately | Team key | Team key |

**The external services are shared, and that is safe:**
- **Twilio.** Every call is outbound and carries its own callback addresses (04 §4.1). A call placed from the laptop calls back the tunnel; a call placed from staging calls back staging. One number serves all three environments, and nothing changes in the Twilio console.
- **Firebase.** Firebase only proves who owns a phone number; roles are grants stored in *each environment's database* (G6). So one number can be DAS in staging and unknown in production. One project means one `google-services.json`, one set of SHA fingerprints and one list of test phone numbers. Each device's push token is stored by the API it signed in to.

#### The local environment

**One command runs everything: `docker compose up --watch`.** It starts Postgres, the API and the dashboard's dev server, and the tunnel too with a profile. This matters most for the teammates who do not work on the backend. The Android and dashboard owners get a working API with no Python setup, and the Wear OS owner can test the whole watch → phone → API chain on a laptop.

Compose Watch keeps the inner loop fast inside containers. It copies each saved file into the running container, where uvicorn's `--reload` and Vite's hot reload pick it up. When a lock file changes, it rebuilds the image.

```yaml
# compose.yaml (indicative)
services:
  db:
    image: postgres:17            # match the major version of Railway's Postgres service
    environment:
      POSTGRES_USER: sentinela
      POSTGRES_PASSWORD: sentinela
      POSTGRES_DB: sentinela
    ports: ["5432:5432"]          # for pytest, alembic and a database client on the host
    volumes: [pgdata:/var/lib/postgresql/data]
    configs:
      # second database so pytest never wipes development data; runs only on a fresh volume
      - source: create-test-db
        target: /docker-entrypoint-initdb.d/10-test-db.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U sentinela"]
      interval: 2s
      retries: 15

  api:
    build: ./backend              # the same Dockerfile Railway builds
    env_file: backend/.env        # Twilio, Firebase, model provider keys; not committed
    environment:
      DATABASE_URL: postgresql://sentinela:sentinela@db:5432/sentinela
    ports: ["8000:8000"]
    depends_on:
      db: { condition: service_healthy }
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"
    volumes:
      # bind mount, not sync: migrations generated inside the container must land on the host
      - ./backend/alembic:/app/alembic
    develop:
      watch:
        - { action: sync, path: ./backend/app, target: /app/app }
        - { action: rebuild, path: ./backend/uv.lock }

  dashboard:
    build: { context: ./dashboard, target: dev }
    env_file: dashboard/.env      # VITE_FIREBASE_* web config; not committed
    environment:
      # read by the browser on the host, so it is localhost, not the service name "api"
      VITE_API_URL: http://localhost:8000
    ports: ["5173:5173"]
    develop:
      watch:
        - { action: sync, path: ./dashboard/src, target: /app/src }
        - { action: rebuild, path: ./dashboard/package-lock.json }

  tunnel:
    profiles: [tunnel]            # only with --profile tunnel
    image: ngrok/ngrok:3.39.11-alpine
    # the account's free dev domain is assigned automatically and stays the same across restarts
    command: http api:8000
    environment:
      NGROK_AUTHTOKEN: ${NGROK_AUTHTOKEN:-}  # from the root .env, not committed
    ports: ["4040:4040"]          # request inspector at http://localhost:4040
    depends_on: [api]

configs:
  create-test-db:
    content: "CREATE DATABASE sentinela_test;"

volumes:
  pgdata:
```

| Command | Does |
|---|---|
| `docker compose up --watch` | Postgres, the API on `localhost:8000` (migrated) and the dashboard on `localhost:5173`, all reloading on save |
| `docker compose --profile tunnel up --watch` | The same, plus the ngrok tunnel to the API, for Twilio and real phones |
| `docker compose exec api alembic upgrade head` | Applies a new migration without restarting. `--reload` restarts uvicorn, not the migration step |
| `docker compose exec api alembic revision --autogenerate -m "…"` | Writes the migration into `backend/alembic/versions` on the host, through the bind mount |
| `DATABASE_URL=postgresql://sentinela:sentinela@localhost:5432/sentinela_test uv run pytest`, in `backend/` | Tests on the host against `sentinela_test`, which they may wipe freely. The image has no dev dependencies, so pytest is not run inside it |
| `docker compose up --watch db dashboard`, then `uv run uvicorn app.main:app --reload` on the host | **For debugging:** the API outside Docker, with breakpoints in the IDE. Postgres and the dashboard stay in Compose |
| `docker compose down -v` | Wipes both databases, for a clean start |

Three details of this file are easy to get wrong:
- **`VITE_API_URL` is `localhost`, not `api`.** The dashboard's JavaScript runs in the browser on the host, which cannot resolve Compose's service names. Only container-to-container addresses, such as `DATABASE_URL` and the tunnel's `api:8000`, use service names.
- **Migrations need a bind mount, not watch's sync.** Sync copies files one way, from host to container. A migration generated with `alembic revision` inside the container would never appear in Git.
- **Backend developers still keep a local `uv sync`**, so the IDE has the virtual environment for autocompletion and type checks. Teammates who only run the stack do not need it.

**The tunnel: ngrok with its free static domain.** Both ngrok and Cloudflare Tunnel carry the WebSocket Twilio needs. What matters is a **stable address**:
- `PUBLIC_BASE_URL` in `backend/.env` stays the same from one session to the next.
- An Android teammate can point a debug build at your laptop through `local.properties`, and it keeps working tomorrow.

ngrok's free plan includes one static domain. Cloudflare's quick tunnels need no account but give a new random address every run. Its named tunnels are stable, but need a domain of your own on Cloudflare. Each backend developer uses their own ngrok account, whose dev domain ngrok assigns automatically. They keep `NGROK_AUTHTOKEN` in a root `.env`, which Compose reads automatically.

ngrok runs in Compose, not on the host, so one command brings up the whole local environment, and nobody installs ngrok. It targets `api:8000` over Compose's network. It stays behind a profile because only backend developers have an ngrok account, and two tunnels cannot claim the same domain at once.

The tunnel also makes local behave like Railway. A public HTTPS edge terminates TLS and forwards plain HTTP, so the signature check built from `PUBLIC_BASE_URL` (spike S1) is exercised on the laptop too.

**Other clients against the local API**

| Client | Address |
|---|---|
| Dashboard | Already in Compose, at `localhost:5173`. `localhost` is authorized in Firebase by default |
| Android emulator | `http://10.0.2.2:8000` |
| A real phone, yours or a teammate's | The tunnel's static domain |

#### Moving a change through the environments

1. **local.** Write the change and its migration. Iterate freely: `alembic downgrade -1`, edit, `upgrade`, or `down -v`. Test with pytest and with a real call to your phone through the tunnel.
2. **staging.** `git push origin main`. With one or two backend developers, push straight to `main`. CI still runs, and Wait for CI keeps a red build off staging. Switch to pull requests once the Android app depends on staging every day. The pre-deploy command applies the migration.
3. **production.** `git push origin main:release`, when staging is good. The same commit is built again for production, and its pre-deploy command applies the same migrations.

Two migration rules follow from this:
- **A migration is frozen once it is pushed to `main`.** Fix it with a new migration, never by editing the old one. Staging has already recorded the old one as applied.
- **Migrations only add**, because the old and new copies overlap during a deploy (see "Deploys on Railway" below).

#### Checks against crossing environments

The three databases can only be mixed up by a person with a laptop. Three small checks make the dangerous mistakes impossible rather than just unlikely:

| Mistake | Check |
|---|---|
| Running `alembic upgrade` from a laptop against staging or production | `alembic/env.py` refuses any database host other than `localhost` and `db`, unless it runs inside a Railway deployment (`RAILWAY_DEPLOYMENT_ID` is set; `railway run` on a laptop can copy `RAILWAY_ENVIRONMENT_NAME`, but not a deployment id). The cloud databases are migrated only by their own pre-deploy command |
| A local API on a cloud database, competing with that environment's scheduler for the lock (G9) and dialing its queue with the tunnel's address | The API refuses to start when the `DATABASE_URL` host is not `localhost` or the Compose service `db`, `SCHEDULER_ENABLED` is `true`, and it is not inside a Railway deployment. It does not rely on `APP_ENV`, which `railway run` would set to the cloud environment's value |
| pytest wiping the development database | The test settings require a database name ending in `_test` |

#### Debugging against staging data

Occasionally a bug shows only on the data a teammate's phone is showing. Then:
1. Turn on public access for staging's Postgres.
2. Run the local API with `DATABASE_URL` set to its `DATABASE_PUBLIC_URL` and `SCHEDULER_ENABLED=false` (the check above insists).
3. Read, debug, and turn public access off again.

Do not run migrations this way; the `env.py` check refuses anyway. Expect about 30–50 ms per query to EU West, so do not measure call latency in this setup. **Production is never reached this way.**

CI uses a `postgres:17` service container in `backend.yml`, the same image as Compose. The engine and alarm-phrase tests need no database at all (06 §5).

#### Deploys on Railway

**Migrations run as the pre-deploy command.** If a migration fails, the deploy stops and the old copy keeps serving. While two copies overlap, the old code runs against the new schema, so migrations must only add: new columns nullable or with defaults, nothing renamed or dropped in the same deploy.

**Proposed refinement to 01 §9: let live calls finish during a deploy.** Today the spec accepts that a deploy drops live calls. Railway sends SIGTERM to the old copy and SIGKILL `drainingSeconds` later. The call length limit is 3 minutes, so with `drainingSeconds = 200` the old copy can:
1. release the scheduler lock on SIGTERM, so the new copy takes over dialing;
2. refuse new relay connections;
3. keep its open WebSockets until their calls end.

Callbacks need no special handling. They are stateless HTTP requests, they reach whichever copy is serving, and the state they need is in the database. Only the relay WebSocket is tied to one copy. **Add to S8:** do the WebSockets already open on the old copy survive the switch of traffic to the new copy? If they do not, keep the spec's rule as it is.

**Wait for CI** is turned on for both Railway services, so a red workflow never deploys. This has one consequence for Android, covered in 2.4.

### 2. How CI/CD affects the Android apps

The API and the dashboard are delivered *continuously*. The Android apps are delivered *by hand*. Most Android decisions come from that difference.

```mermaid
flowchart LR
    subgraph GIT["GitHub, one repository"]
        PR["Pull request"] --> MAIN["main"]
        MAIN -->|"fast-forward, promote"| REL["release"]
    end

    subgraph ACT["GitHub Actions, path-filtered"]
        BW["backend.yml<br/>ruff, pytest, openapi.json check"]
        DW["dashboard.yml<br/>tsc, vite build"]
        AW["android.yml<br/>lint, unit tests, assemble"]
        AR["android-release.yml<br/>signed APKs, distribute"]
    end

    subgraph STG["Railway staging"]
        SAPI["api"]
        SDB[("postgres")]
        SDASH["dashboard"]
    end

    subgraph PRD["Railway production"]
        PAPI["api"]
        PDB[("postgres")]
        PDASH["dashboard"]
    end

    subgraph DEV["Devices, installed by a person"]
        FAD["Firebase App Distribution<br/>phones and tablet"]
        ADB["adb over Wi-Fi<br/>watch"]
    end

    PR --> BW & DW & AW
    MAIN -->|"Wait for CI"| SAPI & SDASH
    REL -->|"Wait for CI"| PAPI & PDASH
    MAIN --> AR
    REL --> AR
    AR -->|"debug build, staging address"| FAD
    AR -->|"release build, production address"| FAD
    AR -->|"wear APK as a workflow artifact"| ADB
    SAPI --- SDB
    PAPI --- PDB
```

#### 2.1 One signing key for everything

| Why one key | What breaks without it |
|---|---|
| The Data Layer needs the phone and the watch signed alike | Watch events silently never reach the phone. Typical cause: the watch was installed from one laptop's debug key and the phone from another's |
| Firebase phone sign-in checks the key's SHA-1 and SHA-256 | Sign-in falls back to reCAPTCHA or fails, only for builds from an unregistered key |
| Installing over an existing build | `INSTALL_FAILED_UPDATE_INCOMPATIBLE`: the app must be uninstalled first, which signs the person out and drops the push token |

So both the `debug` and `release` build types, in `:app` and `:wear`, use one keystore. Its SHA fingerprints are registered once in Firebase. The apps never go to the Play Store, so the key has no store identity to protect. Keep it out of Git anyway: share it among the four developers through a password manager, and give it to CI as a base64 secret. Each developer points `local.properties` at their copy.

#### 2.2 Builds are tied to an environment when they are built

| Build type | API address | Built when | Goes to |
|---|---|---|---|
| `debug` | staging | Every push to `main` that touches `android/**` | App Distribution group `team` |
| `release` | production | Every push to `release` that touches `android/**` | App Distribution group `demo-devices` |

The address is a `BuildConfig` field, which a developer can override in `local.properties` to point at a tunnel to their laptop. The watch never calls the API, but it must be built in the same build type as the phone, so that the package name and the key match.

`versionCode` comes from the workflow run number, the same for phone and watch, so every new build installs over the last one.

App Distribution reaches the phones and the tablet. Its tester app does not run on the watch, so the wear APK is attached to the workflow run and installed with `adb` over Wi-Fi.

#### 2.3 An old APK will talk to a new API

Railway deploys the API minutes after a merge. A device updates only when someone taps install, and the demo involves about five Android devices and a watch. So every API change must keep working with the apps already installed:

| Rule | Where it is enforced |
|---|---|
| The API adds and never removes: new fields are optional, old fields stay until every device has updated | Review of `backend/openapi.json`. CODEOWNERS makes the Android and dashboard owners reviewers of that file |
| The app ignores fields it does not know | The Kotlin JSON setup: `ignoreUnknownKeys = true` |
| The app survives values it does not know. Enumerations in the spec will grow: trigger, incident outcome, push `type` (`code_changed`, `incident`, `refresh`), the refresh's "what changed" | Decode these as strings with a fallback, or use `coerceInputValues` with a default. A plain Kotlin `enum` crashes on an unknown value |
| A push type the app does not know is still treated as a refresh | The push handler's default branch |
| `openapi.json` is regenerated in CI and must match the committed copy | `backend.yml`: export, then `git diff --exit-code` |

A breaking-change checker such as `oasdiff` could compare the file with `main` automatically. Skipped for now: with four people, the CODEOWNERS review covers it. Add it when the API has outside consumers.

#### 2.4 The Android workflow can hold back a backend deploy

Wait for CI waits for every workflow on a commit. If one commit to `main` touches both `backend/` and `android/`, and the Android build fails, the API deploy is **skipped**. The API deploy also waits for the Gradle build, which takes several minutes on a cold cache. Two habits avoid this:

- **Separate workflows with `paths:` filters**, not one workflow with per-component jobs. A workflow that does not run never blocks. A single combined workflow would tie every deploy to the slowest job.
- **Prefer one component per pull request**, except for deliberate contract changes, where holding back the deploy until the clients build is what you want.

Path-filtered workflows have one known trap: a check marked *required* in branch protection waits forever on a pull request that does not touch that path. So **do not mark these workflows as required checks.** Wait for CI already guards deploys, and review guards merges.

#### 2.5 What Android CI runs, and what it does not

| Runs on every Android pull request | Why it is in CI |
|---|---|
| `./gradlew lint testDebugUnitTest assembleDebug` | Fast enough with Gradle caching (`gradle/actions/setup-gradle`, JDK 17) |
| Unit tests of `:shared`: message encoding and decoding round trips, the watch threshold cases from 06 §5 | Plain Kotlin, no device needed |

| Does not run in CI | Why |
|---|---|
| Emulator and instrumented tests | Slow, flaky on hosted runners, and the risky behaviour (background sensors S5, background delivery S6, push after idle S7) only shows on the real hardware |
| End-to-end runs with Twilio | Real calls cost money and need real phones. Covered by the rehearsal in 06 §5 |

**Secrets in GitHub:** the keystore with its passwords, and a Firebase service account for App Distribution. That is all. Twilio, model provider and Firebase admin credentials stay in Railway's variables (06 §4). Railway pulls from GitHub itself, so GitHub never needs a Railway token.

`google-services.json` is committed. It holds identifiers, not secrets, and access is protected by the registered SHA fingerprints and by FastAPI checking every token.

## Consequences

**Easier**
- A contract change and the client updates it needs are one pull request, reviewed by the people it affects.
- Android, dashboard and docs changes never redeploy the API, so they never drop calls.
- Every phone, tablet and watch has an installable build that matches an environment, without anyone building it on a laptop.
- The engine, alarm-phrase and watch-threshold tests (the logic that decides a person's code) run on every relevant change, as 06 §5 asks.

**Harder**
- The API has to stay additive, which requires discipline the moment the Android app ships.
- One shared keystore to look after. If it is lost, every device needs an uninstall and a new install, and the new fingerprints must be registered in Firebase.
- Two Railway environments cost about twice as much as one; still small at this scale.

**To revisit**
- PR environments, once the Firebase domain issue has a fix (a wildcard custom domain) and Twilio has a dry-run mode.
- `oasdiff` in CI, once anyone outside the team uses the API.
- Whether live calls survive a deploy (S8 addition above). If they do, update 01 §9 and 06 §1.
- A Kotlin client generated from `openapi.json`, if the hand-written data classes start drifting from the API.

## Action items

1. [ ] Create `backend/`, `dashboard/` and `android/` with the layout above. `android/` gets `:app`, `:wear` and `:shared`, with one `applicationId` and the shared signing config.
2. [ ] Add `compose.yaml` at the root and `backend/.env` to `.gitignore`. Add the three checks against crossing environments. Each backend developer puts their ngrok authtoken in the root `.env`.
3. [ ] Generate the shared keystore, store it in the team's password manager, add it to GitHub secrets, and register its SHA-1 and SHA-256 in Firebase.
4. [ ] Railway: one project, EU West, environments `staging` (follows `main`) and `production` (follows `release`). Services `api`, `dashboard` and `postgres` in each. Root directories, absolute config paths, watch paths, Wait for CI.
5. [ ] Add both dashboard domains to Firebase Auth's authorized domains.
6. [ ] Add `backend.yml`, `dashboard.yml` and `android.yml` with `paths:` filters, and `android-release.yml` on pushes to `main` and `release`.
7. [ ] Add `.github/CODEOWNERS` with `backend/openapi.json` assigned to the Android and dashboard owners.
8. [ ] On the first staging deploy, confirm `RAILWAY_DEPLOYMENT_ID` is set during the pre-deploy command. If it is not, staging's migrations will be refused by `alembic/env.py`.
9. [ ] Add to spike S1: Twilio's signature check passes behind Railway's proxy.
10. [ ] Add to spike S8: open WebSockets survive the traffic switch during a deploy with `drainingSeconds = 200`.
11. [ ] Add a ruleset to `release` that blocks pushes after the Sunday-morning freeze.
12. [ ] Once accepted, add it to the decision log in the [spec README](../specs/sentinela/README.md) as G17.
