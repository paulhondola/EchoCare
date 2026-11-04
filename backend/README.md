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
| `DATABASE_URL` | `postgresql://echocare:echocare@localhost:5432/echocare` | Compose overrides it to use its `db` service. `postgresql://` is rewritten to the asyncpg driver |
| `PUBLIC_BASE_URL` | your ngrok domain | The API's public address, for Twilio callbacks and signature checks |
| `ALLOWED_ORIGIN` | `http://localhost:5173` | The only browser origin allowed by CORS: the dashboard. With `APP_ENV=local` the API also allows `http://localhost:5173` and `http://127.0.0.1:5173`, the dev server under both names (real-SMS sign-in needs `127.0.0.1`) |
| `SCHEDULER_ENABLED` | `true` | Must be `false` to point a laptop at a cloud database (see below) |
| `DEMO_MODE` | `true` | Shortens timers for the demo (06 §3) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` | empty | The Twilio account and the project's number (Romanian, +40). Empty, the scheduler dials nothing and every callback is refused. See [Real calls locally](#real-calls-locally) |
| `TWILIO_API_HOST` | `api.twilio.com` | The Voice API's host. The project runs in Ireland: `api.dublin.ie1.twilio.com`, with the IE1 auth token in `TWILIO_AUTH_TOKEN` (credentials are per region) |
| `MAX_LIVE_CALLS` | `3` | How many calls the scheduler keeps live at once |
| `DIAL_ALLOWLIST` | empty | Whom the scheduler and `place_call.py` may ring: comma-separated numbers, `*` for everyone. Empty dials nobody, in every environment; a call it will not dial stays queued and keeps its mock card |
| `FIREBASE_WEB_API_KEY` | your Firebase web API key | Used by `dev_token.py` to sign in test numbers; same as dashboard's `VITE_FIREBASE_API_KEY` |

## Real calls locally

The scheduler ([06 §2](../docs/specs/echocare/06-operations.md)) runs inside the API and dials queued calls that are due: accepting a senior, or starting a campaign, rings their phone. With nothing set, it dials nothing and the mock card answers as before.

1. **Twilio.** In `backend/.env`, set `TWILIO_ACCOUNT_SID`, `TWILIO_FROM_NUMBER`, and `TWILIO_AUTH_TOKEN` with `TWILIO_API_HOST=api.dublin.ie1.twilio.com`. Use the IE1 auth token, not the US one.
2. **The tunnel.** Twilio calls the API back, so it must reach port 8000. Compose runs ngrok for it ([ADR-001](../docs/adr/ADR-001-monorepo-and-delivery.md)): put your ngrok authtoken in `NGROK_AUTHTOKEN` in the root `.env`, and your account's dev domain in `PUBLIC_BASE_URL`. From the repository root:

   ```bash
   docker compose --profile tunnel up --watch
   ```

   The domain stays the same across restarts; ngrok's request inspector at http://localhost:4040 shows it, with every callback Twilio sends. Compose reads `backend/.env` only when it creates the container, so **recreate the API after changing it** (`docker compose up -d --force-recreate api`). Without a tunnel the phone still rings, but no callback arrives, and the sweep settles the call about 4.5 minutes later.
3. **A number to ring.** The seeded seniors' numbers are made up. Replace an active senior's number with your own by hand, then list it in `DIAL_ALLOWLIST` (a number off the list is never dialed). Before listing it, cancel or delete the old queued calls in your local database: welcome, manual and watch calls never lapse, so every old one for a listed senior is dialed at once.
4. **Try it.** Accept a senior, or start a campaign, and your phone rings. The welcome call runs UC-04 ([02-use-cases.md](../docs/specs/echocare/02-use-cases.md)): press 1 for identity and 1 for consent, or say „da” twice, and the senior becomes `active` with code green. On a wellbeing call, pressing 9 or saying a tier 1 phrase („am căzut”) opens an incident and rings the on-duty DAS employee, whose number must be on `DIAL_ALLOWLIST` too. Answering takes the incident.

`uv run python scripts/place_call.py <number>` places a scripted test call instead, and follows the allowlist too. Run once on a new Twilio setup, it also checks two things Twilio's docs do not confirm for IE1: that callbacks verify (a 403 on every callback says they do not) and that voicemail detection runs.

Twilio's console webhook on the number is not used: every outbound call carries its own callback addresses.

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

`lint-imports` checks the import contracts in `pyproject.toml`: the layers inside each package, no FastAPI or HTTP client in models and schemas, a pure status engine, and no cycles between packages. `tests/architecture/test_contracts.py` checks that `__init__.py` files import nothing.

```bash
uv run lint-imports
```

Tests that need a database use `echocare_test`, never `echocare`, so Compose's `db` must be running. Each run migrates it down and up again, so it also proves the migrations. Compose creates `echocare_test` on a fresh volume; on an older one, create it once:

```bash
docker compose exec db createdb -U echocare echocare_test
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
| `+40700000006` | `666666` | a second senior, for the welcome card |
| `+40700000009` | `999999` | nothing |

