# ADR-008: The iPhone sends blood oxygen and ECG from Apple Health

**Status:** Proposed
**Date:** 2026-11-14
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Amends:** [ADR-006](ADR-006-das-sees-watch-health.md) "Not done" (ECG and SpO2), [ADR-007](ADR-007-ios-demo-clients.md) (what the iOS app sends), [04-interfaces.md](../specs/echocare/04-interfaces.md) §1 and §3, [05-data-model.md](../specs/echocare/05-data-model.md) §4 and §5

This change waits for the team's agreement. It is built on a branch and not merged to `main` until the team accepts it: the migration freezes and deploys to staging on merge, so it can't be taken back.

## Context

The demo needs real health data from the senior's watch on the dispatcher's screen. Heart rate is there already (ADR-006). Blood oxygen (SpO2) and the ECG are not, and Android can't supply them: on Wear OS neither signal reaches a third-party app (ADR-006 "Not done").

An Apple Watch can: a blood-oxygen reading takes 15 s in the watch's Blood Oxygen app and an ECG 30 s in the ECG app, and Apple syncs both to the iPhone's Health store. A third-party iPhone app can read them, with the owner's permission, but can't start a measurement.

`ios/AGENTS.md` says not to change the backend or the API contract to make iOS easier. This isn't that: it adds data only Apple supplies, so it is a product decision, and this ADR asks the team for it.

## Decision

1. **The iPhone reads blood oxygen and ECG from Apple Health** and sends them to FastAPI, one reading per call, through `POST /me/health-readings` (04 §3, senior role): the last 24 hours on start and each new reading while the app runs. An ECG is sent as Apple's verdict, its average pulse and a shortened trace (the first seconds, at most 1,280 points). The watch app is untouched and the watch never calls FastAPI (G5).
2. **Readings are kept 24 hours** in `health_readings`, like `watch_readings` (05 §4), and the scheduler deletes older ones. Each keeps its own measurement time, and its HealthKit id makes a re-send a harmless duplicate.
3. **DAS and the others who see the watch read them** through `GET /seniors/{id}/watch/health` (04 §1), with the same scoping as `GET /seniors/{id}/watch`: the latest blood oxygen, the day's readings and the latest ECG, for the dashboard's watch card. The export and the erasure include them (05 §5).
4. **Shown, never acted on.** A reading raises no event, call, push or code. A low blood oxygen or an atrial fibrillation verdict is displayed as Apple's finding; EchoCare doesn't diagnose.
5. **Android is unchanged.** It sends nothing new and calls neither endpoint, and `GET /seniors/{id}/watch` keeps its shape.

## Consequences

- The shared contract carries data that only iOS supplies. Android and Wear OS never fill it, so a card shows blood oxygen and ECG only for a senior with an iPhone and an Apple Watch.
- Blood oxygen and ECG are health data, a special category (GDPR Art. 9). They are kept 24 hours, exported (Art. 15) and erased (Art. 17) with the senior, and shown only to whoever already sees the watch.
- A new table and endpoints only add (ADR-001 §2.3): old clients are not affected.
- On a free Personal Team, whether HealthKit delivers in the background is unverified (ADR-007), so readings flow only while the app runs. The demo doesn't need more.
- Old data does not accumulate: the day's readings are a few dozen rows per senior, and an ECG trace is bounded.

## Alternatives

- **Ride on the check-in.** The phone adds the latest blood oxygen and ECG to each watch check-in. Dropped: check-ins flow only while the watch workout runs, a reading from hours earlier would carry the check-in's time, and a 1,280-point trace would be copied into a `watch_readings` row every minute.
- **The watch reads Health and sends it over WatchConnectivity.** Dropped: it needs the workout running and a new watch-to-phone message, and the phone's Health store already holds the same data.

## Not done

- **Android and Wear OS.** No signal to send (ADR-006).
- **Starting a measurement.** Apps can only read what Apple measured.
- **The iPhone's own screens.** Only the dashboard shows the new data.
- **Breathing rate, heart rate variability, wrist temperature.** Left for later; `kind` has room.
- **The full 30 s, 512 Hz ECG.** Only the shortened trace is sent.
