# Medical record profile design

Date: 2026-11-13. Builds on the summary agents ([2026-11-08-senior-summary-agents-design.md](2026-11-08-senior-summary-agents-design.md)) and the medic tablet panel ([2026-11-04-medic-tablet-panel-design.md](2026-11-04-medic-tablet-panel-design.md)).
Spec: UC-01 (registration), UC-04 (welcome call, consent), 01 §6 (who sees what), 04 §2 and §5, 05 §1.

## 1. Intent

Today every wellbeing call asks the same three questions whatever the senior lives with. A senior with diabetes is never asked about her insulin; one with migraines is never reminded of her pills. The medic knows these things and has them on paper: the senior's *fișa medicală*.

The feature: when registering a senior, the medic may attach the fișa medicală as a PDF. After DAS accepts the senior, an analyzer agent reads it once and writes a **medical profile**: the conditions it found, and for each one a ready-made Romanian check question („Ați luat insulina la ora obișnuită azi?”) and what counts as a worrying reply. The registering medic reviews the profile on the tablet, unticks or edits items, and confirms it. From then on each wellbeing call asks one confirmed check.

Why precompute (the user's reasoning): the call model must answer in about a second and re-reads its prompt every turn. Deciding there what to ask a diabetic either gives fast, shallow answers or a long think while the senior waits. The analyzer does the thinking once, with no one on the line; the call model only says a prepared sentence at the right moment.

Done when:
- A medic attaches a PDF while registering a senior (or later, from the senior's page).
- After DAS accepts, within a couple of scheduler ticks, the medic's tablet shows the profile with its items, and the medic gets a push.
- The medic unticks one item, edits another's question, and confirms.
- The next wellbeing call asks one confirmed check in the medic's wording; a worrying reply raises a concern through the existing `raise_concern` tool.
- A scanned PDF (no text layer) gives a profile too.
- DAS sees the confirmed profile, read-only, on the dashboard's senior details.

This is an MVP: the main path plus the simplest safe behaviour for edge cases.

## 2. Goals, non-goals, anti-goals

**Goals**
- Optional upload, never blocking registration, submit or accept.
- Profiles that rest on the document: every item cites words from the fișă.
- No item reaches a call until the medic confirms it (user's choice, option A).
- No extra latency before the agent's first word, as with the summary notes.

**Non-goals**
- Feeding the profile to the post-call summary agent. Later, if wanted.
- Medication schedules, dose tracking, reminders outside calls, or any new push to the senior or caregivers.
- A new recorded answer field. The check's reply lives in the transcript; only a worrying reply has an effect, through `raise_concern`.
- Deleting a record without replacing it. A wrong file is replaced by uploading another.
- The profile in the caregiver or senior roles.
- docling or any ML stack on the API image.

**Anti-goals: a failure even if it technically works**
- An unconfirmed item reaching a call.
- The agent giving medical advice beyond reminding and asking: never a dose, never „luați încă o pastilă”, never a diagnosis. „Ați luat insulina?” is allowed; changing what the senior takes is not.
- An item the document does not support (a made-up condition).
- The fișă or its text reaching a caregiver or the senior, a log line, or a URL that outlives a short presign. This includes a condition or medication named in a concern's reason, which caregivers and the senior read.
- A slow or failing OCR/model call holding the scheduler's lock, delaying dials, or blocking accept.
- A call that grows long: the medical check adds one question, not a list.
- Breaking installed APKs or the older API copy during a deploy (ADR-001 §2.3).

## 3. Approaches considered

| Approach | Trade-off | Verdict |
|---|---|---|
| **A. OCR on the tablet** (PdfRenderer + ML Kit), text sent to the backend | No backend OCR, but the original file is lost (no viewing, no re-analysis with a better model), tables flatten badly, and OCR logic is pinned to APK versions that lag the API | Rejected |
| **B. PDF in S3, backend ingestion queue with docling** | Keeps the file, good layout handling, but docling brings torch and model weights (gigabytes) onto the `api` image and may lack Python 3.14 wheels | Rejected in this form |
| **C. PDF in S3, scheduler-driven analysis: text layer first, DeepInfra OCR model for scans** | Keeps the file, no ML stack on Railway, reuses the scheduler's "row is the queue" pattern and the DeepInfra key already in use | **Chosen** (user picked B's shape; docling swapped for C's extraction, and a separate profile instead of writing into the summary table) |

Why not the summary table: a summary version is written after every call and its validator rejects anything not quoted from the senior's call turns. Medical facts would fail validation or be overwritten by the next call.

## 4. Decisions

| Decision | Choice | Whose |
|---|---|---|
| Where the PDF lives | S3 (`app.core.storage`, its first real user), key `medical-records/{senior_id}/{record_id}.pdf` | User |
| Ingestion | Backend; the scheduler tick finds due records and starts one asyncio task each, outside the lock, as `app/memory/service.py` does for summaries | User |
| Extraction | `pypdfium2` reads the text layer. A page with almost no text (under ~50 characters) is rendered (~150 dpi PNG, via Pillow) and sent to a DeepInfra vision OCR model. New setting `OCR_MODEL`, default `allenai/olmOCR-2-7B-1025`. At most 10 pages are read | Mine |
| Analyzer model | Pydantic AI agent on `SUMMARY_MODEL` (DeepSeek on DeepInfra); structured output; a validator rejects items whose `evidence` is not in the extracted text (normalized as `app.status.alarms.normalize` does), as the summary agent's citation check does | Mine |
| Who confirms | The registering medic, on the tablet (option A). Only confirmed, included items reach calls | User |
| What a suggestion is | A reminder or a check question about the condition and its medication („Ați luat insulina la ora obișnuită azi?”, „Ați avut dureri de cap zilele acestea?”), plus what counts as a worrying reply. Never dosing or advice | User |
| Checks per call | One per wellbeing call, rotating through the confirmed items | Mine |
| A worrying reply | The agent calls the existing `raise_concern` at **yellow** (caregivers alerted when the call ends); no new escalation path. Red stays for what already warrants it, such as acute symptoms | User |
| The concern's reason | **Generic**, never naming the condition or the medication: „Problemă cu medicația de azi”. The reason is the code's `reason`, which caregivers and the senior read in `GET /seniors` and `GET /seniors/{id}`. The medic and DAS get the detail from the transcript. The same holds for the `end_call` summary | User |
| DAS | Reads the confirmed profile on the dashboard's senior details; cannot edit | Mine |
| When analysis runs | After accept (user). Upload is allowed from `draft` onwards; the record waits until the senior is `accepted` or later | User |
| Welcome call | Not blocked by the profile and never uses it | Mine |
| Consent | A new consent text version (`v2`) adds one sentence about the fișă. Wording drafted in §7; DAS must approve it before a real pilot | Mine, DAS approves |

## 5. Design

### 5.1 Data (05-data-model.md)

New table `medical_records`, one current row per senior (a new upload replaces the row's content and resets it):

| Column | Type | Notes |
|---|---|---|
| `id` | uuid pk | Changes on each upload, so the S3 key changes too |
| `senior_id` | uuid, fk seniors, unique | |
| `storage_key` | text | S3 key of the PDF |
| `uploaded_by` | uuid fk users | |
| `uploaded_at` | timestamptz | |
| `state` | enum `pending`, `review`, `confirmed`, `failed` | |
| `source_text` | text, null | Extracted text, kept for re-analysis and the citation check. Never logged, never served |
| `items` | jsonb, null | List of items (below) |
| `model` | text, null | Analyzer model name |
| `analyzed_at` | timestamptz, null | |
| `confirmed_at` / `confirmed_by` | timestamptz / uuid, null | |

An item: `{"condition": str, "question": str, "worrying": str, "evidence": str, "included": bool}`. Romanian for `condition`, `question` and `worrying`; `evidence` is the quote from the document. The analyzer writes at most 6 items, all `included: true`.

Migration only adds. The old API copy ignores the table.

### 5.2 States

```
upload ──► pending ──(senior accepted+, task succeeds)──► review ──(medic confirms)──► confirmed
              │                                                │
              └──(3 failed attempts)──► failed                 └──(reanalyze)──► pending
upload again (any state) ──► pending, items cleared
reanalyze (review, confirmed, failed) ──► pending, items cleared
```

A `pending` record is **due** when its senior's enrollment state is `accepted` or `active` (my call: a senior who refused, withdrew, or was never reached has nothing sent to DeepInfra) and no task for it is running. Confirm and reanalyze are refused with `wrong_state` outside those two states as well. Attempts are counted per process, as summaries are (`_failures`); after 3, the task sets `failed`. If `source_text` is already set (reanalyze), extraction is skipped.

### 5.3 Analysis task (`app/medical/`)

1. Download the PDF from S3.
2. Extract per page with `pypdfium2`; OCR pages with no text layer through `OCR_MODEL` (one chat request per page, image as base64 `image_url`). Store `source_text`.
3. Run the analyzer agent on the text. English instructions; output in Romanian; the document text goes in as data, not instructions (it is untrusted). Rules: only conditions the text states, at most 6, questions short and spoken, no dosing or advice, no item for a condition with nothing to check by phone.
4. Write `items`, `model`, `analyzed_at`, `state = review`, in a session opened after the model returns (none held while it works). If the row's `id` changed meanwhile (a new upload), drop the result.
5. Push the registering medic (§5.6).

No DeepInfra key or no bucket: the step does nothing and the records stay `pending`, as summaries do without a key.

### 5.4 API (04-interfaces.md), all new and additive

| Endpoint | Who | What |
|---|---|---|
| `PUT /seniors/{id}/medical-record` | The registering medic, any state but `refused`, `withdrawn` | Raw body, `Content-Type: application/pdf`, at most 10 MB, must start with `%PDF`. Stores to S3, then upserts the row as `pending`. Answers the record view. Refusals: `too_large` (413), `not_pdf` (415), `storage_unavailable` (503) |
| `GET /seniors/{id}/medical-record` | Registering medic; DAS for a senior past `draft` (as the summary). Others `not_found` | `state`, `uploaded_at`, `analyzed_at`, `confirmed_at`, `items` (with `evidence`), `pdf_url` (presigned, 10 minutes). `204` when none. DAS sees `items` and `pdf_url` only when `confirmed` (my call: the PDF holds everything the profile does, so it waits for the medic too) |
| `POST /seniors/{id}/medical-record/confirm` | Registering medic, state `review` or `confirmed` | Body `{"items": [...]}`: the medic's list, same length and order as stored, with `included` and an edited `question` per item. `condition`, `worrying` and `evidence` are taken from the stored items. Sets `confirmed`. Other states `wrong_state` |
| `POST /seniors/{id}/medical-record/reanalyze` | Registering medic, state `review`, `confirmed` or `failed` | Back to `pending`, items cleared |

The upload uses a raw body, not multipart, so no `python-multipart` dependency. `GET /seniors/{id}` does not change (my call, from planning): the new `medical` package sits above `seniors` in the import layers, so `seniors` cannot read its table; the medic's page reads `GET /seniors/{id}/medical-record` instead.

### 5.5 The call (04 §5)

`answer_context` (`app/calls/service.py`), for wellbeing calls with `notes=True`, also reads the senior's record when `confirmed`, and picks one included item: index = number of the senior's ended answered wellbeing calls, modulo the number of included items. A read failure leaves the call without it, as summary notes do.

`notes_block` gains `medical_check` (`question`, `worrying`) in the same JSON data line, with rules:
- Ask the medical check once, in its words, after the feeling answer. If there is also a follow-up, ask the medical check first.
- Never record it with `record_answer`.
- If the reply matches the worrying description, or the person sounds unsure about medication, call `raise_concern` at yellow with the fixed reason „Problemă cu medicația de azi”. Never name the condition or the medication in a reason or in the `end_call` summary.
- Acute symptoms keep the existing rules: a reply such as „mă doare tare pieptul” is handled as today, red included.

The generic reason rests on the prompt rule only (my call): the loop cannot tell which concern came from the check, so code cannot rewrite the reason without also hiding concerns that have nothing to do with it. A test asserts that the prompt carries the rule, and the end-to-end check reads the stored reason.
- Never give a dose, a diagnosis or advice about medication; only remind and ask.

The fixed rule „no medical advice beyond water, shade or warmth, and rest” stays.

### 5.6 Push

When a record reaches `review`, the registering medic's devices get a visible push with one fixed text, „O fișă medicală e gata de verificat.”, and a `senior_refresh` so the open page reloads. Through the existing `app.notify` machinery. No name in the push (04 §6, P18: pushes carry no name, code or reason), and not on the high-priority `alerts` channel: this is not an emergency. If the app has only that channel, add a normal-priority one (my call).

### 5.7 Android (`:app`, medic role)

- Registration flow: an optional „Fișa medicală (PDF)” file picker (Storage Access Framework, `application/pdf`). The PUT is sent once the draft exists; a failed upload shows an error and does not block submit. Placement in the stepped form is the builder's call.
- Senior page, a new section „Fișa medicală”, sketched:

```
Fișa medicală                         [Deschide PDF]
Stare: așteaptă confirmarea medicului

☑ Diabet zaharat tip 2
   Întrebare: „Ați luat insulina la ora obișnuită azi?"   (editable)
   Îngrijorător: nu a luat-o / nu știe
☐ Hipertensiune

                 [Confirmă]   [Analizează din nou]
```

  State labels: `pending` before accept „Se analizează după acceptarea DAS”, after „Se analizează…”; `failed` „Analiza a eșuat” with „Analizează din nou”; `confirmed` shows the items read-only with „Modifică” to edit and confirm again. „Încarcă altă fișă” replaces the file. „Deschide PDF” opens `pdf_url` in the system viewer.
- New calls in `Api.kt`; all Romanian strings in `strings.xml`.

### 5.8 Dashboard

`SeniorDetails.svelte` shows a read-only „Fișa medicală” block when the record is `confirmed`: conditions and questions, and a link to the PDF. Nothing for other states except a one-line state.

## 6. Constraints

- Contract changes move together (AGENTS.md): 04-interfaces.md, 05-data-model.md, backend, `Api.kt`, dashboard in one change. New fields optional; nothing renamed.
- New dependencies: `pypdfium2`, `pillow` (both with Python 3.14 wheels; to verify at install).
- User-facing text in Romanian; code and docs in English.
- S3 must be configured on staging and production (`S3_*` variables) before the feature works there. Compose already runs MinIO locally. Setting Railway variables is the user's step.
- Logs carry ids and counts, never document text or items.

## 7. Consent text v2 (draft, DAS to approve)

Add before „Puteți renunța oricând.” in both `CONSENT_TEXT` and `CARD_CONSENT_TEXT`: „Dacă medicul a adăugat fișa medicală, o folosim ca să vă punem întrebări potrivite.” Bump the versions to `v2` and `v2-app`. Seniors who consented on `v1` are not asked again (MVP).

The tablet's signature text (`SIGNATURE_CONSENT_TEXT`, `v1-semnatura`) stays as it is (my call): installed APKs carry their own copy and the server accepts only that exact version, so changing it would break them. A signature is not a consent decision (G7), and the call's consent, which does change, is the one that counts.

## 8. Testing

- Backend unit: extraction on a text PDF and on an image-only PDF (OCR model stubbed); analyzer citation validator (rejects an item whose evidence is not in the text); rotation index; `notes_block` with a medical check.
- Backend API: upload (size, type, permissions, replace), get (medic, DAS before and after confirm, caregiver `not_found`), confirm (wrong state, edited question kept, `condition` not overwritable), reanalyze.
- Scheduler: a `pending` record of a `submitted` senior is not due; of an `accepted` one is; a task result for a replaced record is dropped.
- Android: ViewModel tests for the review state; a manual run on the tablet emulator.
- End to end on local Compose with MinIO: upload, accept, profile appears, confirm, a mock call's prompt contains the check.

## 9. Left to the builder

- Exact analyzer and OCR prompts, and the 50-character "no text layer" threshold.
- Where the picker sits in the stepped registration form.
- Push payload shape, following the existing push types.
- How the PDF opens on Android (download to cache and an `ACTION_VIEW` intent, or the browser).
