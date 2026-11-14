# Blood oxygen and ECG from Apple Health

Design, 2026-11-14. Touches UC-12, UC-13, `04 §1`, `04 §3`, `05` (watch tables, §4, §5), ADR-006, ADR-007.

## Intent

The demo needs **real health data** from the senior's Apple Watch on the dispatcher's screen. Heart rate is there already (ADR-006). This adds blood oxygen (SpO2) and the ECG: Apple's verdict, its average pulse and a short trace.

The point is a demo where the numbers are real and fresh. Both can be produced on stage: a blood-oxygen reading takes 15 s in the watch's Blood Oxygen app and an ECG 30 s in the ECG app, and each then appears on the dashboard card. Apple also records blood oxygen in the background, and HealthKit keeps history, so the card has data the moment the senior grants access, before any demo reading.

Who it serves: the DAS dispatcher who opens a senior (ADR-006), and the others who already see the watch (caregivers, registering medic, the senior), through the same scoping.

## Goals

- The senior's iPhone reads blood oxygen and ECG recordings from Apple Health and sends them to FastAPI, the last 24 hours on start and each new one while the app runs.
- FastAPI stores them for 24 hours, like `watch_readings` (05 §4).
- The dashboard's watch card shows the latest blood oxygen with its age, a 24-hour line of the blood-oxygen readings, and the latest ECG: Apple's verdict in Romanian, its average pulse, its age, and a 10 s trace.

## Non-goals

- **Android and Wear OS.** They can't read either signal (ADR-006 "Not done"). Android sends nothing new, and its screens don't change.
- **The iPhone's own screens** (senior, caregiver, medic). Only the dashboard shows the new data in this change.
- **Starting a measurement.** Third-party apps can only read what Apple measured.
- **Breathing rate, heart rate variability, the hypertension flag, wrist temperature.** Discussed and left for later. The table below has room for another `kind`.
- **HealthKit background delivery.** Readings flow while the app runs. Whether background delivery works on a free Personal Team is unverified (ADR-007), and the demo doesn't need it.
- **The full 30 s, 512 Hz ECG.** Only a shortened trace is sent.

## Anti-goals

- **A reading that acts like an alert.** No new event, no call, no code change, no push. A low SpO2 or an AFib verdict is shown, not acted on. EchoCare doesn't diagnose; the ECG label is shown as Apple's.
- **Breaking old clients** (ADR-001 §2.3). Everything is a new endpoint, a new table, or a new optional field.
- **Keeping health data longer than 24 hours,** or exporting less than is stored (GDPR Art. 15) or missing it on erasure (Art. 17).
- **Health data hidden on a card that is showing.** Once the card is visible, the SpO2 and ECG parts show whenever readings exist, whatever the check-in says.

## Constraints

- **iOS is demo-only** (ADR-007), and `ios/AGENTS.md` says not to change the backend or the API contract to make iOS easier. This change isn't for iOS's convenience. It adds data only Apple supplies, so it's a product decision and needs the team's agreement: ADR-008 (proposed) records it.
- **The watch never calls FastAPI** (G5). The phone reads Apple Health, which already holds the watch's data, so the watch app is untouched.
- **Contract changes move together** (root AGENTS.md): `04-interfaces.md`, the backend, `ios/EchoCare/Api/Api.swift` and `ApiClient.swift`, `dashboard/src/services/api.ts`. `android/app/.../Api.kt` doesn't change: Android calls neither endpoint, and `GET /seniors/{id}/watch` is not changed.
- **Only the owner writes a table** (ADR-005). The new table belongs to `seniors`, like `watch_state` and `watch_readings`. `export` and `erasure` reach it through `seniors`' functions.
- **Migrations only add,** and a migration on `main` is frozen (backend/AGENTS.md).
- **Personal Team signing.** HealthKit read works there (ADR-007 spike, confirmed again for ECG voltages by Alex on 2026-11-14). The ECG read needs the `HKElectrocardiogramType` read permission and no further entitlement.
- **User-facing text is Romanian.** Card labels, ECG verdicts and the iPhone's Health permission text.

