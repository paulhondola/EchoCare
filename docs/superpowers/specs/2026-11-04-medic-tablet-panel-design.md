# Medic tablet app: the patient panel, consent and „Sună din nou” — design

Date: 2026-11-04. Status: agreed in a grilling session with mockups, for [paulhondola/EchoCare#54](https://github.com/paulhondola/EchoCare/issues/54).

Implements UC-01 step 5, UC-04 („Sună din nou”, withdrawal), UC-12 (the medic row), 03 §7 (a yellow is a warning in the app for the medic), 04 §1–2, 05 §1, G7.

Items marked **(builder's call, settled)** were decided by the writer of this document, not by the product owner. Change them only with a reason.

## Intent

A family doctor registers seniors at the practice on a tablet and is then responsible for following them. Today the medic's home is one grid of their seniors ([SeniorsScreen.kt](../../../android/app/src/main/java/ro/echocare/home/SeniorsScreen.kt)), in name order, with nothing standing out. A senior whose welcome call failed sits in that grid looking like any other, and the medic has no button to try again. The signature endpoint and the withdrawal endpoint exist in the backend with no screen.

This change gives the medic a home with two jobs, **Monitorizare** (who needs me) and **Înregistrare** (register someone), and makes the patients who need the medic impossible to miss: red and yellow first, then the ones whose enrollment is stuck. From the patient the medic can read every call in full, re-queue a failed welcome call, record a withdrawal, and take the optional signature.

## Goals

1. The medic's home is a landing page with two large buttons, „Monitorizare” and „Înregistrare”, each carrying live counts.
2. Monitorizare orders patients by what they need from the medic, red and yellow highlighted, and on a landscape tablet shows list and detail side by side.
3. Per patient: registration details, an enrollment timeline with when each step happened, consent state, call history with full transcripts, the watch's state, and the actions that fit the patient's state.
4. „Sună din nou” re-queues the welcome call of a `wrong_number` or `unreachable` senior, and the senior shows as „În progres” until that call ends.
5. „Retragere consimțământ” on an active patient, with a confirmation.
6. The optional signature (G7) is taken under the consent text it confirms.
7. Every signed-in role sees their own name in the top bar.

## Non-goals

- **Editing one's own profile.** A later issue. The top bar shows the name read-only. Today only DAS edits a medic's name and practice (`PATCH /staff/{userId}`); a self-edit endpoint is that issue's work.
- **Health readings on the cards.** The Wear OS readings are still being built. The card shows the watch's state (`ok`, `not_worn`, `offline`), which exists today, and nothing else from the watch. No placeholder values: made-up readings in a medical app can be mistaken for real ones.
- **Risk factors** (README open question 5).
- **A way back from `refused` or `withdrawn`.** UC-04 has none yet.
- **Dashboard changes.** The new response fields are optional; the dashboard may ignore them. The `GET /enrollments` order change is server-side only.
- **Home node state and room readings** (proposed in 04 §1, tables do not exist).

## Anti-goals

- A patient who needs the medic looking like one who doesn't. Any layout where an `unreachable` senior sits among green ones has failed.
- „Sună din nou” making the patient vanish from view. After pressing it the medic must still see the patient, as „În progres”, until the call ends.
- Refusing „Sună din nou” because the number did not change. A correct number can come back as `wrong_number` (someone else answered, the senior misheard); the medic must be able to simply try again.
- Placeholder or invented health data anywhere.
- Hiding the actions behind menus. The actions that fit the state are visible buttons on the patient.

## Constraints

- **Old clients, new servers** (ADR-001 §2.3). New response fields are optional; nothing is renamed or dropped. The migration only adds nullable columns.
- **Contract changes move together** (AGENTS.md). `04-interfaces.md`, `05-data-model.md`, the backend and `Api.kt` change in the same change. Prefer one component per PR: the backend (with the spec) can land first, then Android.
- **The look is the DAS dashboard's** ([07-dashboard-stitch-spec.md](../../specs/echocare/07-dashboard-stitch-spec.md), [android/app/AGENTS.md](../../../android/app/AGENTS.md)): one dark theme, `Palette` colours (`Rosu`, `Galben`, `Verde`), no rounded corners, 2dp rules, `ui/Components.kt` pieces. This is an Operate surface: familiar patterns, fast scanning, no decoration.
- **User-facing text is Romanian**, in `res/values/strings.xml`.
- **Decode leniently.** Enrollment state, consent decision and method are strings with a fallback, never a Kotlin `enum`.
- Permissions stay in FastAPI. The app hides buttons; the server refuses.

## Backend

### `POST /seniors/{id}/welcome-call` („Sună din nou”)

- **Who:** medic, own senior (the registering medic). Anyone else gets what they get today for a senior outside their reach (`not_found` / `not_allowed`, as the other medic commands).
- **From:** `wrong_number` or `unreachable`. No check on whether the number changed.
- **Effect, in one transaction:** a conditional UPDATE moves the senior to `accepted` (`WHERE enrollment_state IN ('wrong_number','unreachable')`), then queues a welcome call as `queue_welcome_call` does today (trigger `welcome`, attempt 1, due now). Moving back to `accepted` is required: `end_welcome` and `confirm_welcome` only act on an `accepted` senior, and `GET /profile/mock-call` offers a welcome call only to an `accepted` senior. Attempt 1 means the UC-04 retry rules start over: one redial, then `unreachable` again.
- **Answers** the senior as one row of `GET /seniors`, like submit and accept.
- **A repeat** (a double tap: the senior is already `accepted` with a welcome call queued or live) answers the same, 200 with the senior, and queues nothing. This follows 04 §0's rule that a command which queues a call returns the existing one **(builder's call, settled)**.
- **Refused:** any other state → `wrong_state` (an `accepted` senior with no welcome call queued or live is `wrong_state` too: that is not a repeat).
- `accepted_at` / `accepted_by` are **not** changed by this; they record DAS's acceptance.

### Enrollment timestamps

- Nullable `submitted_at`, `accepted_at` (timestamps) and `accepted_by` (user FK) on `seniors`, each set in the same conditional UPDATE that moves the state (submit, accept). Existing rows stay null; no backfill.
- `GET /enrollments` orders by `submitted_at`, then `created_at`, then `id` (nulls first for `submitted_at`: a null means submitted before the stamp existed, so older than any stamped request).
- `GET /seniors/{id}` and the rows of `GET /seniors` add optional `created_at`, `submitted_at`, `accepted_at`.

### Watch state on the rows

The rows of `GET /seniors` add `watch_state`, with the same rule as `GET /seniors/{id}`: set for the senior's caregivers and registering medic, null for anyone else and before the first check-in. 04 §1 already lists it on the rows as added with its work; this is that work. It saves the tablet one detail read per card **(builder's call, settled)**.

