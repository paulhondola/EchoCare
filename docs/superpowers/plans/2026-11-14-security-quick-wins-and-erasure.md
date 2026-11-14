# Security quick wins and senior erasure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DAS or the registering medic can erase a senior and everything stored about them from the dashboard, and five hygiene gaps a technical judge could spot are closed.

**Architecture:** Each package that owns senior data gets one delete function that doesn't commit. A new `app/erasure/` package calls them children-first in one transaction behind `POST /api/seniors/{id}/erase`, then deletes the medical PDF from S3 after the commit. The quick wins are one small change each in `main.py`, the Android manifests, CI and the dashboard's Caddyfile.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, pytest; Svelte 5, Vite+ (`vp`); Android manifests; GitHub Actions and Dependabot; Caddy 2.

**Spec:** [docs/superpowers/specs/2026-11-14-security-quick-wins-and-erasure-design.md](../specs/2026-11-14-security-quick-wins-and-erasure-design.md)

## Global Constraints

- Branch `security-erasure`, cut from `main`. Commit with the hooks on; no `--no-verify`. End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Only a table's owner writes it (ADR-005). `uv run lint-imports` and `test_only_the_owner_writes_a_table` must pass.
- API changes only add. `DELETE /seniors/{id}` keeps its contract: draft only, registering medic.
- Contract changes move together: `04-interfaces.md`, the backend and the dashboard in the same branch.
- User-facing text is Romanian; code, comments and docs English. Cite spec IDs in new comments (`04 §2`, `ADR-005`).
- Refusals use `refuse(status, reason)` from `app.auth.service`; new reasons are exactly `call_live` and `incident_open`.
- Backend tests use the `echocare_test` database through the fixtures in `backend/tests/conftest.py`.
- The audit steps never fail CI (`continue-on-error: true`).
- No script-restricting CSP on the dashboard; only `frame-ancestors 'none'`.

## Review Focus

1. **A senior with a test call** (`trigger` `test`, from `scripts/place_call.py`) that is ringing: erasure must refuse with `call_live`, although the existing `call_in_progress()` ignores test calls. Pinned in Task 1.
2. **A queued call already handed to Twilio** (`dialed_at` set, state still `queued`): it counts as live. Pinned in Task 1.
3. **A caregiver who also cares for a second senior**: erasing one senior keeps that caregiver's user and their other grant. Pinned in Task 1.
4. **S3 down during erasure**: the request still answers 204, the database is clean, and the key is logged. Pinned in Task 2.
5. **A second erase of the same senior** (double click, retry): 404 `not_found`, no 500. Pinned in Task 2.

---

### Task 1: Owner delete functions and the erase service

**Files:**
- Create: `backend/app/erasure/__init__.py` (empty), `backend/app/erasure/service.py`
- Modify: `backend/app/codes/service.py`, `backend/app/incidents/service.py`, `backend/app/seniors/service.py`, `backend/app/voice/service.py`, `backend/app/medical/service.py`, `backend/app/auth/service.py`
- Modify: `backend/pyproject.toml` (the layers contract: `"calls | agent | system | memory | erasure"`)
- Test: `backend/tests/erasure/__init__.py` (empty), `backend/tests/erasure/test_service.py`

**Interfaces:**
- Consumes: `seniors.service.editable_senior(session, caller, senior_id) -> Senior` (access check, row lock, 404/403).
- Produces, all `async`, none commits except `erase_senior`:
  - `voice.service.call_live(session, senior_id) -> bool`: any call for the senior in `ringing` or `in_progress`, or `queued` with `dialed_at` not null. Test calls included.
  - `voice.service.senior_call_ids(session, senior_id) -> list[uuid.UUID]`
  - `voice.service.erase_calls(session, call_ids: list[uuid.UUID]) -> None`: `answers`, `call_turns`, then `calls`, the calls in one `DELETE`.
  - `incidents.service.incident_unresolved(session, senior_id) -> bool`: `open` or `in_progress`.
  - `incidents.service.erase_senior_incidents(session, senior_id) -> None`: `events`, then `incidents`.
  - `codes.service.erase_senior_codes(session, senior_id, call_ids) -> None`: `status_reports` for those calls, then the `senior_statuses` row.
  - `seniors.service.erase_senior_children(session, senior_id) -> None`: `consents`, `senior_summaries`, `watch_readings`, `watch_states`.
  - `seniors.service.erase_senior_row(session, senior_id) -> None`: the `seniors` row (grants cascade).
  - `medical.service.erase_record(session, senior_id) -> str | None`: the PDF's `storage_key`, if any, after deleting the row.
  - `auth.service.grant_holder_ids(session, senior_id) -> list[uuid.UUID]` (read) and `auth.service.drop_users_without_grants(session, user_ids) -> None`.
  - `erasure.service.erase_senior(session, caller, senior_id) -> str | None`: the whole erasure, committed; returns the PDF key for the router to delete.

