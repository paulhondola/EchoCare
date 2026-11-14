# Senior data export (GDPR Art. 15 & Art. 20): design

Date: 2026-11-14. Status: draft for approval.

## Why

PR #75 added GDPR right to erasure (Art. 17) and documented **export for any senior (Art. 15 right of access, Art. 20 data portability)** as the highest-value follow-up in [docs/pitch/security-gdpr-brief.md](../../pitch/security-gdpr-brief.md). Export walks the exact same table owners as erasure—reading instead of deleting—so DAS or the registering medic can download a single, complete, machine-readable `.json` file of everything EchoCare holds about a senior in one click from the dashboard.

## Goals

1. DAS (for any senior past `draft`) or the registering medic (in any state) can export all personal data stored about a senior in one action via `GET /api/seniors/{senior_id}/export` and from the senior's dashboard panel.
2. Every table that holds data about the senior or their calls is included in the structured JSON payload, and a reflection guard test over `Base.metadata.tables` enforces that no table pointing at `seniors.id` or `calls.id` is omitted.
3. Need-to-know access (`01 §6`) and internal-field fences (`05 §2`) hold: DAS receives `medical_record.items` and the 10-minute pre-signed `pdf_url` only when the medical record is `confirmed` (the registering medic receives them in every state), and internal columns (`source_text`, `storage_key`, `twilio_call_id`, `dialed_at`, `firebase_uid`) are never exposed.
4. Pitch and spec documents reflect that both erasure (Art. 17) and export (Art. 15, 20) are implemented.

## Non-goals

- Bundling the PDF into a `.zip` archive. The JSON includes the 10-minute pre-signed `pdf_url` (when visible to the caller), keeping the export a fast single-JSON download with no S3 streaming overhead.
- Export buttons in the Android or iOS apps. The endpoint already permits the registering medic; mobile UI can follow later.
- Allowing `Role.senior` or `Role.caregiver` to call the endpoint. Access matches `editable_senior()`, identical to erasure.

## Constraints

- Only a table's owner queries or shapes its domain records; packages import only from layers below their own (`pyproject.toml`, ADR-005).
- API changes only add (ADR-001 §2.3).
- Contract changes move together: `04-interfaces.md`, the backend, the dashboard, and the pitch/spec docs in one change.

## Approaches considered

| | Approach | Trade-off | Verdict |
|---|---|---|---|
| A | Place export inside `app/erasure/` alongside `erase_senior` | Reuses the existing package, but mixes erasure and export under the name `erasure` | Rejected |
| B | New sibling package `app/export/` in the same layer (`calls \| agent \| system \| memory \| erasure \| export`), calling read helpers on each owning package | Clean separation of Art. 15/20 export from Art. 17 erasure, fits ADR-005 layering, shares the same owner-walk mental model | **Chosen** |
| C | Client-side assembly in the dashboard from existing endpoints | Misses tables with no full-history endpoint (`consents`, all `senior_summaries` versions, raw `events` with GPS, `answers`, resolved `incidents` per senior) and makes N+1 requests for call transcripts | Rejected |

## Design

### Export endpoint

`GET /api/seniors/{senior_id}/export` answers **200** with ` SeniorExport` (`application/json`).

| Case | Answer |
|---|---|
| Out of the caller's reach, or erased | 404 `not_found` |
| Reached, but neither the registering medic nor DAS past `draft` | 403 `not_allowed` |
| Otherwise (including during a live call or open incident) | 200, full JSON export |

Access uses `seniors.editable_senior(session, caller, senior_id)`: the registering medic in any state, or DAS for seniors past `draft`. Because export is read-only, it does not block on live calls or unresolved incidents.

After assembling the export, the service logs at `INFO`: `exported senior <id> by user <id>` (no name, no phone number).

### Where the code lives

A new package `app/export/` (`__init__.py`, `router.py`, `service.py`, `schemas.py`), placed in the layer `calls | agent | system | memory | erasure | export` in `backend/pyproject.toml`. The router is mounted under `/api` in `backend/app/main.py`.

Each owning package exposes a read function for its rows:

| Owner | Function | Rows it reads |
|---|---|---|
| `seniors` | `export_senior_data(session, senior)` | `SeniorView` (profile, address, enrollment state, timestamps, `medic`, `caregivers`), `consents` (ordered by `at`, `id`), `senior_summaries` (all versions ordered by `created_at`, `id`), `watch_state` (`WatchView` or `None`), and `watch_readings` (ordered by `measured_at`, `id`) |
| `codes` | `export_senior_codes(session, senior_id, call_ids)` | Current `senior_statuses` row (if any) and `status_reports` for `call_ids` grouped by `call_id` (ordered by `at`, `id`) |
| `incidents` | `export_senior_incidents(session, senior_id)` | `events` (ordered by `measured_at`, `id`) and `incidents` (ordered by `opened_at`, `id`) |
| `voice` | `export_calls(session, senior_id)` | `calls` for the senior (ordered by `due_at`, `id`), plus their `call_turns` (ordered by `position`) and `answers` (ordered by `at`, `id`) |
| `medical` | `export_record(session, senior_id, storage, *, full)` | Reads `current_record(session, senior_id)` and returns `await view_of(record, storage, full=full)` if present, else `None` (`full=True` when the caller is the registering medic, so DAS sees `items` and `pdf_url` only when `state == confirmed`) |