### Consent state on the senior

`GET /seniors/{id}` adds, for every role that can read the senior (04 §1 lists „consent state” as added with its work). **A signature is not a consent decision here** **(builder's call, settled)**: G7 and UC-01 say consent is given on the welcome call, and a signature is taken before it. These fields can't change meaning after release (ADR-001 §2.3), so they are kept apart:

- `consent`: the latest consent record with method `call`, `app`, `medic` or `das` (decisions `given`, `refused`, `withdrawn`), as `{decision, method, at}`, or null. Records with method `signature` are left out.
- `consent_given_at`: when the latest `given` record from method `call` or `app` was made, or null. It survives a later withdrawal, so the timeline still dates „Activ”.
- `signed_at`: when the latest signature was recorded, or null. Lets the page say „Semnat pe tabletă” and hide the prompt to sign again.

### The signature's consent text

The text signed on the tablet, version **`v1-semnatura`**, is a server constant in `backend/app/voice/dialogue.py` beside `v1` and `v1-app`, and is written out in 04 §2's signature row, so the server and the spec say what the version means **(builder's call, settled)**. The text is the mock card's wording with its closing question „Sunteți de acord?” replaced by „Semnând mai jos, sunteți de acord.”. The app carries the same text in `strings.xml`; a change to it is a new version on both sides.