## Approaches

1. **Its own endpoint and table (chosen).** The iPhone posts each reading to `POST /me/health-readings` with its own time and HealthKit id; FastAPI keeps them in `health_readings` for 24 hours; the dashboard reads `GET /seniors/{id}/watch/health`. Each reading keeps its real measurement time, a re-send is a harmless duplicate, and it works with no watch check-in at all.
2. **Riding on the check-in.** The phone adds the latest SpO2 and ECG to each watch check-in it relays. Dropped: check-ins only flow while the watch workout runs (about an hour, ADR-007), a reading from hours earlier would carry the check-in's time, and a 1,280-point trace would be copied into a `watch_readings` row every minute.
3. **The watch reads Health and sends it over WatchConnectivity.** Dropped: it needs the workout running and a new watch-phone message, and the phone's Health store already has the same data.

Alex picked 1.

## Decided

### The reading, end to end

```
Apple Watch ─(Apple syncs)─► iPhone Health ──► HealthSync (iOS app, senior role)
                                                   │ POST /me/health-readings, one reading per call
                                                   ▼
                                               health_readings (24 h) ◄── scheduler prune
                                                   │
                       GET /seniors/{id}/watch/health ──► WatchHealth.svelte (polls 30 s)
```

### iOS: `HealthSync`

A new file in `ios/EchoCare/Watch/`, beside `Relay.swift`, owned by the app (not the watch target).

