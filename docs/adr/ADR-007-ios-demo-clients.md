# ADR-007: Demo-only iOS and watchOS clients, signed from one Mac

**Status:** Accepted
**Date:** 2026-11-14
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Builds on:** [ADR-001](ADR-001-monorepo-and-delivery.md) (one native toolchain per folder), [01-architecture.md](../specs/echocare/01-architecture.md) (G5, the watch talks only to the phone)

## Context

The developers here use iPhones, Macs and Apple Watches. The only Android phone, tablet and Wear OS watch belong to a teammate who is not here, so nobody here can run or demo the senior's watch flow.

We tried installing on a real Apple Watch. A free Apple ID (an Xcode "Personal Team") installs on Alex's watch. Paul's watch never offered to trust the Mac, while Alex's did.

## Decision

1. **A second set of clients, for the demo only:** a SwiftUI iPhone and iPad app and a watchOS app in a new root folder `ios/`. They behave like `android/` (the four roles; the watch's anomaly detection) and talk to the same FastAPI backend. No API or schema change.
2. **One signer.** Every device is signed from Alex's Mac under Alex's Personal Team, with one bundle ID (`ro.echocare.ios`, the watch app `ro.echocare.ios.watchkitapp`) and so one Firebase iOS registration. A bundle ID registered by one team cannot be used by another.
3. **The watch never calls FastAPI** (G5). WatchConnectivity relays its events and check-ins through the phone (04 §3 messages), which is signed in as the senior.
4. **Monitoring runs inside an `HKWorkoutSession`.** watchOS suspends an app soon after the wrist drops; a running workout session keeps heart-rate and accelerometer samples coming.

The evidence is the 2026-11-14 spike: HealthKit works on a free team, heart rate arrives about every 5 s, the accelerometer runs at 50 Hz with the wrist down, `startWatchApp` starts the watch app from the phone, and `sendMessage` wakes a terminated iPhone app. The table is in the [design](../superpowers/specs/2026-11-14-ios-port-design.md#spike-results-2026-11-14).

## Consequences

- **No push.** APNs needs the paid Apple Developer Program. Screens re-read every 30 s while open, as Android does next to push.
- **About an hour of monitoring per workout session**, at a battery cost of roughly 10 to 15% an hour. Enough for a demo.
- **No Apple fall detection.** `CMFallDetectionManager` needs an entitlement Apple grants on request. The watch uses its own detectors, as Wear OS does.
- **Installs expire after 7 days.** Reinstall from Xcode. A free team allows at most 3 apps per device.
- **Real SMS sign-in uses the reCAPTCHA flow**, because Firebase cannot verify the app without APNs.
- **Contract changes now touch three clients:** `Api.kt`, `ios/EchoCare/Api/Api.swift` with `ApiClient.swift`, and `dashboard/src/`. Because the API only adds (ADR-001 §2.3), an old iOS install keeps working.
- **A permanently refused watch event is resent every minute**, as on Android. Noted, not changed.
- `android/` and `backend/` stay as they are. `ios/` has no CI and no TestFlight or App Store build.

## Alternatives considered

| Option | Why not |
|---|---|
| Kotlin Multiplatform, sharing `android/shared` and the API client | Xcode builds would depend on Gradle in another folder, against ADR-001. watchOS tooling adds friction |
| Compose Multiplatform for the iPhone screens | Android's plumbing (Hilt, Retrofit, Navigation, the Firebase Android SDK) does not run on iOS and is rewritten anyway. Hardest setup, non-native look |
| Wear OS emulators on the Macs | No real wrist, so no real pulse or fall |
| The paid Apple Developer Program | Would add push and TestFlight, and lift the 7-day limit. Not needed for the demo |
