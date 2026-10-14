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
| `FIREBASE_WEB_API_KEY` | your Firebase web API key | Used by `dev_token.py` to sign in test numbers; same as dashboard's `VITE_FIREBASE_API_KEY` |

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

## Sign in by hand

Every client signs in with a phone number ([auth-layer.md](../docs/specs/auth-layer.md)). No key or account setup is needed: the API checks tokens against Firebase's public keys. These Firebase test numbers need no SMS:

| Number | Code | Granted as |
|---|---|---|
| `+40700000001` | `111111` | DAS |
| `+40700000002` | `222222` | medic |
| `+40700000003` | `333333` | DAS and medic |
| `+40700000004` | `444444` | a caregiver |
| `+40700000005` | `555555` | a senior |
| `+40700000009` | `999999` | nothing |

The numbers `+40700000004` and `+40700000005` work once a person has added them in the Firebase console ([seniors-and-enrollment.md](../docs/specs/seniors-and-enrollment.md), §10 step 1).

Grants live in each environment's database. Locally, grant DAS with the setup script (on Railway, run the same inside `railway ssh -s api -e staging`):

```bash
docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001
```

A real token for a test number and its code, valid for an hour. Paste it into Authorize at http://localhost:8000/api/docs, or use it with curl:

```bash
TOKEN=$(uv run python scripts/dev_token.py +40700000001 111111)
```

```bash
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/me
```

A DAS grants medics through the API:

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"display_name": "Medic Test", "phone": "+40700000002", "role": "medic", "practice": "CMI Test"}' localhost:8000/api/staff
```

## Mock data

[scripts/seed.py](scripts/seed.py) fills the local database with fictitious people and their history: twelve seniors in every enrollment state, their medics and caregivers, a cold-weather campaign, calls with transcripts, and incidents open, in progress and resolved. It grants `+40700000001` DAS and `+40700000002` medic, and makes `+40700000004` and `+40700000005` Maria Popescu's son and Maria Popescu, so each test number signs in to something. From `backend/`:

```bash
uv run python scripts/seed.py
```

A second run adds nothing. Its times are relative to when it ran, and resolved incidents leave the dashboard after a day; `--reset` replaces only the seed's own rows with fresh ones. Rows made through the API or `grant_das.py` stay. It refuses any database but a local one.

```bash
uv run python scripts/seed.py --reset
```

**Staging and production: planned, not ready.** ADR-001 expects staging to hold the seed plus the team's test phones, and production the demo cast, seeded once before the freeze. Seeding stays a person's action, never part of a deploy: no pre-deploy command, no start-up hook. It would run inside the `api` container, as `grant_das.py` does, since a laptop cannot reach `postgres.railway.internal`:

```bash
railway ssh -s api -e staging
```

Two things must change before that:

- **The guard.** The script refuses every database but a local one, including from inside Railway. It would follow `alembic/env.py`: allowed inside a Railway deployment, still refused from a laptop.
- **The phone numbers.** The seeded seniors' numbers are made up and may belong to real people; two are Timișoara landlines. Locally nothing dials them, but with Twilio set up a campaign or `place_call.py` would. The active seniors need the team's own phones first.

On the day, run `--reset` shortly before the demo, so the open incident is minutes old and the resolved ones are still on the board. Never during a live demo: `--reset` deletes every incident and call attached to a seeded senior.

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