- **When it runs:** on a phone signed in with a `senior` grant, from the senior's home appearing (where „Pornește monitorizarea” and the location prompt already live), again right after `startMonitoring()` succeeds, and for as long as the app runs. It doesn't run for the other roles. Starting it twice is a no-op.
- **Permission** (builder check, Claude's call): the two new types join the one request `WatchLink.startMonitoring()` already makes at the „Pornește monitorizarea” tap (`WatchLink.swift:76`): read `HKQuantityType(.oxygenSaturation)` and `HKObjectType.electrocardiogramType()` beside `.heartRate`. One Health prompt, at a moment the senior chose, and no new prompt on launch. `HealthSync` itself never prompts: HealthKit hides read permission, so before the tap its queries simply return nothing. A senior who started monitoring before this change gets the prompt again on the next tap, since `statusForAuthorizationRequest` sees new types. `NSHealthShareUsageDescription` (the two iOS targets in `project.pbxproj`) gets reworded in Romanian to name blood oxygen and the ECG.
- **What it reads:** an `HKAnchoredObjectQuery` per type, starting 24 hours back, with an update handler for new samples. The anchor stays in memory. Each launch re-reads the last 24 hours and re-sends them; FastAPI drops the duplicates. That's a few dozen readings a day at most, and it means nothing has to persist on the phone.
- **Blood oxygen:** the sample's value as a percentage (HealthKit stores a fraction, 0.97), rounded to a whole number; `measured_at` is the sample's `startDate`.
- **ECG:** `classification`, `averageHeartRate` (rounded bpm, optional), and the voltages from `HKElectrocardiogramQuery`, lead I. Shortened on the phone: the first 10 s, averaged down to 128 Hz (512 Hz → groups of 4, computed from `samplingFrequency`, not assumed), as whole microvolts. At most 1,280 points.
- **Sending:** one `POST /me/health-readings` per sample, through `ApiClient`. A failure is logged and left. The next launch's 24-hour re-read sends it again. No queue.
- **Testing:** the conversions (fraction → %, voltages → 128 Hz µV, the HealthKit classification → its API string) are pure functions with tests in `EchoCareTests`. The HealthKit queries themselves are checked only on a device; the simulator has no ECG.

### API

**`POST /me/health-readings`** (04 §3, the senior's phone app → FastAPI). Senior role. Body:

| Field | |
|---|---|
| `id` | UUID, the HealthKit sample's `uuid`. A re-send by the same senior is a duplicate |
| `kind` | `spo2` or `ecg` |
| `measured_at` | with an offset; a naive time is 422 |
| `spo2` | 50 to 100, a whole percentage. Required for `spo2`, refused for `ecg` |
| `ecg_classification` | `sinus_rhythm`, `atrial_fibrillation`, `inconclusive_low_heart_rate`, `inconclusive_high_heart_rate`, `inconclusive_poor_reading`, `inconclusive_other`, `unrecognized`. Required for `ecg` |
| `ecg_heart_rate` | 0 to 300, optional |
| `ecg_trace` | list of ints (µV, -10,000 to 10,000), at most 1,280. Optional |
| `ecg_trace_hz` | 128; required with `ecg_trace` (an int 1 to 512, so the phone can change it later) |

Answers 204, a duplicate included. A `measured_at` in the future is stored as the arrival time, as a check-in is. A reading measured more than 24 hours ago is answered 204 and not stored, since the sweep would delete it anyway. HealthKit's `notSet` classification maps to `unrecognized` on the phone. A field that doesn't belong to the `kind`, or a missing required one: 422.

**`GET /seniors/{id}/watch/health`** (04 §1). Same scoping as `GET /seniors/{id}/watch`: `reach_senior`, then content only for whoever `sees_watch`. Answers 204 when the caller doesn't see the watch or there are no readings. Otherwise:

```json
{
  "spo2": { "value": 97, "measured_at": "…" },
  "spo2_readings": [ { "at": "…", "value": 96 } ],
  "ecg": {
    "classification": "sinus_rhythm",
    "heart_rate": 72,
    "measured_at": "…",
    "trace": [12, 15, …],
    "trace_hz": 128
  }
}
```

`spo2` is the latest reading, or null. `spo2_readings` holds every reading of the last 24 hours, oldest first, unbucketed: there are only a handful. `ecg` is the latest recording, or null. Older ECGs are kept for the export but not served here.

It's a separate endpoint rather than new fields on `GET /seniors/{id}/watch`. That keeps a trace of up to 1,280 points out of the check-in read and its export copy, keeps `WatchView` exactly as Android and iOS parse it, and lets the readings have their own 204.

### Backend

In `backend/app/seniors/`:

- **`models.py`:** `HealthReading`, table `health_readings`: primary key (`senior_id`, `id`), with `senior_id` an FK to the senior and `id` the HealthKit UUID (builder check, Claude's call: one demo iPhone moved between seeded seniors re-sends the same samples, and each senior must get their own copy), `kind` (enum `spo2`, `ecg`), `measured_at`, `received_at`, `spo2` (int, null), `ecg_classification` (enum, null), `ecg_heart_rate` (int, null), `ecg_trace` (JSONB, null), `ecg_trace_hz` (int, null). Index on (`senior_id`, `measured_at`). One additive migration.
- **`schemas.py`:** `HealthReadingForm` with the per-kind validation; `WatchHealthView`, `Spo2View`, `EcgView`. Naming per backend/AGENTS.md.
- **`service.py`:** `record_health_reading` (insert, `ON CONFLICT (senior_id, id) DO NOTHING`), `watch_health` (the read above), `prune_health_readings` (24 h, `READINGS_KEPT`). The scheduler calls the prune beside `prune_watch_readings`. `erase_senior_children` adds `HealthReading`.
- **`router.py`:** the two endpoints.
- **`export/`:** `ExportWatch` gains `health_readings`, every stored row in time order, the trace included.
- **Tests:** validation per kind, duplicate, the 24-hour cut-off and future clamp, scoping (DAS sees it, an unrelated caregiver gets 204), the prune, export and erasure.

### Dashboard

- **`services/api.ts`:** `WatchHealthView` and `fetchWatchHealth(id, signal)`, null on 204.
- **`WatchHealth.svelte`:** a third `poll` (30 s). Two more parts of the card, each shown only when it has data:

```
┌ Ceas ─────────── Purtat ─────────── Ultimul semnal acum 1 min ┐
│ Puls 74 bpm   Puls în repaus 61 bpm   Baterie 82%             │
│ Pași azi 1204   Fără pași de 3 min    SpO2 97% · acum 3 min   │
│ ─ SpO2, ultimele 24 h ─────────────────────────────────────── │
│   •    •  •        •           •   •      min 94 · max 98 %   │
│ ─ ECG · acum 5 min ────────────────────────────────────────── │
│ Apple: Ritm sinusal · 72 bpm                                  │
│ ╱╲_╱╲__╱╲_╱╲__╱╲_╱╲__╱╲_╱╲__   primele 10 s                   │
└───────────────────────────────────────────────────────────────┘
```

  - SpO2 joins the stat grid as „SpO2” with its value and age (`since`).
  - The 24-hour SpO2 line reuses the `pulseGraph` look, drawn with `sparkline`. Its gap rule (35 min) breaks a line of sparse readings into dots, which is the honest look for spot readings.
  - The ECG block draws the trace with `sparkline`: point `i` at `i * 1000 / trace_hz` ms, across 0 to 10 s. The label reads „Apple: <verdict>”. The verdicts in Romanian: `sinus_rhythm` „Ritm sinusal”, `atrial_fibrillation` „Fibrilație atrială”, `inconclusive_low_heart_rate` „Neconcludent: puls scăzut”, `inconclusive_high_heart_rate` „Neconcludent: puls ridicat”, `inconclusive_poor_reading` „Neconcludent: citire slabă”, `inconclusive_other` „Neconcludent”, `unrecognized` „Neclasificat”; an unknown string shows as it is, like `STATES`.
  - **When the card shows doesn't change** (builder check, Claude's call). `SeniorDetails.svelte:423` shows `WatchHealth` only for a senior with a watch (or equipment not stated) and no „Ceas înregistrat, nu a trimis date” warning, which means after the watch app's first check-in. The Health parts live inside that card. For the demo, the senior starts monitoring once: that tap both grants Health access and makes the first check-in, so the card and its Health data appear together. Inside the card, the Health parts render from their own read, independent of the check-in's `state`, and the 204 branch of `fetchWatch` („Ceasul nu a trimis încă date.”) is left as it is.
  - No colour for a low SpO2 or an AFib verdict (anti-goal: no alert).

### Docs

- `04-interfaces.md`: §1 the `GET`, §3 the `POST`.
- `05-data-model.md`: `HEALTH_READING` in the diagram and table list, §4 retention (24 hours, like `watch_readings`), §5 erasure.
- **ADR-008 (proposed):** the iPhone reads blood oxygen and ECG from Apple Health; Android doesn't supply them; 24-hour retention; shown, not acted on. It amends ADR-006's "Not done".

### Delivery order

Built on a branch, with ADR-008 in it as **Proposed**. Nothing is merged to `main` until the team agrees to ADR-008 and Alex asks for the merge: the migration freezes and deploys to staging on merge (backend/AGENTS.md), so it can't be taken back afterwards.

## Left to the builder

- Whether `scripts/seed.py` adds mock Health readings for the local dashboard (a few SpO2 points and one ECG with a synthetic trace would let the card be checked without a device).

- Names inside the Swift file and the Svelte markup, and whether `HealthSync` is an actor or a main-actor class (follow `Relay`).
- Exact Pydantic bounds beyond the ones above, and the migration's revision name.
- How the senior's home triggers `HealthSync` (an `.task` on the view, like the location prompt, is the expected fit).
- Whether `spo2_readings` needs a cap; at a few dozen a day it doesn't, but a defensive `LIMIT 500` is fine.

## Noticed, not in scope

Commit `2f4b60e` added the `health-records` (clinical records) entitlement, which `ios/AGENTS.md` warns about, and `DEVELOPMENT_TEAM` to `project.pbxproj`, which the same file forbids. This design needs neither. Fixing them is separate.

## Unverified

- How long a reading takes to sync from the watch to the iPhone's Health store. It decides whether "live on stage" means seconds or a minute.
- Background blood-oxygen readings: how often Apple takes them varies by watch and wearer. The on-demand reading is the dependable demo path.
