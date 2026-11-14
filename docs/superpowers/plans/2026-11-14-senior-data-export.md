# Senior Data Export (GDPR Art. 15 & Art. 20) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** DAS or the registering medic can export all personal data stored about a senior as a single machine-readable JSON file via `GET /api/seniors/{senior_id}/export` and from the senior's dashboard panel.

**Architecture:** Each owning package (`codes`, `incidents`, `seniors`, `voice`, `medical`) provides a read function for its senior-linked rows. A new `app/export/` package in the top layer (`calls | agent | system | memory | erasure | export`) calls them in one transaction behind `GET /api/seniors/{senior_id}/export`, applying `editable_senior` access rules and `medical.service.view_of` need-to-know filtering.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic 2, pytest; Svelte 5, TypeScript, Vite+ (`vp`).

**Spec:** [docs/superpowers/specs/2026-11-14-senior-data-export-design.md](../specs/2026-11-14-senior-data-export-design.md)

## Global Constraints

- Branch `gdpr-export`, cut from `main`. Commit with the hooks on; no `--no-verify`.
- Package layering and ownership (ADR-005): `uv run lint-imports`, `test_only_the_owner_writes_a_table`, and `test_package_inits_import_nothing` must pass (`__init__.py` files stay empty).
- API changes only add (ADR-001 §2.3). Contract changes move together (`04-interfaces.md`, backend, dashboard).
- User-facing text is Romanian; code, comments and docs English. Cite spec IDs in new comments (`04 §1`, `ADR-005`).
- Refusals use `refuse(status, reason)` from `app.auth.service`.
- Internal-only columns (`MedicalRecord.source_text`, `MedicalRecord.storage_key`, `Call.twilio_call_id`, `Call.dialed_at`, `User.firebase_uid`) must never appear in the export payload.

## Review Focus

1. **DAS exporting a senior with an unconfirmed (`review` or `pending`) medical record**: `medical_record.items` and `medical_record.pdf_url` must be `None` (01 §6 need-to-know), whereas the registering medic gets both. Pinned in Task 1 and Task 2.
2. **Stale/minimal `SummaryVersion.content` JSON in `senior_summaries`**: `SummaryVersion.content` is exported as raw `dict[str, Any]` so historical versions (or `{}` in tests) are never dropped by current `SummaryContent` validation. Pinned in Task 1.
3. **Export during a live call or open incident**: unlike erasure, export is read-only and must succeed (`200`) while a call is `ringing`/`in_progress` or an incident is `open`. Pinned in Task 2.
4. **S3 failure while presigning the medical PDF URL**: `view_of` catches `StorageError` and sets `pdf_url=None`; the export still answers `200`. Pinned in Task 2.
5. **A new table added later pointing at `seniors.id` or `calls.id`**: `test_every_senior_table_is_exported` inspects `Base.metadata.sorted_tables` and fails until added to `EXPORTED_TABLES`. Pinned in Task 1.

---

### Task 1: Owner read functions and `app/export/` service & schemas

**Files:**
- Create: `backend/app/export/__init__.py` (empty), `backend/app/export/schemas.py`, `backend/app/export/service.py`
- Modify: `backend/app/codes/service.py`, `backend/app/incidents/service.py`, `backend/app/seniors/service.py`, `backend/app/voice/service.py`, `backend/app/medical/service.py`
- Modify: `backend/pyproject.toml` (layer contract: `"calls | agent | system | memory | erasure | export"`)
- Test: `backend/tests/export/__init__.py` (empty), `backend/tests/export/test_service.py`

**Interfaces:**
- Consumes:
  - `seniors.service.editable_senior(session, caller, senior_id) -> Senior`
  - `seniors.service.senior_view(session, senior) -> SeniorView`
  - `medical.service.current_record(session, senior_id) -> MedicalRecord | None`
  - `medical.service.view_of(record, storage, *, full: bool) -> MedicalRecordView`
