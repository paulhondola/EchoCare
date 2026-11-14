# Senior equipment, declared at registration

Design, 2026-11-14. Touches UC-01, UC-03, UC-13, UC-15, `04 §2`, `05` (seniors).

## Intent

When a medic registers a senior (UC-01), they record which devices the senior uses: the EchoCare app on their own phone, a watch, a home node. The people who look after the senior then see only what applies. Today DAS always draws the watch panel, and for a senior with no watch it says „Ceasul nu a trimis încă date.”, which reads exactly like a broken watch. Declared equipment lets the system tell the two cases apart:

- **Not declared:** show nothing for that device.
- **Declared but never reported:** show a device warning, so someone goes and sets it up.

A senior with an old phone that can't install apps gets none of these. They only take the wellbeing calls, and that is a normal, complete enrollment.

## Goals

- The tablet registration form (Android and iOS) records the equipment, and an edit can change it later.
- DAS's senior page shows the watch panel only for a senior with a watch, and warns about a declared device that has never reported.
- The medic and caregiver phone screens show the same warning chip.

## Non-goals

- Building the home node. It landed separately on main (P20–P27); a declared node warns until its first room reading.
- Serial numbers, per-device history, or when a device was declared.
- Gating anything else on equipment, such as calls, campaigns or "Sunați-mă". Every senior is still called.

## Anti-goals

- Existing seniors suddenly lose their watch panel or get warnings. Not stated (`null`) must behave exactly as today.
- An installed APK that predates this change wipes the equipment on edit (ADR-001 §2.3).
- A device warning that acts like an alert. Like UC-13, it changes no code and pushes no alert.

## Approaches

1. **One `equipment` list on the senior (chosen).** A single nullable column. It rides on the existing form and view: one migration, one contract field.
2. **A devices table.** One row per declared device with timestamps. It has room for serials later, but costs a new endpoint and erasure changes (ADR-005) for data nobody uses yet.
3. **Inferring from data alone.** Dropped: it can't tell "no watch" from "watch never set up", which is the whole point.

Picked 1: it is the smallest change that gives the warning, and moving to 2 later stays additive.

## Decided

**Values.** `equipment` is a list drawn from `"smartphone"`, `"watch"` and `"home_node"`, or `null`.

- `null` means not stated: seniors registered before this change.
- `[]` means none: the senior only takes calls.
- `"smartphone"` means the senior uses the EchoCare app on their own phone. It does not mean simply owning a mobile phone. A phone that can't install apps is not ticked.

**Rules,** checked on the form and enforced by the API with a 422:

- `"watch"` or `"home_node"` requires `"smartphone"`, because both talk only to the senior's phone app (01 §12).
- `"smartphone"` requires the senior's own number to be a mobile. A landline has no senior grant and can't sign in (UC-01 step 3, UC-02).
- *Design call:* the rules are checked only when the body carries `equipment`. Take an old APK that changes the number to a landline and leaves the list out: the stale list stays, and the „nu a deschis aplicația” warning brings it to light. A 422 the old app can't explain would be worse.

**Form („Echipamente”, after the caregivers):**

```
Echipamente
[ ] Telefon cu aplicația EchoCare
[ ] Ceas
[ ] Senzor din casă
```

- Ticking Ceas or Senzor ticks the phone and locks it. The phone box is disabled for a landline.
- A new registration sends the list, so all unticked sends `[]`.
- *Design call:* editing a senior with `null` equipment opens the section with nothing ticked and the line „Nespecificat”. The form leaves `equipment` out of the `PUT` until the medic changes a box. Otherwise, fixing a typo would hide a working watch.
- Copy is Romanian. The exact wording of the hint under the section is left to the builder.

**API (`04 §2`).** `SeniorForm` and `SeniorView` gain an optional `equipment`.

- On `PUT /seniors/{id}`, a body that leaves `equipment` out, or sends it as `null`, keeps the stored value. Old APKs send the whole form without it, and the Android client's JSON writes absent optionals as `null`. So once a senior has a list, it never goes back to "not stated".
- `SeniorView` also gains `app_signed_in: bool`: whether the user holding this senior's `senior` grant has ever signed in (`users.firebase_uid` set). With no senior grant (a shared or landline number, AL7) it is false. It is visible to the same callers as the watch (`sees_watch`).
- *Design call, a known limit:* a sign-in in any role counts, so someone who signed in as a caregiver from the senior's own number counts as signed in. That is acceptable for the MVP. Upgrade to a "signed in as senior" timestamp if the warning misleads in a pilot.
- Both are additive, and old clients ignore them.

**What each screen shows:**

| Equipment | Data | Shown |
|---|---|---|
| `null` | any | as today, unchanged |
| no `"watch"` | any | no watch panel or chip |
| `"watch"` | a `watch_state` row | today's watch panel |
| `"watch"` | no `watch_state` row | device warning „Ceas înregistrat, nu a trimis date” |
| `"home_node"` | no `room` reading yet | device warning „Senzor din casă înregistrat, nu a trimis date” |
| `"home_node"` | a `room` reading | nothing from this feature; the room chip as main shows it (P20) |
| `"smartphone"` | `app_signed_in` false | device warning „Pacientul nu a deschis aplicația” |
| `"smartphone"` | `app_signed_in` true | nothing |

This applies to DAS's senior page ([SeniorDetails.svelte](../../../dashboard/src/features/seniors/SeniorDetails.svelte), [WatchHealth.svelte](../../../dashboard/src/features/seniors/WatchHealth.svelte)) and to the medic and caregiver senior screens on Android (`home/SeniorScreen.kt`) and iOS (`Home/SeniorView.swift`). Warnings use the existing yellow device-warning tone.

*Design call: where and when warnings show.*

- They appear only once the senior is `accepted` or `active`, because before DAS accepts there is nothing to set up yet.
- They appear only to the medic, caregivers and DAS. The senior's own page and step 4 of the registration form never show them.
- In `draft` and `submitted`, the panel-hiding half of the table still applies. A `watch_state` row going `offline` keeps UC-13's behaviour.

**Spec.** In one change, as the contract-change rule requires: UC-01 gains the step, `04 §2` gains the two fields and the PUT rule, `05` gains the column, and UC-13 notes the never-reported warning.

## Left to the builder

- The column type: a Postgres text array, or JSONB with a check.
- How "left out" is detected in the PUT body. Pydantic's `model_fields_set` is one way.
- Ordering and de-duplication of the list.
- Whether the seed script (`backend/scripts/seed.py`) gives mock seniors a mix of equipment. It should, so the dashboard shows each case.
- Tests: the two validation rules, the PUT keep-on-omit rule, and the display table.