### Spec and tests

- Update 04 §1 (the new fields, `watch_state` on the rows, the `GET /enrollments` order), 04 §2 (the welcome-call row: the move to `accepted`, no number check, the repeat, the refusals; it currently says „after a corrected number”, which this change drops on purpose; the signature row names `v1-semnatura` and its text), 05 §1 (`SENIOR` gets the three columns).
- Tests: welcome-call from each allowed state, the repeat, the refusals, the queued call's attempt and due time, a full second round ending `unreachable` again, the mock card offered again after the move; timestamps set on submit and accept and untouched by the welcome call; enrollment order; `watch_state` on the rows by role; `consent`, `consent_given_at` and `signed_at`, including a signed-but-not-yet-called senior (`consent` null) and a withdrawn one (`consent_given_at` kept).

## Android

### Top bar, every role

The shared top bar ([Frame.kt](../../../android/app/src/main/java/ro/echocare/home/Frame.kt) `TopBar`) shows the signed-in person's initials and display name in the right corner, read-only, from `GET /profile`. No tap target yet; the profile issue will add one. On a phone where it doesn't fit beside the title, initials only **(builder's call, settled)**.

### Medic home: the landing page

Two large buttons side by side in landscape, stacked on a phone.

- **Monitorizare**, with counts: red, yellow, and „de rezolvat” (`wrong_number` + `unreachable`), as `Chip`s in the code colours. Counts come from `GET /seniors?role=medic`, already read for the panel. A red or yellow count is the medic's in-app warning (03 §7: yellow is a warning in the app, red also arrives as a push since #53).
- **Înregistrare**, with the number of unfinished drafts.

### Înregistrare

Opens to „Pacient nou” plus the medic's drafts to continue, newest first **(builder's call, settled)**. „Pacient nou” stays the existing four-step form ([enroll/](../../../android/app/src/main/java/ro/echocare/enroll/)): Pacient → Adresă → Aparținători → Verificare. The last step gains the consent section:

- The consent text `v1-semnatura` (see Backend), shown above the signature box. Above the text: „Opțional: consimțământul se confirmă și la apelul de bun venit.”
- A signature box drawn with a finger, „Semnați aici”, with „Șterge” to clear it and „Salvează semnătura” to send it.
- **The signature is sent on its own, when the medic presses „Salvează semnătura”** **(builder's call, settled)**, not with submit. By the review step the senior already exists (step 1's „Continuă” saves the draft), so a draft that can't be submitted yet (no caregiver) can still be signed. It goes to `POST /seniors/{id}/signature`: strokes as lists of `[x, y]` normalised to 0–1 against the box, at most 5,000 points in all (thin the points if a signature runs over), and the text version. Once saved, the section shows „Semnat” with the time; a failure shows a `Banner` and keeps the drawing for another try.
- The section shows only while the senior is `draft`, `submitted` or `accepted` (what the server accepts) and not yet signed (`signed_at` null).

### Monitorizare: the panel

**Groups, in this order** (each a section with a label and a 2dp rule):

| Group | Who | Card highlight |
|---|---|---|
| Roșu și galben | `active` with code `red`, then `yellow` | `Rosu` / `Galben` edge and tint |
| De rezolvat | `wrong_number`, `unreachable` | blue edge (`Link`) |
| În progres | `accepted` (welcome call queued or ringing; freshly accepted by DAS too) | none |
| Verde | `active` with code `green`, or `active` with no code yet | none |
| La DAS | `submitted` | none |
| Inactivi (collapsed) | `refused`, `withdrawn` | dimmed |

Drafts are not in Monitorizare; they are in Înregistrare. A state the app doesn't know goes into Inactivi under its raw name.

**Within a group** **(builder's call, settled):** red before yellow, each oldest `since` first (longest waiting at the top); the other groups by name, as the API returns them.

**A card shows:** the code chip or the state label, the form of address and name, the reason (for a code) or the state in words (for the rest: „Număr greșit”, „Nu a putut fi contactat”, „Apel de bun venit în curs”), and the watch's state from the row's `watch_state` when it isn't `ok`. A time shows only where the row has one: `since` for a code, `submitted_at` for La DAS. De rezolvat and În progres cards show no time; nothing records when a senior became `wrong_number` or `unreachable`, and the call list on the patient has the times **(builder's call, settled)**.