- [ ] **Step 1: Write the failing tests** in `tests/erasure/test_service.py`, using `add_user`, `add_senior` and `add_active_senior`:
  - `test_erase_removes_every_row`: builds an active senior with a consent, a senior summary, a watch state and two watch readings, an event, a resolved incident, two ended calls (the second with `previous_call_id` set to the first) with turns, answers and status reports, a senior status, a medical record with a `storage_key`, and a caregiver grant. Runs `erase_senior` as DAS. Asserts that a count of rows mentioning the senior's ID or its call IDs is 0 in each of `seniors, consents, senior_summaries, watch_states, watch_readings, events, incidents, calls, call_turns, answers, status_reports, senior_statuses, medical_records, grants`. Asserts the senior's user and the caregiver's user are gone, the medic and DAS users remain, and the return value equals the record's `storage_key`.
  - `test_erase_by_registering_medic_on_draft`: the registering medic erases a draft; returns `None` (no record).
  - `test_erase_refuses_das_on_draft`: raises `HTTPException` 403 `not_allowed`; the senior remains.
  - `test_erase_refuses_live_call` (parametrized over `ringing`, `in_progress`, and a `test` trigger ringing) and `test_erase_refuses_dialed_queued_call` (`queued`, `dialed_at` set): 409 `call_live`; every row remains.
  - `test_erase_deletes_undialed_queued_call`: a `queued` call without `dialed_at` is erased with the senior.
  - `test_erase_refuses_open_incident` (parametrized `open`, `in_progress`): 409 `incident_open`; every row remains.
  - `test_erase_keeps_caregiver_of_another_senior`: a caregiver with grants on two seniors keeps their user and the other grant.

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && uv run pytest tests/erasure -q`
Expected: FAIL, `ModuleNotFoundError: app.erasure`.

- [ ] **Step 3: Add the owner functions** listed under Interfaces, each in its owner's `service.py`, each a plain `delete()` or `select()` that doesn't commit, with a one-line docstring citing the design.

- [ ] **Step 4: Implement `erase_senior` in `app/erasure/service.py`**, in this order: `editable_senior`; `call_live` → `refuse(409, "call_live")`; `incident_unresolved` → `refuse(409, "incident_open")`; read `senior_call_ids` and `grant_holder_ids`; then `erase_senior_codes`, `erase_senior_incidents`, `erase_senior_children`, `erase_calls`, `erase_record` (keep the key), `erase_senior_row`, `drop_users_without_grants`; commit; `log.info("erased senior %s by user %s", senior_id, caller.user.id)` on logger `echocare.erasure`; return the key. Place `erasure` in the layers contract.

- [ ] **Step 5: Run the tests, the import contracts and the architecture tests**

Run: `cd backend && uv run pytest tests/erasure tests/architecture -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app backend/pyproject.toml backend/tests/erasure
git commit -m "backend: erase a senior through each table's owner, children first (ADR-005)"
```

### Task 2: The erase endpoint, S3 cleanup and the draft PDF

**Files:**
- Create: `backend/app/erasure/router.py`
- Modify: `backend/app/main.py` (mount the router), `backend/app/seniors/router.py` (`delete_senior`), `backend/app/medical/service.py`
- Modify: `docs/specs/echocare/04-interfaces.md` (§2 commands: the erase row, the draft delete row's PDF sentence; the refusal reasons `call_live`, `incident_open`)
- Test: `backend/tests/erasure/test_api.py`, `backend/tests/seniors/` (the existing draft delete tests' file)

**Interfaces:**
- Consumes: `erasure.service.erase_senior` (Task 1); `core.storage.get_storage`, `StorageService.delete(key)`, `StorageError`.
- Produces: `POST /api/seniors/{senior_id}/erase` → 204; `medical.service.record_key(session, senior_id) -> str | None` (read only).

- [ ] **Step 1: Write the failing tests** in `tests/erasure/test_api.py`, overriding `get_storage` with a fake that records deleted keys and can be set down (as `tests/medical/test_api.py` does):
  - `test_erase_answers_204_and_deletes_pdf`: DAS erases an active senior with a medical record; 204; the fake recorded the record's key; `GET /api/seniors/{id}` is 404.
  - `test_erase_twice_is_not_found`: the second `POST` answers 404 `not_found`.
  - `test_erase_with_storage_down_still_204`: the fake raises `StorageError`; 204; the senior row is gone; the log (`caplog`) names the senior ID and the key.
  - `test_erase_refusal_bodies`: a live call gives 409 with `{"detail": {"reason": "call_live"}}`; an open incident gives 409 `incident_open`; a caregiver gives 404.
  - `test_delete_draft_deletes_pdf` (next to the existing draft delete tests): a draft with a medical record; `DELETE /api/seniors/{id}` answers 204 and the fake recorded the key; with storage down, still 204.

- [ ] **Step 2: Run them to see them fail**

Run: `cd backend && uv run pytest tests/erasure/test_api.py tests/seniors -q -k "erase or delete_draft_deletes_pdf"`
Expected: FAIL, 404 on the new route.

- [ ] **Step 3: Implement `erase(senior_id, caller: current_caller, session, storage) -> Response` in `app/erasure/router.py`**: `erase_senior`, then, if a key came back, `await storage.delete(key)` inside `try/except StorageError` that logs a warning with the senior ID and the key. Mount in `main.py`. Add `record_key` and use it in `delete_senior`: read the key before `delete_draft`, delete it from storage after, same `try/except`.

- [ ] **Step 4: Update `04-interfaces.md`**: a command row for `POST /seniors/{id}/erase` (who: the registering medic, or DAS for a senior past `draft`; effect: deletes the senior and every row about them, and the PDF; refusals `call_live`, `incident_open`; a repeat is `not_found`), and the draft delete row: "its PDF is deleted from the file store too".

- [ ] **Step 5: Run the backend checks**

Run: `cd backend && uv run pytest -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend docs/specs/echocare/04-interfaces.md
git commit -m "backend, docs: POST /seniors/{id}/erase; a deleted draft takes its PDF (04 §2)"
```

### Task 3: The dashboard's erase button

**Files:**
- Modify: `dashboard/src/services/api.ts`, `dashboard/src/features/seniors/SeniorDetails.svelte`, `dashboard/src/features/seniors/Seniors.svelte`
- Create: `dashboard/src/utils/erase.ts`
- Test: `dashboard/src/utils/erase.test.ts`

**Interfaces:**
- Consumes: `POST /api/seniors/{id}/erase` (Task 2); `apiFetch`, `refused`, `ApiError` in `api.ts`.
- Produces: `eraseSenior(id: string): Promise<void>` in `api.ts` (throws `ApiError` on refusal); `eraseRefusalText(reason: string | undefined): string` in `utils/erase.ts`; a new prop `onErased: () => void` on `SeniorDetails`.

- [ ] **Step 1: Write the failing test** `utils/erase.test.ts`:
  - `eraseRefusalText("call_live")` → `"Un apel este în desfășurare. Încercați după ce se încheie."`
  - `eraseRefusalText("incident_open")` → `"Seniorul are un incident nerezolvat. Rezolvați-l mai întâi."`
  - `eraseRefusalText("not_found")` → `"Seniorul nu mai există."`
  - `eraseRefusalText(undefined)` → `"Ștergerea a eșuat. Încercați din nou."`

- [ ] **Step 2: Run it to see it fail**

Run: `cd dashboard && npx vp test src/utils/erase.test.ts`
Expected: FAIL, cannot resolve `./erase`.

- [ ] **Step 3: Implement** `eraseRefusalText` and `eraseSenior` (same shape as `acceptSenior`, no body returned). In `SeniorDetails.svelte`, at the bottom of the panel, a destructive „Șterge toate datele” button that reveals an in-page confirmation (no `confirm()`). It names the senior and reads „Toate datele despre {nume} vor fi șterse definitiv: apeluri, transcrieri, fișa medicală, consimțăminte. Acțiunea nu poate fi anulată.” It has buttons „Anulează” and „Șterge definitiv”; the latter is disabled while the request runs. On success call `onErased()`; on `ApiError` show `eraseRefusalText(err.reason)` under the buttons. In `Seniors.svelte`, `onErased` closes the dialog, removes the senior from the list and shows „Datele au fost șterse” using the list's existing notice pattern, or a plain status line if it has none.

- [ ] **Step 4: Run the dashboard checks**

Run: `cd dashboard && npx vp check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npx vp build`
Expected: all pass.

- [ ] **Step 5: Check it by hand against the local stack** (`docker compose up --watch` from the repo root, `uv run python scripts/seed.py` in `backend/`): sign in as a seeded DAS at http://localhost:5173, open a seeded senior without an open incident, erase it, and see the notice and the senior gone. Open a senior with an open incident and see the `incident_open` text.

- [ ] **Step 6: Commit**

```bash
git add dashboard/src
git commit -m "dashboard: erase a senior from its panel, with an in-page confirmation (04 §2)"
```

### Task 4: API docs off in production

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/core/test_docs.py`

