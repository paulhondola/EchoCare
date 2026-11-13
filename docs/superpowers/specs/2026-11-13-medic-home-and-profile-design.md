# Medic home and profile page: design

Date: 2026-11-13. Size: small change (Android, one optional API field, spec lines).

## Why

The medic's home is two tiles, Monitorizare and Înregistrare, so it routes to other screens and does
no work of its own. The spec puts nothing on the medic's critical path: DAS takes reds, and codes
keep the medic informed (03 §7, UC-12). The work only the medic can do is a to-do list: finish
drafts (UC-01), fix failed welcome calls (UC-04) and confirm medical profiles (design 2026-11-13).
Today that list is split across two tiles, and profiles to confirm arrive only as a push notice.

Some people hold several roles (a DAS member who is also a medic and a caregiver). Switching sits
in the ⋮ menu and sends them back through the full-screen role picker.

## Goals

- The medic lands on their tasks, most important first, each one tap from where it is done.
- Reds and yellows stay visible on home, as counts.
- Anyone with several roles switches in one tap from a profile page opened from the initials
  square in the top bar.

## Non-goals

- No changes to Monitorizare, the patient page, the form or the dashboard.
- No actions on home itself: a task opens the patient's page, where the action already exists.
- No count of open incidents on the profile page: DAS alerts already reach every signed-in device
  whatever role the app is in (03 §7).
- No editing of one's own name (staff names change only through `PATCH /staff/{userId}`).

## Anti-goals

- A home that hides a red. The count strip always shows red and yellow when there are any.
- A state or code this build does not know producing a task, a crash or a wrong label
  (ADR-001 §2.3). Unknown values make no task; the patient still shows in Monitorizare.

## Approaches

1. **An optional field on each `GET /seniors` row (picked).** The app derives every task from the
   list it already reads; one field adds the medical record's state. Rules live in plain Kotlin
   beside `Panel.kt` and are tested on the JVM.
2. **A new `GET /tasks` endpoint.** Rules in one place on the server, but a new contract and tests
   for a list one Android screen reads, and old APKs meet task kinds they cannot draw.
3. **No API change.** Either one medical-record read per patient on every refresh, or no profile
   tasks on home. The first is wasteful; the second defeats leading with tasks.

## Design

### API (contract change: `04-interfaces.md`, backend, Android together)

`GET /seniors` rows gain `medical_record_state`: `pending`, `review`, `confirmed`, `failed`, or null
when no record is attached. Filled for the senior's registering medic only, null for everyone else
(01 §6: the record is the registering medic's until confirmed). Optional, so old APKs and the
dashboard ignore it. Android decodes it as a string.

### Medic home (layout A, chosen with mockups)

```
┌ EchoCare / Acasă ─────────── [+ Pacient nou] [IP] ┐
│ [1 roșu] [2 galben] [14 verzi] [3 la DAS]  Toți pacienții → │
│ DE FĂCUT · 5                                     │
│ ▌Doamna Maria Popescu  confirmă întrebările  [Revizuiește] │
│ ▌Domnul Ion Stan       număr greșit           [Corectează] │
│ ▌Doamna Elena Dinu     nu răspunde            [Sună din nou] │
│ ▌Gheorghe Marin        ciornă                 [Continuă] │
└──────────────────────────────────────────────────┘
```

- **Tasks, in this order** (decided: sorted by importance; the order itself is my call):
  1. `medical_record_state == "review"`: confirm the questions → patient page.
  2. `medical_record_state == "failed"`: the analysis failed → patient page (my call: grouped with 1).
  3. `wrong_number`: correct the number → patient page.
  4. `unreachable`: call again or visit → patient page.
  5. `draft`: continue → the form, filled in.
- Not tasks: `refused`, `withdrawn`, an unsigned consent (optional, G7), codes, `submitted`.
- **Strip:** counts of red, yellow, green (active seniors) and `submitted` (la DAS), each shown only
  when above zero, and „Toți pacienții →” to Monitorizare.
- „Pacient nou” moves to the top bar. The Înregistrare screen and route go away; drafts are tasks.
- Empty list: „Totul e la zi”.
- Kept: the notifications prompt and the „Trimis la DAS.” banner after a submit.

### Profile page (full page, chosen with mockups)

- The initials square in the top bar becomes a button on every role's home and opens `ProfileRoute`.
  The ⋮ menu goes away; its two items live here.
- Shows: initials, display name, the phone number from the Firebase sign-in (hidden if absent).
- **Rol:** each granted role in `ROLES` order with one line of what its home shows; the current one
  marked „Activ”. Tapping another calls `AuthViewModel.pickRole` and lands on that role's home. A
  person with one role sees it alone, with nothing to tap.
- **Notificări:** whether alerts are allowed on this device, using the same check as
  `NotificationsPrompt`.
- „Ieșire” at the bottom.
- The role picker at sign-in stays for the first choice. `switchRole()` and „Schimbă rolul” go.

## Left to the builder

- Order within one task kind (proposed: longest waiting first where the row has a time, drafts by
  `created_at`, welcome-call problems by `accepted_at`; otherwise the API's order).
- The Romanian wording of each task line and button, and of each role's description line.
- How the tablet two-column layout of the old tiles maps onto one list (a single centred column with
  a maximum width is enough).
- Tests: JVM tests for task derivation and order, including unknown states and a null
  `medical_record_state`; backend tests that the field is filled only for the registering medic.
