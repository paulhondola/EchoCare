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
