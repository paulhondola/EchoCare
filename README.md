# Sentinela-Test

Sentinela checks on seniors living alone with automated phone calls, a Wear OS watch and an Android app, and hands emergencies to a dispatch team (DAS) through a web dashboard. The design is in [docs/specs/sentinela](docs/specs/sentinela/README.md); how the repository is built and delivered is in [ADR-001](docs/adr/ADR-001-monorepo-and-delivery.md).

| Folder | What | Setup and commands |
|---|---|---|
| [backend/](backend/) | FastAPI service (`api` on Railway), Python, uv, Alembic | [backend/README.md](backend/README.md) |
| [dashboard/](dashboard/) | DAS web dashboard, Svelte 5 + SvelteKit 3, served by Caddy | [dashboard/README.md](dashboard/README.md) |
| [android/](android/) | Android app (four roles) and Wear OS app, one Gradle build | [android/README.md](android/README.md) |
| [.railway/](.railway/) | Railway infrastructure as code for staging and production | [.railway/README.md](.railway/README.md) |
| [docs/](docs/) | Specification and architecture decisions | |

## Tools

| Tool | Needed for | Install (macOS) |
|---|---|---|
| Docker Desktop (Compose v2.24+) | The whole local environment | [docker.com](https://www.docker.com/products/docker-desktop/) |
| Android Studio | The Android and Wear OS apps | [developer.android.com/studio](https://developer.android.com/studio) |
| Android CLI (`android`) | Emulators, installing and inspecting the apps from the terminal; agent skills | [developer.android.com/tools/agents](https://developer.android.com/tools/agents) |
| uv | Backend development outside Docker (IDE, pytest, ruff) | `brew install uv` |
| Node.js 26 + npm | Dashboard development outside Docker; `.railway/` | `brew install node` |
| Railway CLI | Applying `.railway/`, logs, SSH into deployments | `brew install railway` |
| GitHub CLI | Pull requests from the terminal (optional) | `brew install gh` |
| lefthook | Git hooks: each folder's checks on commit and push (see below) | `brew install lefthook` |

Teammates who only run the stack, such as the Android and Wear OS owners, need only Docker.

## Run everything locally

Copy the example environment files once. None of the copies are committed.

```bash
cp .env.example .env
```

```bash
cp backend/.env.example backend/.env
```

```bash
cp dashboard/.env.example dashboard/.env
```

Fill in `dashboard/.env` with the Firebase web config (Firebase console → Project settings → Your apps → the web app). For the tunnel, put your ngrok authtoken in the root `.env` and your ngrok domain in `PUBLIC_BASE_URL` in `backend/.env`.

Start Postgres, the API (migrated) and the dashboard, all reloading on save:

```bash
docker compose up --watch
```

| Address | What |
|---|---|
| http://localhost:8000/api/health | API health check: `{"status":"ok","env":"local"}` |
| http://localhost:8000/api/docs | API docs |
| http://localhost:5173 | Dashboard, showing "API: ok (local)" |
| localhost:5432 | Postgres: user, password and database `sentinela`; `sentinela_test` for tests |

With the ngrok tunnel, for Twilio and real phones (request inspector at http://localhost:4040):

```bash
docker compose --profile tunnel up --watch
```

Wipe both local databases for a clean start:

```bash
docker compose down -v
```

## How changes ship

```
pull request → CI (backend.yml, dashboard.yml, android.yml) → merge to main → Railway staging
PR main → release, merged with a merge commit → Railway production
```

- **CI** runs only for the folder a change touches. Railway waits for it to pass before deploying (Wait for CI).
- **Watch paths** keep a docs, dashboard or Android change from redeploying the API, which would drop live calls.
- **`release`** accepts changes only through a pull request merged with a merge commit; anyone on the team can open and merge one.
- **Railway's settings** live in [.railway/railway.ts](.railway/railway.ts) and are applied by hand; see [.railway/README.md](.railway/README.md).

## Git hooks

[lefthook.yml](lefthook.yml) runs CI's checks on your laptop, only for the folders a commit or push touches ([ADR-002](docs/adr/ADR-002-git-hooks.md)). Install the hooks once per clone:

```bash
lefthook install
```

| Touches | On commit | On push |
|---|---|---|
| `backend/` | `ruff check --fix`, `ruff format`, `pytest` | |
| `dashboard/` | `vp check --fix`: format, lint, type check | |
| `android/` | `ktlintFormat` | `ktlintCheck lint testDebugUnitTest :shared:test` |

- **Formatters fix and restage** the files you commit. A lint error, type error or failing test stops the commit.
- **Each hook needs its folder's toolchain:** uv for `backend/`, `npm ci` in `dashboard/`, the Android SDK for `android/`.
- **Committing part of a file:** the unstaged lines are kept, but when a formatter changes the staged ones they can come back a few lines off. Check `git diff` afterwards.
- **Skipping:** `git commit --no-verify` or `LEFTHOOK=0`. CI still runs the same checks.
- **Git GUIs** (Android Studio, VS Code) may run hooks without Homebrew on the `PATH`. Create `lefthook-local.yml` (not committed) with `rc: ~/.lefthookrc`, and put `export PATH="/opt/homebrew/bin:$PATH"` in `~/.lefthookrc`.

## Claude Code and other agents

Each folder has an `AGENTS.md` (layout, scope, commands, rules), which the `CLAUDE.md` beside it imports. The team's Claude Code setup is committed:

| File | What |
|---|---|
| [.claude/settings.json](.claude/settings.json) | Shared plugins and their marketplaces; a hook that refuses edits to migrations already on `main`; asks before Railway changes and `docker compose down -v` |
| [.mcp.json](.mcp.json) | The Railway MCP server, signed in through your own `railway login`; Playwright, for driving the dashboard in a browser |
| [.claude/skills/](.claude/skills/) | `use-railway` and `archify` (diagrams; needs Node) |

On the first session in this folder, Claude Code asks you to trust the marketplaces, install the plugins and approve the MCP server. To turn a shared plugin off for yourself only, set it to `false` in `.claude/settings.local.json`, which is not committed:

```json
{ "enabledPlugins": { "explanatory-output-style@claude-plugins-official": false } }
```
