# ADR-004: The API stays one async process, awake; no nginx, no Redis

**Status:** Proposed
**Date:** 2026-10-18
**Deciders:** the team of four (backend owner first: every change lands on `api`)
**Builds on:** 01 §8–§10, 06 §2–§3, [ADR-001](ADR-001-monorepo-and-delivery.md) §2 (Railway deploy settings)

## Context

The question: Railway gives the `api` replica 8 vCPU and 8 GB. Should uvicorn run more workers, and would nginx or Redis help?

**What the service uses.** Railway metrics, 2026-10-11 to 2026-10-18:

| | `api` production | `api` staging | `Postgres` production |
|---|---|---|---|
| CPU, average / peak | 0.0003 / 0.043 vCPU | 0.0003 / 0.076 vCPU | 0.0001 / 0.021 vCPU |
| Memory, average / peak | 69 / 231 MB | 64 / 392 MB | 38 / 107 MB |
| Requests | | 179 in 7 days, none 5xx | |
| Latency p50 / worst p99 | | 15 ms / 2.3 s | |
| State on 2026-10-18 | `SLEEPING` | | |

Peak use is under 8% of one core. The 8 vCPU / 8 GB is the plan's per-replica ceiling, not a reservation: Railway bills what the container uses, so the ceiling costs nothing and buys nothing.

**What it must carry at its busiest.** 06 §3 caps calls in progress at 3. Each is one relay WebSocket and one streamed model reply: a few short text messages a second. On top come the dashboard's 5-second re-read per open tab and the phones' 30-second backstop. All of it is waiting on the network. One asyncio event loop holds thousands of such connections, and the code is written for one: `verify_token` is a plain `def`, so FastAPI runs the blocking firebase-admin call on its thread pool, and `Storage._run` puts boto3 on an executor (01 §8, "everything in the request path is asynchronous").

**What ties the service to one process.**

1. A relay WebSocket lives in the process that accepted it (01 §8, ADR-001 §2).
2. The scheduler (06 §2, not built yet) is a loop inside FastAPI behind a database lock. Each uvicorn worker runs its own lifespan, so N workers start N loops and the lock idles N−1 of them.
3. Each process opens its own connection pool. `app/core/db.py` takes SQLAlchemy's defaults, 5 connections plus 10 overflow: up to 15 per process.

**Where the slow requests come from.** The worst p99 values (1.4–2.3 s) are one or two requests per bucket, while p50 stays under 60 ms in every bucket but one that held a single request. These are first requests to a fresh process, not load, and since 2026-10-16 every wake-up makes a fresh process. 7d82902 turned `sleepApplication` on for `api` and `dashboard`, and ce19cf7 turned it on for `Postgres` and removed `drainingSeconds: 200` from `api`. Both contradict 01 §9 ("sleeping when idle turned off") and the configuration in ADR-001 §2. Railway's serverless page says the first request to a slept service pays a cold boot and "may return a 502 Bad Gateway". With `api` and `Postgres` both asleep, that request waits for two wake-ups in a row. On the SOS path the target is under 5 seconds from press to alert (06 §5).

## Decision

1. **One uvicorn process, one replica.** No `--workers`. The Dockerfile's `CMD` stays as it is.
2. **`api` and `Postgres` never sleep, and `api` drains for 200 seconds.** Restore ADR-001 §2's `deploy: { sleepApplication: false, drainingSeconds: 200 }` on `api` and drop `sleepApplication` from `Postgres`, in both environments. `dashboard` may keep sleeping: it serves static files, and an open DAS tab talks only to `api`.
3. **No nginx.** Railway's edge already terminates TLS and proxies WebSockets, and `dashboard/Caddyfile` already does the static-file work.
4. **No Redis.** Postgres already holds the queue, the timers and the locks (06 §2, `pg_advisory_xact_lock` in `campaigns` and `staff`). 01 §10 rules out a broker for the MVP.

## Options considered

### A. More uvicorn workers (`--workers 4` to `8`)

| Dimension | Assessment |
|---|---|
| Complexity | Low to switch on, medium to make correct |
| Cost | About 70 MB more memory per worker |
| Scalability | Adds CPU, which is not the constraint |
| Team familiarity | High |

**Pros:** one flag; uses cores that are otherwise idle.

