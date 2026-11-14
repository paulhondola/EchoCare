# Security quick wins and senior erasure: design

Date: 2026-11-14. Status: draft for approval.

## Why

Judges at the hackathon asked about security and GDPR. The team brief ([docs/pitch/security-gdpr-brief.md](../../pitch/security-gdpr-brief.md)) lists what counts for and against EchoCare. This change removes the cheapest "against" items. Five hygiene fixes a technical judge could spot in minutes, plus a right-to-erasure feature (GDPR Art. 17), so "can a senior's data be deleted?" gets a yes and a button to show on stage, not "only drafts".

## Goals

1. DAS, or the registering medic, can erase a senior and everything stored about them, in one action, from the dashboard.
2. Nothing personal about that senior survives in the database or the file store, except a log line saying who erased which senior ID and when.
3. Five quick wins: no public API docs in production, no Android backup of app data, the medical PDF deleted with a draft, dependency scanning, and safe security headers on the dashboard.
4. The pitch material says erasure exists, once it does.

## Non-goals

- Export of a senior's data (Art. 15, 20). Same walk over the tables, later.
- Anonymised retention of incidents. The team chose full deletion.
- Deleting the Firebase sign-in account. The API holds no Firebase service account (auth-layer AL11); the brief names this as a known limit.
- An erase button in the Android app. The medic's screen can come later; the endpoint already allows the medic.
- A script-restricting Content-Security-Policy on the dashboard. Firebase phone sign-in loads reCAPTCHA from Google domains, and a wrong CSP breaks sign-in on stage.
- A push to tell open apps the senior is gone. Open Android screens re-read on their backstop timer and get `not_found`, as they already do for a removed grant; the dashboard re-reads every few seconds.
- Retention periods, an access log, rate limiting. Candidates for later.

## Anti-goals

- Erasing a senior during a live call or an open incident. DAS must finish handling an emergency before its record can go.
- Weakening the owner-writes rule (ADR-005) or the draft delete's existing guards.
- A dependency audit that can block a deploy. Railway waits for CI, so a new advisory published on demo day must not hold back a fix.

## Constraints

- Only a table's owner writes it (ADR-005, `test_only_the_owner_writes_a_table`). Packages import only from layers below their own (`pyproject.toml`).
- API changes only add (ADR-001 §2.3). `DELETE /seniors/{id}` keeps its meaning (draft only); old Android apps call it for drafts.
- Contract changes move together: `04-interfaces.md`, the backend and the dashboard in one change. Android is unaffected.
- Work branches from current `main`, not `ios-port`, which predates PR #72.

## Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | One migration sets `ON DELETE CASCADE` on every foreign key to a senior or a call; erasure is one `DELETE FROM seniors` | Least code, the database prevents orphans. But it rewrites about 15 constraints, removes the guard `delete_draft` relies on (the call foreign key refuses a senior with calls), and deletes other packages' rows behind their backs, which the owner-writes test can't see | Rejected |
| B | Each owning package gets a "delete everything for this senior" function that doesn't commit; one erase step calls them children-first and commits once | About 7 small functions, and the order matters. Fits ADR-005, keeps every delete visible and testable, needs no migration. The list of functions doubles as a map of where personal data lives | **Chosen** |
| C | Extend `DELETE /seniors/{id}` to every state | Changes an endpoint old apps call for drafts only | Rejected |
| D | An admin SQL script | Can't be demoed, bypasses access checks | Rejected |

## Design

### Erasure endpoint

`POST /api/seniors/{senior_id}/erase`, no body, answers **204**.

| Case | Answer |
|---|---|
| Out of the caller's reach, or already erased | 404 `not_found` (as for any senior out of reach) |
| Reached, but neither the registering medic nor DAS past `draft` | 403 `not_allowed` |
| A call for the senior is live: `ringing` or `in_progress`, or `queued` with `dialed_at` set (handed to Twilio) | 409 `call_live` |
| An incident for the senior is `open` or `in_progress` | 409 `incident_open` |
| Otherwise | 204, everything deleted |

Access is exactly `seniors.editable_senior()`: the registering medic in any state, DAS for seniors past `draft`. It also locks the senior row, so an edit or a second erase waits. Any enrollment state is allowed: draft, submitted, accepted, active, refused, withdrawn, unreachable.

### Where the code lives

A new package `app/erasure/` (`router.py`, `service.py`), placed in the layer `calls | agent | system | memory | erasure` in `pyproject.toml`. That layer can import every owner it needs (`medical`, `incidents`, `voice`, `seniors`, `auth`, `codes`). The router is mounted in `main.py`.

Each owner gets one function, named `erase_senior_rows(session, senior_id, call_ids)` or close to it, that deletes its own rows and doesn't commit:

| Owner | Rows it deletes |
|---|---|
| `codes` | `status_reports` for the senior's calls; the senior's `senior_statuses` row |
| `incidents` | the senior's `events` and `incidents` |
| `seniors` | `consents`, `senior_summaries`, `watch_readings`, `watch_state` for the senior; then the `seniors` row (grants cascade already) |
| `voice` | `answers` and `call_turns` for the senior's calls; then all the senior's `calls` in one statement (the `previous_call_id` self-reference resolves within one statement) |
| `medical` | returns the PDF's storage key, if any, then deletes the `medical_records` row |
| `auth` | users who held a grant on this senior (the senior's own user, caregivers) and now hold none; their push tokens cascade |

### Order, in one transaction

1. `editable_senior()`: access check and row lock.
2. The guards above; a refusal changes nothing.
3. Read the senior's call IDs, and the user IDs holding a grant on this senior.
4. Delete children first: `codes`, then `incidents` (events and incidents point at calls), then `seniors` children (consents and summaries point at calls), then `voice`, then `medical` (keep the key), then the `seniors` row, then `auth` users left with no grants.
5. Commit.
6. After the commit, delete the PDF from S3 (`StorageService.delete`). A failure there is logged with the senior ID and the key and doesn't fail the request: the database is already clean, and the orphaned file has no row pointing to it.
7. Log at INFO: `erased senior <id> by user <id>`. No name, no number.

A wrong order fails loudly with a foreign-key error and rolls back; it never leaves half a senior.

Staff users are never deleted, since they keep their staff grants. The users deleted are those who held a grant on this senior and hold none after the senior's grants cascade. Senior and caregiver users are referenced nowhere else by design (they grant nothing, record nothing, take no incidents). If one ever is, the foreign key fails the erasure and it rolls back. That's loud and safe, and the full-senior test would show it.

### Draft delete keeps its PDF no longer

`DELETE /seniors/{id}` (draft only, registering medic) keeps its contract and its guard. After the delete commits, the router also deletes the draft's medical PDF from S3, if it had one. The router reads the storage key before the delete, since the `medical_records` row cascades with the senior. Same rule as erasure: an S3 failure is logged, not raised.

### Dashboard

On the senior's detail page (`dashboard/src/features/seniors/SeniorDetails.svelte`), a destructive action at the bottom, „Șterge toate datele”. It opens a confirmation built into the page, not the browser's `confirm()`. The confirmation names the senior and says, in Romanian, that everything is deleted permanently and can't be undone. Its confirm button reads „Șterge definitiv”. On 204, the dashboard returns to the seniors list with a short notice „Datele au fost șterse”. On `call_live` or `incident_open`, it shows the reason in Romanian and keeps the senior. Exact wording is the builder's, in the dashboard's existing voice.

### Quick wins

| Fix | Where | Detail |
|---|---|---|
| API docs off in production | `backend/app/main.py` | `docs_url`, `redoc_url`, `openapi_url` are `None` when `APP_ENV=production`; local and staging keep them. A test asserts `/api/docs` is 404 in production |
| No Android backup | `android/app` and `android/wear` manifests, `res/xml` rules | `allowBackup="false"`, and data extraction rules that exclude everything from cloud backup and device transfer, so a Firebase session can't be restored onto another device |
| PDF deleted with a draft | above | |
| Dependency scanning | `.github/dependabot.yml`; `backend.yml`, `dashboard.yml` | Dependabot weekly for `uv` (`/backend`), `npm` (`/dashboard`), `gradle` (`/android`) and GitHub Actions. An audit step in each CI workflow (`pip-audit` over the locked dependencies, `npm audit --omit=dev --audit-level=high`) with `continue-on-error: true`: it reports, it never blocks (anti-goal) |
| Security headers | `dashboard/Caddyfile` | On every response: `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-Frame-Options: DENY` plus `Content-Security-Policy: frame-ancestors 'none'` (restricts framing only, not scripts), `Permissions-Policy: camera=(), microphone=(), geolocation=()`, `Strict-Transport-Security: max-age=31536000`. Sign-in must still work on staging afterwards |

### Spec and pitch updates, in the same change

- `04-interfaces.md`: a row for the erase command, the two new refusal reasons, and the draft delete row saying its PDF is deleted too.
- `05-data-model.md` §5: retention gains "until erased"; a note that erasure deletes every row in the owner order.
- `06-operations.md` §4: an erasure row under Data; the docs-off and headers rows under Access.
- `docs/pitch/security-gdpr-brief.md` and the trust sheet: erasure moves from gap to strength, with the Firebase-account limit named; the quick wins drop off the gap list.

## Testing

- **One test erases a fully populated senior** (consents, a summary, watch state and readings, events, an incident resolved, calls with turns, answers and status reports, a medical record, the senior's and a caregiver's grants) and asserts that no row in any table mentions the senior or its calls, that the senior and caregiver users are gone, and that the medic and DAS users remain. This is the test that catches a wrong order.
- Refusals: out of reach (404), a caregiver (404 or 403, as `editable_senior` answers), DAS on a draft (403), a live call (409 `call_live`), a dialed queued call (409), an open incident (409 `incident_open`). Each leaves every row in place.
- A queued, undialed call is deleted, not refused.
- S3: the PDF key is deleted after commit; an S3 error still answers 204 and logs.
- Draft delete: the PDF is deleted; the existing draft tests still pass.
- `test_only_the_owner_writes_a_table` and `lint-imports` pass with the new package placed.
- Docs off: `/api/docs` and `/api/openapi.json` 404 with `APP_ENV=production`, 200 locally.
- Dashboard: a unit test for the confirmation flow if the dashboard's test setup covers components; otherwise a manual check against the local stack.
- Caddy headers: checked with `curl -I` against the local dashboard container, and sign-in checked on staging after merge.

## Calls made by Claude, for review

- The new package `erasure` and its layer.
- Refusal reasons `call_live` and `incident_open`.
- A dialed but still `queued` call counts as live.
- Senior and caregiver users left with no grants are deleted; a stray reference fails the erasure instead of being worked around.
- S3 deletion after the commit, logged on failure, never raised.
- The audit step is report-only.
- HSTS without `includeSubDomains`, since the dashboard sits on a Railway subdomain.

## Left to the builder

- Exact function names and signatures of the owner functions.
- The dashboard's Romanian wording, within the meaning above.
- How `pip-audit` reads the locked dependencies (`uv export` or `uv run --with`).
- Whether the erasure test uses the shared fixtures in `tests/conftest.py` or builds its own senior.
