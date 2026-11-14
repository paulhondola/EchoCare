# Spike results

Part of the [Sentinela specification](README.md). What the spikes in [06-operations.md](06-operations.md) section 6 found on real hardware, with the raw numbers. The spec's proposals are updated from these; this file keeps the evidence.

## S13 · Fall detection on the watch, screen on

**Date:** 2026-10-14 · **Device:** Galaxy Watch5 44 mm (SM-R910), One UI 8 Watch (Wear OS 6, API 36) · **App:** the sensor test screen on branch `wear/sensor-test` · **Wearer:** one team member, watch on the left wrist

### What the watch delivers

| Sensor | Result |
|---|---|
| Accelerometer (LSM6DSV) | 50 readings a second at the requested 20 ms period. It reports a range of 8 g, yet delivered peaks up to 12.5 g |
| Heart rate (Samsung HR, non-wake-up) | One value a second while the screen is open. 0 while acquiring, for a few seconds after start. „No contact” as soon as the watch leaves the wrist |
| Step counter | Counts correctly (20 steps walked, 19 to 23 counted) |
| Permissions | `android.permission.health.READ_HEART_RATE` for the pulse (not `BODY_SENSORS`, on Wear OS 6) and `ACTIVITY_RECOGNITION` for steps |
| Screen off or app in the background | The system cuts the app's sensor access („has sensor access: false”). Background delivery is spike S5, not measured yet |

### Method

Five trials of each movement, one movement per trial. Falls onto a bed, then 15 seconds still. Per trial the app logs (logcat tag `SentinelaTrial`):

- **max**: the highest total acceleration, in g;
- **free fall**: the longest stretch below 0.4 g, in ms;
- **still after**: the longest stretch within 0.1 g of 1 g after the highest peak above 1.5 g, in s. It ends when the trial is closed, so short trials understate it.

### Results

| Trials | Movement | Max (g) | Free fall (ms) | Still after (s) |
|---|---|---|---|---|
| 1–5 | Fall forward, onto knees and hands | 9.95 · 12.15 · 5.91 · 10.15 · 11.21 | 160 · 40 · 0 · 20 · 80 | 9.8 · 7.6 · 11.2 · 11.2 · 11.2 |
| 6–10 | Fall to the side | 4.69 · 5.17 · 2.93 · 5.36 · 2.78 | 120 · 100 · 60 · 60 · 20 | 12.1 · 15.5 · 15.5 · 15.6 · 15.0 |
| 11–15 | Fall backwards | 4.03 · 2.04 · 2.85 · 3.22 · 2.50 | 20 · 0 · 0 · 0 · 20 | 14.5 · 15.5 · 14.2 · 11.6 · 8.9 |
| 16–20 | Sitting down hard on a chair | 2.74 · 3.48 · 2.61 · 2.35 · 2.09 | 0 · 160 · 0 · 40 · 0 | 8.1 · 10.6 · 11.6 · 13.9 · 0.3 |
| 21–25 | Lying down quickly on the bed | 2.09 · 1.95 · 1.81 · 3.02 · 4.00 | 0 · 0 · 0 · 0 · 40 | 6.0 · 8.3 · 10.2 · 8.2 · 15.4 |
| 26–30 | Walking 20 steps | 1.80 · 2.14 · 1.82 · 2.37 · 2.28 | 0 · 0 · 0 · 0 · 0 | 0.9 · 2.4 · 2.1 · 2.4 · 3.5 |
| 31–35 | Stairs up and down | 3.92 · 3.44 · 3.19 · 2.48 · 3.30 | 140 · 120 · 0 · 100 · 80 | 0.7 · 0.3 · 1.5 · 1.6 · 3.0 |
| 36–40 | Slapping a table | 11.46 · 9.72 · 8.85 · 9.70 · 11.81 | 140 · 100 · 40 · 80 · 20 | 0.9 · 0.2 · 0.2 · 0.2 · 0.7 |
| 41–45 | Sudden gestures: shaking the hand, raising the arm fast | 12.12 · 7.71 · 11.49 · 10.80 · 12.03 | 20 · 40 · 0 · 0 · 0 | 0.7 · 0.4 · 1.0 · 0.3 · 0.7 |