**Interfaces:**
- Consumes: `Settings.app_env`, `AppEnv.production`.
- Produces: `docs_urls(env: AppEnv) -> dict[str, str | None]` in `main.py`, the three FastAPI keyword arguments.

- [ ] **Step 1: Write the failing test** `test_docs_hidden_in_production`: `docs_urls(AppEnv.production) == {"docs_url": None, "redoc_url": None, "openapi_url": None}`; `docs_urls(AppEnv.staging)["docs_url"] == "/api/docs"`, likewise for `local`.

- [ ] **Step 2: Run it to see it fail**

Run: `cd backend && uv run pytest tests/core/test_docs.py -q`
Expected: FAIL, `ImportError: docs_urls`.

- [ ] **Step 3: Implement `docs_urls`** and pass `**docs_urls(settings.app_env)` to `FastAPI(...)`.

- [ ] **Step 4: Run the backend checks** (as in Task 2 Step 5). Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add backend/app/main.py backend/tests/core/test_docs.py
git commit -m "backend: no OpenAPI docs in production"
```

### Task 5: No Android backup of app data

**Files:**
- Modify: `android/app/src/main/AndroidManifest.xml`, `android/wear/src/main/AndroidManifest.xml`
- Modify: `android/app/src/main/res/xml/backup_rules.xml`, `android/app/src/main/res/xml/data_extraction_rules.xml`; and the wear module's if it has its own (`android/wear/src/main/res/xml/`)

**Interfaces:** none.

- [ ] **Step 1: Set `android:allowBackup="false"`** in both manifests. Replace the sample rules with real ones: `backup_rules.xml` excludes every domain (`root`, `file`, `database`, `sharedpref`, `external`); `data_extraction_rules.xml` excludes every domain under both `<cloud-backup>` and `<device-transfer>`. If the wear manifest has no rules, `allowBackup="false"` alone is enough there.

- [ ] **Step 2: Build both apps and run the unit tests**

Run: `cd android && ./gradlew :app:assembleDebug :wear:assembleDebug test`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 3: Commit** (the pre-push hook runs Android's checks)

```bash
git add android
git commit -m "android: no backup or device transfer of app data, so a session can't move devices"
```

### Task 6: Dependency scanning

**Files:**
- Create: `.github/dependabot.yml`
- Modify: `.github/workflows/backend.yml`, `.github/workflows/dashboard.yml`

**Interfaces:** none.

- [ ] **Step 1: Write `.github/dependabot.yml`**, `version: 2`, weekly updates for `uv` at `/backend`, `npm` at `/dashboard`, `gradle` at `/android`, `github-actions` at `/`, each with `open-pull-requests-limit: 5`.

- [ ] **Step 2: Add a report-only audit step** after the tests in each workflow, with `continue-on-error: true`: in `backend.yml`, `uv export --locked --no-dev --format requirements-txt --no-hashes | uvx pip-audit -r /dev/stdin --disable-pip`; in `dashboard.yml`, `npm audit --omit=dev --audit-level=high`.

- [ ] **Step 3: Run both audit commands locally** from their folders to confirm they execute (findings are fine, a usage error is not).

- [ ] **Step 4: Commit**

```bash
git add .github
git commit -m "ci: Dependabot, and report-only dependency audits for backend and dashboard"
```

### Task 7: Security headers on the dashboard

**Files:**
- Modify: `dashboard/Caddyfile`

**Interfaces:** none.

- [ ] **Step 1: Add one site-wide `header` block** at the top of the site (it applies to every `handle`, errors included): `X-Content-Type-Options nosniff`, `Referrer-Policy strict-origin-when-cross-origin`, `X-Frame-Options DENY`, `Content-Security-Policy "frame-ancestors 'none'"`, `Permissions-Policy "camera=(), microphone=(), geolocation=()"`, `Strict-Transport-Security "max-age=31536000"`.

- [ ] **Step 2: Check the headers and sign-in locally**

Run (repo root; Compose's `dashboard` is the Vite dev target, so build the Caddy stage directly): `docker build -t echocare-dash-check dashboard && docker run --rm -d -p 3000:3000 -e PORT=3000 --name dash-check echocare-dash-check && curl -sI http://localhost:3000/ | grep -iE "x-content-type|referrer|x-frame|content-security|permissions|strict-transport"; docker stop dash-check`
Expected: all six headers. Then sign in at http://localhost:5173 with a Firebase test number to confirm reCAPTCHA still loads. The dev server doesn't serve the Caddy headers, so staging after merge is the real sign-in check; note it in the PR.