**Layout:** on a wide screen (tablet landscape, `WindowWidthSizeClass` expanded or a width breakpoint of the builder's choice), list on the left (about 40%) and the selected patient on the right; nothing is selected at first, and the right pane says „Alegeți un pacient”. On a narrower screen, the list, and a tap opens the patient's page (today's navigation). The patient detail is one composable used in both places.

**States:** loading shows grey placeholder cards, not a spinner. An empty list shows „Încă nu aveți pacienți” with a button to Înregistrare. A failed read uses the existing `Failure` handling. Refresh as today: refresh push plus the timed re-read.

### The patient (detail pane or page)

Built on today's [SeniorScreen.kt](../../../android/app/src/main/java/ro/echocare/home/SeniorScreen.kt) details, adding:

- **Enrollment timeline:** Ciornă → Trimis → Acceptat → Activ, each with its date (`created_at`, `submitted_at`, `accepted_at`, `consent_given_at`). Steps not reached are dimmed. An end state adds its own last step: Refuzat or Retras dated by `consent.at`; Număr greșit or Nu a putut fi contactat with no date. Null timestamps (older rows) show no date.
- **Consent:** the latest decision, how (apel, aplicație, medic, DAS) and when, from `consent`; separately „Semnat pe tabletă” with the date when `signed_at` is set.
- **Calls:** the full list from `GET /seniors/{id}/calls`, each opening its transcript from `GET /calls/{id}/transcript`: the turns and the answers, in time order. Reuse the DAS incident page's transcript rendering where it fits.
- **Watch state.**
- **Actions, by state:**

| State | Actions |
|---|---|
| `wrong_number`, `unreachable` | „Sună din nou” (primary), „Editează datele” |
| `active` | „Retragere consimțământ” (danger tone) |
| `submitted`, `accepted` | „Semnătură” if not yet signed (opens the consent text and box) |
| any state past `draft` | „Editează datele” (today's form) |

Drafts never reach the patient page (`openFor` in `Routes.kt` opens the form); they sign in the form.

**„Editează datele” in every state.** Today `editable()` in `Routes.kt` allows it only for `draft` and `submitted`, with a comment saying PUT refuses past `submitted`. The backend, 04 §2 and SE9 allow editing in any state, and seniors §9.1 says the app's limit lasts until the app is updated. Widen `editable()` and fix that comment and the one on `updateSenior` in `Api.kt`. A changed number queues no call (04 §2), so after saving a new number for a `wrong_number` or `unreachable` senior the patient shows: „Numărul a fost schimbat. Apăsați «Sună din nou» ca să-l sunăm.”

„Sună din nou” sends at once, no confirmation; on success the patient moves to „În progres”. A refusal shows through `refusalOf`.

„Retragere consimțământ” asks first, as a dialog: „Retrageți consimțământul pentru {formă de adresare}? Nu va mai primi apeluri. Nu se poate anula.” with „Retrage” and „Renunță”. On success the patient moves to Inactivi.

### Tests

JVM unit tests: the grouping and order (every enrollment state and code, unknown states, nulls); which actions show in which state; the timeline's steps and dates for each state; stroke normalisation and the 5,000-point limit. No instrumented tests (none exist in the repo).

## Done when

On a tablet emulator in landscape against the local stack with seeded data: the medic sees a red patient above a green one, opens their transcript, and presses „Sună din nou” on a senior marked `unreachable`, who then shows under „În progres” and gets a welcome call card in the senior app. A withdrawal and a signature also go through. Still usable on a phone emulator.

## Left to the builder

- Exact breakpoint and pane widths; whether to use the Material 3 adaptive list-detail scaffold or a plain `Row`.
- Placeholder card count and shape.
- The signature canvas implementation and point thinning.
- How the transcript view is shared with the DAS incident page.
- Whether the backend lands as its own PR before Android (recommended).