- Produces:
  - `codes.service.export_senior_codes(session, senior_id, call_ids) -> tuple[SeniorStatus | None, dict[uuid.UUID, list[StatusReport]]]`: current `SeniorStatus` row (or `None`) and `StatusReport` rows grouped by `call_id` ordered by `StatusReport.at, StatusReport.id`.
  - `incidents.service.export_senior_incidents(session, senior_id) -> tuple[list[Event], list[Incident]]`: `Event` rows ordered by `Event.measured_at, Event.id`, and `Incident` rows ordered by `Incident.opened_at, Incident.id`.
  - `seniors.service.export_senior_children(session, senior_id) -> tuple[list[Consent], list[SummaryVersion], WatchState | None, list[WatchReading]]`: `Consent` ordered by `Consent.at, Consent.id`; `SummaryVersion` ordered by `SummaryVersion.created_at, SummaryVersion.id`; `WatchState` (or `None`); `WatchReading` ordered by `WatchReading.measured_at, WatchReading.id`.
  - `voice.service.export_calls(session, senior_id) -> tuple[list[Call], dict[uuid.UUID, list[CallTurn]], dict[uuid.UUID, list[Answer]]]`: `Call` rows ordered by `Call.due_at, Call.id`, `CallTurn` rows grouped by `call_id` ordered by `CallTurn.position`, and `Answer` rows grouped by `call_id` ordered by `Answer.at, Answer.id`.
  - `medical.service.export_record(session, senior_id, storage, *, full: bool) -> MedicalRecordView | None`
  - `export.schemas.SeniorExport` (and nested Pydantic models `ExportStatus`, `ExportConsent`, `ExportSummary`, `ExportWatch`, `ExportWatchReading`, `ExportEvent`, `ExportIncident`, `ExportCall`, `ExportTurn`, `ExportAnswer`, `ExportReport`).
  - `export.service.export_senior(session, caller, senior_id, storage) -> SeniorExport`

- [ ] **Step 1: Write the failing tests** in `backend/tests/export/test_service.py`:
  - `test_export_includes_every_senior_row`: populates an active senior with a caregiver grant, `Consent` (with `evidence` and `signature_strokes`), `SummaryVersion` (with `content={"narrative": "ok"}`), `WatchState`, two `WatchReading` rows, `Event` (with GPS coordinates), `Incident` (`resolved`, with `outcome` and `note`), two `Call` rows (second with `previous_call_id`) with `CallTurn`, `Answer`, and `StatusReport`, `SeniorStatus`, and a `confirmed` `MedicalRecord`. Calls `export_senior` as DAS and asserts every entity's fields match and no internal fields (`source_text`, `storage_key`, `twilio_call_id`, `dialed_at`) appear in `result.model_dump()`.
  - `test_export_redacts_unconfirmed_medical_record_for_das_but_not_medic`: attaches a `review` `MedicalRecord` with `items=[...]` and a fake storage returning a presigned URL; asserts `export_senior` as registering medic includes `items` and `pdf_url`, while as DAS `medical_record.state == "review"` and both `items` and `pdf_url` are `None`.
  - `test_export_refuses_das_on_draft`: raises `HTTPException` 403 `not_allowed`.
  - `test_every_senior_table_is_exported`: reflection guard over `Base.metadata.sorted_tables` asserting the set of tables with `senior_id`/`call_id` or FKs to `seniors`/`calls` equals `EXPORTED_TABLES`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/export/test_service.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.export'`.

- [ ] **Step 3: Add owner read helpers and `app/export/schemas.py` + `app/export/service.py`**
  - Add `"calls | agent | system | memory | erasure | export"` in `backend/pyproject.toml`.
  - Implement `export_senior_codes`, `export_senior_incidents`, `export_senior_children`, `export_calls`, and `export_record` in their respective owner `service.py` files.
  - Implement `SeniorExport` in `backend/app/export/schemas.py` and `export_senior` in `backend/app/export/service.py` (checking `editable_senior`, computing `is_medic = Role.medic in caller.roles and senior.medic_id == caller.user.id`, gathering owner data, logging `exported senior %s by user %s` on logger `echocare.export`).

- [ ] **Step 4: Run tests, import contracts, and linter**

Run: `cd backend && uv run pytest tests/export/test_service.py tests/architecture -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/pyproject.toml backend/tests/export
git commit -m "backend: export a senior's data through each table's owner (ADR-005)"
```

### Task 2: `GET /api/seniors/{senior_id}/export` endpoint and API contract

**Files:**
- Create: `backend/app/export/router.py`
- Modify: `backend/app/main.py`
- Modify: `docs/specs/echocare/04-interfaces.md`
- Test: `backend/tests/export/test_api.py`

**Interfaces:**
- Consumes: `export.service.export_senior`, `export.schemas.SeniorExport`, `auth.service.current_caller`, `core.db.get_session`, `core.storage.get_storage`.
- Produces: `GET /api/seniors/{senior_id}/export` → `200 SeniorExport`.