- [ ] **Step 3: Commit**

```bash
git add dashboard/Caddyfile
git commit -m "dashboard: security headers, framing blocked, no script CSP (Firebase sign-in)"
```

### Task 8: Spec and pitch material

**Files:**
- Modify: `docs/specs/echocare/05-data-model.md` (§5), `docs/specs/echocare/06-operations.md` (§4)
- Modify: `docs/pitch/security-gdpr-brief.md`, `docs/pitch/trust-sheet.html`

**Interfaces:** none.

- [ ] **Step 1: Spec.** `05 §5`: the "Kept" rows become "Kept until the senior is erased", and a paragraph: erasure deletes every row about the senior through each owner, children first (design 2026-11-14), and the PDF; only a log line with the IDs remains; the Firebase sign-in account is not deleted (AL11). `06 §4`: under Data, an "Erasure" row; under Access, "API docs off in production", "Dashboard security headers", and "Dependency scanning".

- [ ] **Step 2: Pitch.** In the brief, move erasure and the five quick wins from "What works against us" into "What works for us"; keep gap rows 1, 3–8 and 10 and renumber; in the Q&A, the erasure answer becomes "Yes: DAS or the medic presses one button, and everything about the senior goes, the PDF included. The Firebase sign-in record is the one thing we can't delete yet." In the trust sheet, drop "Erasure and export of a senior's data on request" from "Before a real pilot", replace it with "Export of a senior's data on request", and add a "Right to erasure" item to "For the technical reader". Republish the trust sheet to its existing artifact URL (`https://claude.ai/artifact/3NQ2Umr2bAtZdWDoh2Vu84`) from the session that owns it.

- [ ] **Step 3: Commit**

```bash
git add docs
git commit -m "docs: erasure and the quick wins in the spec and the pitch material"
```
