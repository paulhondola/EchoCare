# backend: the FastAPI service

The only backend and the only part that touches the database (spec G2). Python 3.14, FastAPI, SQLAlchemy (async, asyncpg), Alembic, managed with uv. On Railway it is the `api` service, built from this folder's [Dockerfile](Dockerfile).

## Run it

**In Docker, with the rest of the stack** (from the repository root). The API is migrated on start and reloads on save:

```bash
docker compose up --watch
```

**On the host, for breakpoints in the IDE.** Keep Postgres and the dashboard in Compose (from the repository root):

```bash
docker compose up --watch db dashboard
```

Then run the API yourself, from `backend/`. It reads `backend/.env`, whose `DATABASE_URL` points at `localhost`:

```bash
uv run uvicorn app.main:app --reload
```

Either way the API is at http://localhost:8000 (`/api/health`, `/api/docs`).

## Set up for development

Backend developers keep a local virtual environment, so the IDE has autocompletion and type checks. From `backend/`:

```bash
uv sync
```

```bash
cp .env.example .env
```

| Variable | Local value | What it does |
|---|---|---|
| `APP_ENV` | `local` | `local`, `staging` or `production`; shown by `/api/health` |
| `DATABASE_URL` | `postgresql://sentinela:sentinela@localhost:5432/sentinela` | Compose overrides it to use its `db` service. `postgresql://` is rewritten to the asyncpg driver |
| `PUBLIC_BASE_URL` | your ngrok domain | The API's public address, for Twilio callbacks and signature checks |
| `ALLOWED_ORIGIN` | `http://localhost:5173` | The only browser origin allowed by CORS: the dashboard |
| `SCHEDULER_ENABLED` | `true` | Must be `false` to point a laptop at a cloud database (see below) |
| `DEMO_MODE` | `true` | Shortens timers for the demo (06 §3) |

## Test and lint

From `backend/`. CI runs the same commands ([backend.yml](../.github/workflows/backend.yml)):

```bash
uv run pytest
```

```bash
uv run ruff check .
```

```bash
uv run ruff format .
```

Tests that need a database use `sentinela_test`, never `sentinela`, so Compose's `db` must be running. Each run migrates it down and up again, so it also proves the migrations. Compose creates `sentinela_test` on a fresh volume; on an older one, create it once:

```bash
docker compose exec db createdb -U sentinela sentinela_test
```

## Migrations

Run inside the Compose container. Files written there land in `alembic/versions/` on the host through a bind mount.

```bash
docker compose exec api alembic revision --autogenerate -m "add incidents"
```

```bash
docker compose exec api alembic upgrade head
```

Two rules, because the old and new copies overlap during a deploy (ADR-001):
- **Migrations only add.** New columns are nullable or have defaults; nothing is renamed or dropped in the same deploy.
- **A migration is frozen once it reaches `main`.** Fix it with a new migration; staging has already applied the old one.

## On Railway

Railway builds the [Dockerfile](Dockerfile) and runs `alembic upgrade head` before each deploy. A failed migration stops the deploy and the old copy keeps serving. The service's settings are in [.railway/railway.ts](../.railway/railway.ts).

Two checks stop a laptop from crossing into a cloud environment:
- `alembic` refuses to migrate any database other than `localhost` or Compose's `db`, unless it runs inside a Railway deployment. Cloud databases are migrated only by their own deploys.
- The API refuses to start against a cloud database with `SCHEDULER_ENABLED=true`, so a laptop never competes with staging's scheduler for calls.

Logs and a shell in a deployment (the `-e` flag works for these commands):

```bash
railway logs -s api -e staging
```

```bash
railway ssh -s api -e staging
```