**Cons:**
- **Connections run out.** 8 workers × 15 = 120 connections, doubled to 240 while two copies overlap in a deploy, against Postgres's default `max_connections` of 100. Even 4 workers reach 120 during a deploy. Workers would need a hand-tuned `pool_size`.
- **The scheduler runs N times.** The lock keeps it correct, but each idle loop still holds a connection and ticks.
- **No speed-up to measure.** Peak CPU is under 8% of one core. A second process only helps when one event loop is busy computing.

### B. nginx in front of uvicorn

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a second process in the container, or a second service |
| Cost | Small |
| Scalability | None: buffering and TLS are already done at Railway's edge |
| Team familiarity | Medium |

**Pros:** request buffering, rate limits, one domain for dashboard and API (no CORS).

**Cons:**
- **Another hop on the relay WebSocket.** nginx's default `proxy_read_timeout` of 60 seconds cuts a quiet socket, and calls last up to 3 minutes. Every timeout and upgrade header becomes something to get right before spike S8.
- **Another place to break the Twilio signature.** It already depends on `--proxy-headers` and `PUBLIC_BASE_URL` (ADR-001 §2). One more proxy is one more `X-Forwarded-*` to check.
- **Railway's edge and Caddy already do the job.** Caddy is the stack's nginx already.

### C. Redis

| Dimension | Assessment |
|---|---|
| Complexity | Medium: a new service, client and failure mode |
| Cost | A third always-on service per environment |
| Scalability | Needed only with several API copies |
| Team familiarity | Medium |

**Pros:** shared cache, pub/sub between copies, rate-limit counters, a job queue.

**Cons:**
- **Nothing to cache.** p50 is 15 ms. firebase-admin already caches Google's signing keys in the process.
- **A second source of truth for timers.** 06 §2 keeps every timer in a database row so that a restart loses nothing. A Redis queue would put them in two places.
- **Nobody to talk to.** Pub/sub joins API copies, and there is one. With more copies, Postgres `LISTEN`/`NOTIFY` comes first.
- **One more failure mode.** It would need its own row in the failure table (06 §1).

### D. One process, awake, draining (chosen)

| Dimension | Assessment |
|---|---|
| Complexity | Lowest: two settings in `railway.ts` |
| Cost | Roughly $2 per environment per month to stay awake: about 0.2 GB of memory for `api` and `Postgres` together at Railway's $10 per GB-month; CPU rounds to zero (estimate) |
| Scalability | Hundreds of times the measured load; 3 calls at once is the binding limit, and it is a business rule |
| Team familiarity | High: it is what 01 §9 and ADR-001 already describe |

## Trade-off analysis

The load is I/O-bound and small, and the design pins state to one process on purpose. More workers, nginx and Redis each add parts for a constraint the service does not have: CPU, buffering, cross-process state. The constraint it does have is latency on the first request, and it comes from sleep, not size. Turning sleep off costs a few dollars a month and puts the service back where the spec says it should be.

## Consequences

- **Easier:** a wake-up no longer stands between an SOS and an alert. Once the scheduler exists, it would keep `api` awake anyway: its database query every few seconds counts as outbound traffic, so sleep would save nothing then.
- **Unchanged:** a deploy still drops live calls. uvicorn closes open WebSockets with code 1012 when it shuts down, so `drainingSeconds` alone keeps no call alive. It also needs the SIGTERM handling in ADR-001 §2: release the lock, refuse new relays, wait for open calls. Spike S8 decides it.
- **To revisit:**
  - *Workers or a second service*, when one event loop is busy. Measure first: per-turn latency during the S1 and whole-system rehearsals (06 §5), and event-loop lag. If they grow, move call sessions into their own service along the module lines in 01 §8 before adding workers, and set `pool_size` explicitly.
  - *Redis*, when more than one API copy must push live events to each other, and only after `LISTEN`/`NOTIFY` falls short.
  - *nginx*, never on its own: if rate limiting is ever needed, Caddy can do it.

## Action items

1. [ ] `.railway/railway.ts`: `api` → `deploy: { sleepApplication: false, drainingSeconds: 200 }`; remove `sleepApplication: true` from `db.deploy`. Plan and apply to `staging`, then `production` (`.railway/AGENTS.md`).
2. [ ] Redeploy `api` and `Postgres` after applying: Railway applies sleep settings only to a new container.
3. [ ] When building the scheduler: count calls in progress from database rows, never in memory, so the "free line" limit (06 §2) holds with any number of processes.
4. [ ] With spike S8: implement and test the SIGTERM drain (ADR-001 action item 10).