### JSON payload shape (`SeniorExport`)

- `exported_at`: UTC timestamp when the export was generated.
- `senior`: `SeniorView` (id, full_name, form_of_address, phone_e164, phone_is_landline, street, street_number, block, staircase, floor, apartment, intercom_code, key_holder, landmark, call_window, enrollment_state, submitted_at, accepted_at, medic, caregivers).
- `status`: `{code, reason, since, source_call_id} | None`.
- `consents`: list of `{id, decision, method, text_version, call_id, evidence, signature_strokes, at}`.
- `summaries`: list of `{id, call_id, previous_id, content, model, created_at}`.
- `medical_record`: `MedicalRecordView | None` (`{state, uploaded_at, analyzed_at, confirmed_at, items, pdf_url}`).
- `watch`: `{state: WatchView | None, readings: list[WatchReadingView]}`.
- `events`: list of `{id, type, source, measured_at, received_at, snapshot, latitude, longitude, location_accuracy_m, located_at, call_id}`.
- `incidents`: list of `{id, opened_by_call_id, status, reason, opened_at, taken_at, resolved_at, outcome, note}`.
- `calls`: list of `{id, trigger, campaign_id, previous_call_id, attempt, starting_severity, state, due_at, started_at, ended_at, final_severity, final_certainty, reason, summary, welcome_outcome, handover_answered, turns, answers, reports}` where:
  - `turns`: list of `{position, speaker, kind, content, confidence, at}`
  - `answers`: list of `{field, value, clear, quote, at}`
  - `reports`: list of `{source, severity, certainty, reason, quote, at}`

### Dashboard

In `dashboard/src/services/api.ts`:
- `exportSenior(seniorId: string): Promise< Record<string, unknown> >` calling `GET /api/seniors/${seniorId}/export`.

In `dashboard/src/features/seniors/SeniorDetails.svelte`:
- In the bottom action bar alongside „Șterge toate datele”, add an outline button with `<Icon name="download" size={14} />`: **„Exportă datele”** (showing **„Se exportă…”** and disabled while in flight).
- Clicking it fetches `exportSenior(summary.id)`, serializes with `JSON.stringify(data, null, 2)`, creates a `Blob` (`application/json`), and triggers an `<a download="echocare-senior-${summary.id}.json">` click, then revokes the object URL.
- If the request fails, displays an inline alert `Nu am putut exporta datele (...)` in `text-rosu-fg`.

### Spec and pitch updates

- `docs/specs/echocare/04-interfaces.md` §1: add `GET /seniors/{id}/export` under Reads.
- `docs/specs/echocare/06-operations.md` §4: mention `GET /seniors/{id}/export` alongside erasure under Data.
- `docs/pitch/security-gdpr-brief.md` and `docs/pitch/trust-sheet.html`: move senior data export (Art. 15, 20) from candidate fixes to implemented strengths.

## Testing

- **Full-senior export & table-coverage guard (`backend/tests/export/test_service.py`):**
  - Populates a senior with every linked entity (caregiver grant, status, consent, summary version, watch state and readings, event with location, incident, call with turns, answer, status report, and medical record) and asserts that `export_senior` returns every piece of data accurately.
  - Reflection guard test over `Base.metadata.tables`: checks every table with a foreign key to `seniors.id` or `calls.id` is accounted for in the export test, so adding a new table in the future fails the test until included.
- **API & access control (`backend/tests/export/test_api.py`):**
  - 200 for the registering medic (including unconfirmed medical record `items` and `pdf_url`).
  - 200 for DAS on an `active` senior: when the medical record is `review` (unconfirmed), `items` and `pdf_url` are `None`; when `confirmed`, both are populated.
  - 200 even when a call is live or an incident is open.
  - 403 `not_allowed` for DAS on a `draft` senior and for a caregiver on an `active` senior.
  - 404 `not_found` for a senior outside the caller's reach.
  - S3 error when generating `pdf_url` still answers 200 with `pdf_url: null`.
- **Architecture contracts:** `test_only_the_owner_writes_a_table` and `lint-imports` pass with `app/export` placed in `pyproject.toml`.
- **Dashboard checks:** `npm run check` and `npm test` pass in `dashboard/`.