- [ ] **Step 1: Write the failing API tests** in `backend/tests/export/test_api.py`:
  - `test_export_200_for_das_and_medic`: verifies `GET /api/seniors/{id}/export` returns 200 with full JSON structure for DAS on an active senior and for the registering medic on a draft senior.
  - `test_export_succeeds_during_live_call_and_open_incident`: creates a `ringing` call and an `open` incident for the senior; `GET /api/seniors/{id}/export` answers 200 and includes both.
  - `test_export_with_storage_down_still_200`: overrides `get_storage` with a failing fake (`StorageError`); `GET /api/seniors/{id}/export` answers 200 with `medical_record.pdf_url is None`.
  - `test_export_refusals`: DAS on a draft → 403 `not_allowed`; caregiver on an active senior → 403 `not_allowed`; unrelated medic → 404 `not_found`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && uv run pytest tests/export/test_api.py -q`
Expected: FAIL (404 / 405 on `/api/seniors/{id}/export`).

- [ ] **Step 3: Implement `backend/app/export/router.py`, mount in `backend/app/main.py`, and document in `docs/specs/echocare/04-interfaces.md`**
  - Define `@router.get("/seniors/{senior_id}/export", response_model=SeniorExport)` in `backend/app/export/router.py`.
  - Include `export_router` under `/api` in `backend/app/main.py`.
  - Add the `GET /seniors/{id}/export` row to `docs/specs/echocare/04-interfaces.md` §1 Reads.

- [ ] **Step 4: Run full backend test suite and checks**

Run: `cd backend && uv run pytest -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/export/router.py backend/app/main.py backend/tests/export/test_api.py docs/specs/echocare/04-interfaces.md
git commit -m "backend, docs: GET /seniors/{id}/export endpoint (04 §1)"
```

### Task 3: Dashboard „Exportă datele” button and spec/pitch updates

**Files:**
- Modify: `dashboard/src/services/api.ts`, `dashboard/src/features/seniors/SeniorDetails.svelte`
- Modify: `docs/specs/echocare/06-operations.md`, `docs/pitch/security-gdpr-brief.md`, `docs/pitch/trust-sheet.html`

**Interfaces:**
- Consumes: `GET /api/seniors/{id}/export` (Task 2); `apiFetch`, `refused` in `dashboard/src/services/api.ts`; `Icon` (`name="download"`) in `dashboard/src/ui/Icon.svelte`.
- Produces: `exportSenior(seniorId: string): Promise<Record<string, unknown>>` in `dashboard/src/services/api.ts`.

- [ ] **Step 1: Add `exportSenior` to `dashboard/src/services/api.ts` and the download button to `dashboard/src/features/seniors/SeniorDetails.svelte`**
  - In `api.ts`:
    ```ts
    export async function exportSenior(seniorId: string): Promise<Record<string, unknown>> {
      const r = await apiFetch(`/api/seniors/${seniorId}/export`);
      if (!r.ok) throw await refused(r);
      return (await r.json()) as Record<string, unknown>;
    }
    ```
  - In `SeniorDetails.svelte`: add state `exporting = $state(false)` and `exportError = $state<string | null>(null)`, and `async function downloadExport()` that fetches `exportSenior(summary.id)`, creates a `Blob([JSON.stringify(data, null, 2)], { type: "application/json" })`, triggers `<a download="echocare-senior-${summary.id}.json">`, and revokes the URL; on error sets `exportError = failed("exportul datelor", err)`. Place the button `<Icon name="download" size={14} />{exporting ? "Se exportă…" : "Exportă datele"}` alongside „Șterge toate datele” in the bottom action area.

- [ ] **Step 2: Update `06-operations.md`, `security-gdpr-brief.md`, and `trust-sheet.html`**
  - `docs/specs/echocare/06-operations.md` §4: add a Data row for **Export** (`GET /seniors/{id}/export`, GDPR Art. 15, 20).
  - `docs/pitch/security-gdpr-brief.md`: mention one-click JSON export alongside erasure in the 30-second answer, Security table, GDPR table (add `Right of access and portability (15, 20)`), and remove export from the "Candidate fixes" list.
  - `docs/pitch/trust-sheet.html`: add right of access/portability (`GET /seniors/{id}/export`) alongside right to erasure and remove "Export of a senior's data on request" from the "Before a real pilot" gap list.

- [ ] **Step 3: Run dashboard checks**

Run: `cd dashboard && npx vp check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npx vp build`
Expected: all PASS.

- [ ] **Step 4: Commit**

```bash
git add dashboard/src docs/specs/echocare/06-operations.md docs/pitch/security-gdpr-brief.md docs/pitch/trust-sheet.html
git commit -m "dashboard, docs: export a senior's data as JSON from its panel (04 §1)"
```
