# AGENTS.md

Guide for coding agents in this repository. People start with [README.md](README.md).

Sentinela checks on seniors living alone with automated phone calls in Romanian, a Wear OS watch and an Android app, and hands emergencies to a dispatch team (DAS) through a web dashboard. One repository, one native toolchain per folder, no build orchestrator ([ADR-001](docs/adr/ADR-001-monorepo-and-delivery.md)).

## Layout

| Path | What | Toolchain | Agent guide |
|---|---|---|---|
| `backend/` | FastAPI service, the only part that touches the database | Python 3.14, uv, SQLAlchemy, Alembic | [backend/AGENTS.md](backend/AGENTS.md) |
| `dashboard/` | DAS web dashboard | React 19, Vite, TypeScript, npm | [dashboard/AGENTS.md](dashboard/AGENTS.md) |
| `android/` | Phone app `:app`, watch app `:wear`, plain-Kotlin `:shared` | Kotlin, Compose, Gradle | [android/AGENTS.md](android/AGENTS.md) |
| `.railway/` | Railway settings as code, staging and production | TypeScript, Railway CLI | [.railway/AGENTS.md](.railway/AGENTS.md) |
| `docs/specs/sentinela/` | The specification (MVP): architecture, use cases, status model, interfaces, data model, operations | Markdown | |
| `docs/adr/` | Architecture decisions | Markdown | |
| `docs/specs/esti-bine-specificatii-v3.md`, `unihack.md` | The earlier v3 spec and the hackathon brief, in Romanian. History, not the current design | Markdown | |
| `.github/workflows/` | One CI workflow per folder, path-filtered | GitHub Actions | |
| `compose.yaml` | Local stack: Postgres 18, API, dashboard, optional ngrok tunnel | Docker Compose | |

Run each toolchain from its own folder. There is no root `package.json`, Makefile or task runner.

## The spec is the source of truth

Code and comments cite the spec by ID: `G6` (goal), `UC-09` (use case), `04 §6` (file `04-interfaces.md`, section 6), `S5` (spike), `ADR-001 §2.1`. Before building a feature, read the matching file in [docs/specs/sentinela/](docs/specs/sentinela/README.md). The API contract is `04-interfaces.md` and the tables are `05-data-model.md`. Cite IDs the same way in new comments.

## Commands

From the repository root. Each folder's AGENTS.md has its own build, test and lint commands.

| Task | Command |
|---|---|
| Create the local env files, once | `cp .env.example .env && cp backend/.env.example backend/.env && cp dashboard/.env.example dashboard/.env` |
| Start the whole stack, reloading on save | `docker compose up --watch` |
| Same, with the ngrok tunnel for Twilio | `docker compose --profile tunnel up --watch` |
| Postgres and dashboard only, to run the API on the host | `docker compose up --watch db dashboard` |
| Check the stack is up | `curl localhost:8000/api/health` → `{"status":"ok","env":"local"}` |
| Wipe both local databases (ask first) | `docker compose down -v` |

| Address | What |
|---|---|
| http://localhost:8000/api/docs | API and its OpenAPI docs |
| http://localhost:5173 | Dashboard |
| localhost:5432 | Postgres; user, password and database `sentinela`; tests use `sentinela_test` |
| http://localhost:4040 | ngrok request inspector, with the tunnel profile |

## How changes ship

```
branch → CI for the folders it touches → main → Railway staging
PR main → release, merged with a merge commit → Railway production
```

- CI is path-filtered: `backend.yml`, `dashboard.yml`, `android.yml`. Run the same check locally before you push; each folder's AGENTS.md names it.
- Railway's Wait for CI waits for every workflow on a commit, so a red Android build also holds back an API deploy. Prefer one component per change.
- Railway redeploys a service on any change under its folder (`/backend/**`, `/dashboard/**`), Markdown included. Redeploying `api` drops live calls.
- Don't push to `main` or `release`, merge, or open PRs unless the user asks.

## Rules

- **Never commit secrets.** `.env` files, `android/local.properties` and `*.jks` are git-ignored; keep them that way. The Firebase web config is public and is written in plain text on purpose.
- **Leave cloud environments alone.** Don't migrate, apply Railway config, set variables or deploy unless the user asks. `alembic` and the API refuse some of this from a laptop by design; never work around those checks.
- **Old clients talk to new servers.** Installed APKs lag the API, and old and new API copies overlap during a deploy. API changes and migrations only add: new fields optional, nothing renamed or dropped in the same change (ADR-001 §2.3).
- **Contract changes move together.** When an endpoint changes, update `04-interfaces.md`, the backend and the clients that call it (`android/app/.../Api.kt`, `dashboard/src/`) in one change.
- **User-facing text is Romanian.** New phone and watch UI strings and the call script are written in Romanian; code, comments and docs stay in English.