The numbers `+40700000004`, `+40700000005` and `+40700000006` work once a person has added them in the Firebase console ([seniors-and-enrollment.md](../docs/specs/seniors-and-enrollment.md), §10 step 1).

Grants live in each environment's database. Locally, grant DAS with the setup script (on Railway, run the same inside `railway ssh -s api -e staging`):

```bash
docker compose exec api python scripts/grant_das.py "DAS Test" +40700000001
```

A real token for a test number and its code, valid for an hour. Paste it into Authorize at http://localhost:8000/api/docs, or use it with curl:

```bash
TOKEN=$(uv run python scripts/dev_token.py +40700000001 111111)
```

```bash
curl -H "Authorization: Bearer $TOKEN" localhost:8000/api/profile
```

A DAS grants medics through the API:

```bash
curl -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d '{"display_name": "Medic Test", "phone": "+40700000002", "role": "medic", "practice": "CMI Test"}' localhost:8000/api/staff
```

## Mock data

[scripts/seed.py](scripts/seed.py) fills the local database with fictitious people and their history: eighteen seniors in every enrollment state, their medics and caregivers, a cold-weather campaign, calls with transcripts, and fourteen incidents, open, in progress and resolved. It grants `+40700000001` DAS and `+40700000002` medic, and makes `+40700000004` and `+40700000005` Maria Popescu's son and Maria Popescu, so each test number signs in to something. From `backend/`:

```bash
uv run python scripts/seed.py
```

A second run adds nothing. Its times are relative to when it ran, and resolved incidents leave the dashboard after a day; `--reset` makes the seed's seniors again with fresh times. It deletes them first with everything about them, including calls, incidents, caregivers and edits made through the API or the apps since. Users, staff grants, the campaign and seniors made through the API stay. If `+40700000005` is already another senior's number, it keeps signing in to that senior (AL7) and the run says so. It refuses any database but a local one.

```bash
uv run python scripts/seed.py --reset
```

`seed.py` stays local. Its seniors' numbers are made up and may belong to real people; two are Timișoara landlines.

On the day, run `--reset` shortly before the demo, so the open incident is minutes old and the resolved ones are still on the board. Never during a live demo: `--reset` deletes every incident and call attached to a seeded senior.

### The demo cast on staging and production

ADR-001 has staging hold the team's phones and production the demo cast, seeded once before the freeze. [scripts/seed_cast.py](scripts/seed_cast.py) seeds four people through the same steps the apps take:
- a medic;
- a DAS employee, put on duty, so hand-overs ring them;
- a senior the medic registered;
- the senior's caregiver.

The senior is left `submitted`, so the demo starts with DAS pressing „Acceptă”, which rings the welcome call. A second run adds nothing.

The cast is real people, so it never enters Git (#48). Keep it in a JSON file outside the repository, or as `backend/cast.json`, which Git and Docker ignore. [cast.example.json](cast.example.json) shows its shape; every field is checked as the API checks it.

Seeding stays a person's action, never part of a deploy. Run it inside the `api` container, since a laptop cannot reach `postgres.railway.internal`, and pipe the file in from the laptop. `--confirm` must name the environment, so production is never seeded by mistake:

```bash
railway ssh -s api -e staging -- python scripts/seed_cast.py --confirm staging - < cast.json
```

From a laptop the script refuses any database but a local one, as `alembic/env.py` does.

For the senior's calls to ring, put the senior's and the DAS number on that environment's `DIAL_ALLOWLIST`.

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