### Findings

- **The impact alone cannot tell a fall.** Slaps and gestures reach 8 to 12 g; falls backwards onto a bed reach 2 to 4 g.
- **Free fall is unreliable at the wrist.** Falls backwards showed almost none (0 to 20 ms), while stairs and slaps reached 140 ms. It cannot be a required phase.
- **Stillness after the impact separates best.** Every fall stayed still at least 7.6 s; walking, stairs, slaps and gestures at most 3.5 s.

**Rule these numbers support:** a peak above 2 g, followed by at least 7 s within 0.1 g of 1 g. On these 45 trials it catches 15 of 15 falls and raises 6 false alarms out of 30, all from sitting down hard (4) and lying down quickly (2), which also end in stillness. None from walking, stairs, slaps or gestures. Those false alarms reach the wrist prompt only: a „Da” ends them, and no call is placed (UC-09).

### Check of the detector on the watch

The rule above, as `FallDetector` in `:shared`, run live in the sensor test screen. Same wearer, same day, a second set of trials.

| Trials | Movement | Detected |
|---|---|---|
| 1–5 | Fall onto the bed, then still | 4 of 5. Trial 5 peaked at 1.99 g, just under the 2 g threshold, and was still only 0.2 s after it. Trial 1 also counted a second detection while the watch was being set up |
| 6–10 | Slapping a table | 0 of 5 |
| 11–15 | Walking | 0. Trial 13 lasted 0 s, a double press of the button, so the numbering is off by one from here |
| 16–18 | Sitting down hard | 3 of 3, the known false alarm the wrist prompt is for |

The detector behaves as the 45 trials predicted. One fall fell just short of the impact threshold; one sample is not enough to lower it.

### Limits

- Falls were onto a bed. On a floor the impact is higher, so a 2 g threshold errs on the safe side.
- Five trials per movement, one wearer. Enough for a first rule; the course report needs 20 to 30 per movement (06 §5).
- Screen on only. Whether the accelerometer keeps 50 readings a second in the background is still open (S13, S5).

## S5 · Background monitoring — sensors with the screen off

**Date:** 2026-11-07 · **Device:** Galaxy Watch5 44 mm (SM-R910), One UI 8 Watch (Wear OS 6, API 36) · **App:** `MonitoringService` foreground service (health type, PARTIAL_WAKE_LOCK) on branch `wear/sensor-test` · **Wearer:** one team member, watch on the left wrist, screen off for the full session

### What the watch delivers

| Sensor | Result |
|---|---|
| Accelerometer | 2 997 – 2 999 readings per minute (ideal: 3 000). `maxGapMs` = 20 ms every minute — exactly the sampling period, **no reading lost** |
| Heart rate | 49 – 60 readings per minute (target: one per second). One low minute at start while acquiring; stable at ~60 afterwards |
| Step counter | Counted correctly on the minutes when the wearer moved |
| Battery drain | 9 % in 22 minutes (59 % → 50 %) = **~24 % per hour** |

### Method

`MonitoringService` started from the sensor test screen. Screen left off for 22 continuous minutes. Log extracted with `adb shell run-as bia.sentinela cat files/monitor.log`. Raw log (session 2):

```
19:49:47 started battery=59%
19:50:47 minute=1  accel=2997 maxGapMs=20 heartRates=49 lastHeartRate=90  steps=0  falls=0 battery=58%
19:51:47 minute=2  accel=2999 maxGapMs=20 heartRates=60 lastHeartRate=93  steps=0  falls=0 battery=58%
19:52:47 minute=3  accel=2999 maxGapMs=20 heartRates=60 lastHeartRate=88  steps=0  falls=0 battery=57%
19:53:47 minute=4  accel=2998 maxGapMs=20 heartRates=58 lastHeartRate=89  steps=0  falls=0 battery=57%
19:54:47 minute=5  accel=2999 maxGapMs=20 heartRates=60 lastHeartRate=88  steps=0  falls=0 battery=57%
19:55:47 minute=6  accel=2996 maxGapMs=20 heartRates=59 lastHeartRate=92  steps=0  falls=0 battery=56%
19:56:47 minute=7  accel=2997 maxGapMs=20 heartRates=59 lastHeartRate=79  steps=0  falls=0 battery=56%
19:57:47 minute=8  accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=93  steps=0  falls=0 battery=56%
19:58:47 minute=9  accel=2998 maxGapMs=20 heartRates=60 lastHeartRate=89  steps=0  falls=0 battery=55%
19:59:47 minute=10 accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=100 steps=0  falls=0 battery=55%
20:00:47 minute=11 accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=93  steps=0  falls=0 battery=55%
20:01:47 minute=12 accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=89  steps=0  falls=0 battery=54%
20:02:47 minute=13 accel=2998 maxGapMs=20 heartRates=59 lastHeartRate=100 steps=0  falls=0 battery=54%
20:03:47 minute=14 accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=112 steps=18 falls=0 battery=53%
20:04:47 minute=15 accel=2997 maxGapMs=20 heartRates=58 lastHeartRate=94  steps=0  falls=0 battery=53%
20:05:47 minute=16 accel=2998 maxGapMs=20 heartRates=60 lastHeartRate=106 steps=22 falls=0 battery=53%
20:06:47 minute=17 accel=2998 maxGapMs=20 heartRates=59 lastHeartRate=87  steps=0  falls=0 battery=52%
20:07:47 minute=18 accel=2999 maxGapMs=20 heartRates=60 lastHeartRate=89  steps=0  falls=0 battery=52%
20:08:47 minute=19 accel=2997 maxGapMs=20 heartRates=60 lastHeartRate=83  steps=0  falls=0 battery=51%
20:09:47 minute=20 accel=2998 maxGapMs=20 heartRates=60 lastHeartRate=89  steps=0  falls=0 battery=51%
20:10:47 minute=21 accel=2998 maxGapMs=20 heartRates=59 lastHeartRate=96  steps=0  falls=0 battery=51%
20:11:47 minute=22 accel=2998 maxGapMs=20 heartRates=60 lastHeartRate=86  steps=0  falls=0 battery=50%
```

### Findings

- **Background delivery works.** The PARTIAL_WAKE_LOCK keeps the CPU awake: `maxGapMs` never exceeds 20 ms, so no accelerometer reading is lost even with the screen off. The fall detector runs continuously without gaps.
- **Heart rate is reliable after the first minute.** One low minute (49 readings) while the sensor acquires; from minute 2 onward a steady ~60 readings per minute.
- **Battery cost is high.** ~24 %/hour under continuous monitoring. On a Galaxy Watch5 (276 mAh) a full charge lasts roughly 4 hours under this load. This rules out all-day background monitoring; the service suits a fixed monitoring window (e.g. night-time, 06 §6).

### Limits

- One wearer, one device, 22 minutes. Battery behaviour may differ on a charged battery and over longer sessions.
- ADB was connected over Wi-Fi during the test; Wi-Fi radio adds a small drain not present in normal use.
- The monitoring window length and any battery optimisation (reducing accelerometer rate outside fall-risk hours) are out of scope for this spike.

## S6 · Watch events reach FastAPI through the phone

**Date:** 2026-11-07 · **Watch:** Galaxy Watch5 44 mm (SM-R910), Wear OS 6 · **Phone:** Samsung S23 (`Daria S23`), Android 16 (SDK 36), paired through Galaxy Wearable · **App:** `wear/sensor-test` branch on both; FastAPI from `docker compose up db api`, reached from the phone at `http://192.168.3.109:8000` via `echocare.apiUrl` in `local.properties` · **Senior:** `+40700000005` (Maria Popescu), signed in on the phone

### What the pipeline delivers

| Step | Result |
|---|---|
| Check-in every minute | `Wearable MessageClient` → `WearListenerService` → `POST /api/me/check-ins` 204 → `watch_states` updated with the real battery and last pulse |
| Fall event after „Sunteți bine?" | On „Nu, ajutor!" or the 15 s timeout: `POST /api/me/events` 200 → `events` row, joined onto the senior's existing queued call per the UC-09 cooldown |
| Latency, button press to DB row | ~4 s end-to-end (watch → phone → API → commit) |
| First queued call for a fresh senior | `trigger=manual`, `state=queued`, `starting_severity=yellow` (UC-09 §2) |

### Method

`MonitoringService` on the watch sends the check-in in `logMinute()` and the fall event from `AreYouOkScreen` when the senior denies or lets the countdown run out. Both go over the Wearable Data Layer on the paths in `ro.echocare.shared.DataLayer`. The phone's `WearListenerService` (`@AndroidEntryPoint`) decodes the JSON payloads from `ro.echocare.shared.WearMessage` and forwards each one with Retrofit, authenticated by the signed-in senior's Firebase token.

Raw log (watch side, the fall event path):

```
21:24:27 started battery=26%
21:24:47 fall detected in minute=1 id=6569b60e-fdf8-4dfe-916d-025f5e573186
21:24:59 sending fall event id=6569b60e-fdf8-4dfe-916d-025f5e573186
21:25:01 fall event sent to Daria S23
21:25:27 minute=1 accel=2998 maxGapMs=20 heartRates=47 lastHeartRate=86 steps=0 falls=1 battery=26%
21:25:27 check-in sent to Daria S23
```

DB after a clean run (old queued call and its events deleted first):

```
events:  manual_request  received_at=2026-11-07 19:28:51.814+00
calls:   trigger=manual  state=queued  starting_severity=yellow  due_at=2026-11-07 19:28:51.815+00
```

### Findings

- **The Data Layer is reliable when the two apps match.** Same `applicationId` (`ro.echocare`), same signing keystore, same version in both APKs, and the phone paired through Galaxy Wearable: `connectedNodes` returned the phone, every send succeeded. A `connectedNodes` listener that silently drops the empty case explains the first „nothing arrived" pass — the `addOnFailureListener` and the per-node `addOnSuccessListener` now in `MonitoringService` and `AreYouOkScreen` make that visible.
- **Fall events send `type=fall` end to end.** The first pass hit a 422 because `EventForm.type` was `Literal[EventType.manual_request]`; the schema now accepts `Literal[manual_request, fall]`. The service layer treats both the same way for now (one queued yellow call per senior cooldown); differentiated intake belongs to the P19 work.
- **A foreground service cannot launch an activity on API 36.** The first version used an intent; the prompt never appeared. The fix is a `MutableStateFlow<FallPrompt?>` on `MonitoringService` that `MainActivity` collects — the activity shows the prompt the instant the service writes to the flow. The intent path remains unavailable; see the limits below for the screen-off case.
- **Event dedup through the existing queued call works.** A second „Nu" within cooldown attached its `manual_request` row to the same `call_id` as the earlier event, no second call queued (UC-09 §2).

### Limits

- One wearer, one phone, one session. The senior is the seeded Maria Popescu, so her enrollment state is `active` and the intake rules fire; a `draft` or `offline` senior would record the event and start no call.
- The local backend has no Twilio: the queued call stays queued and never rings, so the voice side of UC-09 is unverified locally. Staging has Twilio; the next pass should run the same test there with a number on `DIAL_ALLOWLIST`.
- The prompt relies on `MainActivity` being in the foreground. With the watch asleep (screen off, app in the background) the service writes to `fallPrompt` but nothing shows. A full-screen intent notification would cover that case; it is out of scope for S6.
