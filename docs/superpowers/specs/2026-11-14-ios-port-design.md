# iOS and watchOS port, for the demo

Date: 2026-11-14. Status: approved. The work order's step 1 gate passed on Alex's iPhone and watch on 2026-11-14, except Firebase sign-in, which waits for the Firebase registration (Spike results).

## Intent

The developers on the team all use iPhones, Macs and Apple Watches. The only Android phone, tablet and Wear OS watch belong to a teammate who isn't here, so nobody here can run or demo the senior's watch flow. We tested deploying to a real Apple Watch: a free Apple ID (Xcode "Personal Team") installs fine on Alex's watch. Paul's watch never offers to trust the Mac, so the team settled on Alex's watch.

So we add a second set of clients: a SwiftUI iPhone app and a watchOS app in a new root folder `ios/`, with the same behaviour as `android/`, talking to the same FastAPI backend. Both client sets exist for the demo only, not as a product.

## The demo setup

| Device | Owner | Role in the demo |
|---|---|---|
| iPhone + Apple Watch | Alex | Senior: wears the watch; staging account on his real number, which Twilio rings |
| iPad | Alex | Medic registration: enrollment form and signature |
| iPhone | Paul | DAS, medic and caregiver, one account switching roles from the profile page; staging account on his real number |

Every device is signed from Alex's Mac under Alex's Personal Team and one bundle ID, so there is one Firebase iOS registration (whoever has console access adds it). Three of the four devices are Alex's and the implementation runs on his Mac; Paul's iPhone is connected to that Mac once to be registered and installed. (An earlier draft had Paul's Mac sign; changed 2026-11-14. `ro.echocare.ios` is now registered to Alex's team, so another team can't sign it.)

## Goals

- `ios/` builds with Xcode alone and installs on a real iPhone, iPad and Apple Watch with a free Personal Team.
- One universal app (iPhone and iPad) with the four roles and the same screens and rules as `android/app`: senior, caregiver, medic, DAS, role picker and profile page with the role switch.
- One watch app with the same behaviour as `android/wear`: pulse at rest, inactivity and fall detection, „Sunteți bine?” with Da/Nu and timeout, check-ins, events relayed through the phone with resend until acknowledged (UC-03, UC-09, UC-13, 04 §3).
- The demo flow works end to end: watch anomaly → phone → `POST /me/events` → call queued, visible to caregiver, medic and DAS.

## Non-goals

- Push notifications. APNs needs the paid Apple Developer Program. Screens stay current by re-reading on a timer while open, which Android already does next to push (`Frame.kt`, `REREAD_SECONDS`).
- Monitoring longer than about an hour. The watch monitors while a workout session runs; the demo needs minutes.
- Apple's built-in fall detection (`CMFallDetectionManager`): it needs an entitlement Apple grants on request, which a free team can't get.
- App Store or TestFlight distribution, CI on macOS runners, shared code with Android.
- Any API or schema change. iOS calls the existing endpoints exactly as Android does.

## Anti-goals

- Changing `android/` or the backend to make iOS easier. The Android build stays as it is.
- The watch talking to FastAPI directly. G5 stays: the watch has no identity, the phone relays everything.
- A port that only works on one developer's Mac because of hard-coded team IDs or bundle IDs.

## Constraints

- **Free Personal Team:** installs expire after 7 days (reinstall from Xcode); at most 3 free-signed apps per device; no push, iCloud, App Groups or Sign in with Apple. A bundle ID registered by one team can't be used by another, so the demo build has one signer (The demo setup).
- **HealthKit works on a free team** (confirmed, Spike results). The watch needs it for live heart rate and the workout session.
- **watchOS suspends apps** soon after the wrist drops. Only a running `HKWorkoutSession` keeps the app alive with heart-rate samples and CoreMotion accelerometer data. It costs roughly 10–15% battery an hour and counts toward the Activity rings; fine for a demo.
- **Firebase:** Paul registers the iOS app (bundle ID from `Base.xcconfig`) in the same Firebase project as Android, which gives a `GoogleService-Info.plist`, committed. The demo signs in with **real numbers and real SMS**. Without APNs, Firebase verifies the app with a reCAPTCHA page, which needs the Encoded App ID as a URL scheme. Firebase test numbers (`isAppVerificationDisabledForTesting`) stay available for development, like Android's debug default.
- **Versions:** Xcode 27.2; deployment targets iOS 26 and watchOS 26 (Paul's iPhone runs 27.2, Alex's 27.0.1).
- **User-facing text is Romanian**, as on Android; code, comments and docs in English (AGENTS.md).
- **ADR-001:** one native toolchain per folder, no build orchestrator. `ios/` uses Xcode and Swift Package Manager only.

## Approaches considered

| | Approach | Trade-off |
|---|---|---|
| **A (chosen)** | Plain Swift port: SwiftUI iPhone app, SwiftUI watch app, small local Swift package for the detectors and message types | Retypes ~9,700 lines, but SwiftUI maps closely onto Compose; Xcode only; nothing touches `android/` |
| B | Kotlin Multiplatform: compile `android/shared`, the API client and view models for Swift; SwiftUI screens only | Saves some typing; Xcode builds would depend on Gradle in another folder (against ADR-001), and watchOS KMP tooling adds friction |
| C | Compose Multiplatform for the iPhone screens, SwiftUI watch | Android's plumbing (Hilt, Retrofit, Navigation, Firebase Android SDK) doesn't run on iOS, so it's rewritten anyway; non-native look; hardest setup |

Paul picked A: both client sets are demo-only, so sharing code between them buys nothing.

## Design

### Layout

```
ios/
├── EchoCare.xcodeproj           checked in; folder-synchronized groups keep it small
├── Config/
│   ├── Base.xcconfig            checked in: shared settings, includes Local.xcconfig
│   ├── Local.xcconfig.example   checked in: what to copy
│   └── Local.xcconfig           git-ignored: DEVELOPMENT_TEAM, optional BUNDLE_ID and API_URL
├── EchoCare/                    iPhone app target
│   ├── App/                     entry point, role routing (Screen as on Android)
│   ├── Api/                     URLSession client and Codable types, one per Api.kt type
│   ├── Auth/                    Firebase phone sign-in, landing, role picker
│   ├── Home/                    senior, caregiver, medic screens, profile
│   ├── Enroll/                  enrollment form, signature pad, refusal
│   ├── Das/                     incidents, incident, resolve
│   ├── Watch/                   WatchConnectivity relay, starts the watch workout
│   ├── UI/                      theme, palette, shared components
│   ├── Localizable.xcstrings    Romanian strings, keyed like strings.xml
│   └── GoogleService-Info.plist public config, committed like the Firebase web config
├── EchoCareWatch/               watchOS app target
│   ├── Monitoring/              workout session, sensors, detectors, event queue
│   └── Screens/                 home, „Sunteți bine?”
├── Shared/                      local Swift package, used by both targets
│   ├── Sources/Shared/          RestingBaseline, PulseAnomaly, InactivityDetector, FallDetector, WatchMessage
│   └── Tests/SharedTests/       ported from android/shared/src/test
├── AGENTS.md
└── README.md
```

`Local.xcconfig` plays the part of `android/local.properties`: the signer sets their team, and optionally the API address (default staging, `http://<mac-ip>:8000` for the local stack). Another developer who wants to run on their own device overrides the bundle ID there too, and then needs their own Firebase registration and plist (a git-ignored path set in the same file).

### iPhone app

- **Mirrors `android/app` screen for screen.** Each Kotlin screen or view model has one Swift counterpart with the same name where it makes sense (`SeniorScreen.swift`, `IncidentScreen.swift`, …), and the same spec IDs in comments. The builder ports from the Android source; that source is the specification for behaviour and copy.
- **Role routing** ports `auth/Screen.kt` as a Swift enum: `screenFor(me:saved:)`, `rolesOf`, the saved role in `UserDefaults`.
- **API client:** one `Api.swift` with `Codable` types matching `Api.kt` field for field, snake_case keys, lenient decoding of unknown values (as `app/AGENTS.md` asks), Firebase ID token as `Bearer`, refreshed on 401 once.
- **Refresh:** each screen re-reads when it appears and every `REREAD_SECONDS` while visible (30 by default, as release Android). No push.
- **Location:** with a watch event, the relay attaches the last known location from CoreLocation, as `WearListenerService` does with `lastKnownLocation`.
- **Signature pad:** SwiftUI `Canvas` with a drag gesture, strokes sent in the same format as `SignaturePad.kt`.
- **iPad:** the same app; the medic screens follow the Android tablet layout (`2026-11-04-medic-tablet-panel-design.md`, `MedicHome.kt`) where the width allows. Other roles may simply stretch.

### Watch app

- **Monitoring runs inside an `HKWorkoutSession`** (activity type `.other`, indoor). It starts two ways: from the senior's phone app (`HKHealthStore.startWatchApp(with:)`, „Pornește monitorizarea” on the senior screen), or from a start button on the watch. It stops on the watch, or when the session ends.
- **Sensors:** live heart rate from the session's `HKLiveWorkoutBuilder`; accelerometer from `CMMotionManager` at the rate Android uses; steps from `CMPedometer`; worn state from the workout's wrist detection, or treated as worn while the session runs if no signal is available.
- **Rules:** the four detectors from `Shared`, with the same thresholds and the same demo shortcuts as `BuildConfig.DEMO` on Wear OS (15 s pulse hold, 60 s inactivity, 15 s prompt timeout, check-in every minute). Debug builds are demo builds; Release uses the production values.
- **„Sunteți bine?”:** haptic, repeated every 3 s while it shows, plus full-screen prompt with Da/Nu, timeout as on Wear OS; a fall also plays a sound, a second after the first haptic.
- **Watch ↔ phone:** WatchConnectivity carries the same three messages as the Data Layer (04 §3): event and check-in watch → phone, received phone → watch. An event goes with `sendMessage` when the phone is reachable, which wakes the iPhone app in the background; otherwise with `transferUserInfo`, which queues it. The watch keeps each event in its queue until the phone acknowledges its id, as `EventQueue.kt` does. Check-ins go the same way as events (as Wear OS does), without the queue: a newer check-in replaces an older one still waiting.
- **Phone side of the relay:** posts to `POST /me/events` (`source: "watch"`) and `POST /me/check-ins` exactly as `WearListenerService` does, and acknowledges an event only after FastAPI accepted it.

### Docs and repository

- **ADR-007** records the iOS demo clients: why, the free-team limits, the workout-session constraint, no push.
- `01-architecture.md`: add the iOS and watchOS apps next to the Android rows (components, channel 1 over WatchConnectivity, deployment "installed from Xcode").
- Root `AGENTS.md`: `ios/` row in the layout table; the contract-change rule names `ios/EchoCare/Api/Api.swift` alongside `Api.kt` and `dashboard/src/`.
- `ios/AGENTS.md` and `ios/README.md`: setup (Xcode version, `Local.xcconfig`, trusting the developer profile on the iPhone, Developer Mode on iPhone and watch, home Wi-Fi rather than a hotspot), build and test commands, the 7-day reinstall.
- `.gitignore`: `ios/Config/Local.xcconfig`, `ios/build/`, `xcuserdata/`.
- `lefthook.yml`: `swift test` for the `Shared` package on commits that touch `ios/Shared/`. No CI workflow.

## Work order

1. **Prove the risky parts on Alex's devices first,** with a throwaway build: HealthKit authorization and a workout session under a free team, live heart rate, accelerometer while the wrist is down, `sendMessage` waking the iPhone app, and Firebase sign-in with a real number through the reCAPTCHA flow. If HealthKit or sign-in is refused on a free team, stop and come back: the fallback is the $99 account or the Wear OS emulators. Done except sign-in (Spike results); sign-in is checked before step 3's sign-in work.
2. `Shared` package and its tests.
3. Xcode project, config, API client, sign-in and role routing.
4. Senior role and the watch app: the demo's core path.
5. Caregiver, medic (enrollment, signature, medical section, tasks home), DAS (incidents, resolve), profile.
6. Docs and repository changes above.

## Left to the builder

- SwiftUI structure inside each screen, view model style (`@Observable`), navigation (`NavigationStack`).
- Exact mapping of each Compose component to SwiftUI, and the theme values from `ui/theme/`.
- How the watch stores its event queue (a JSON file is enough).
- ~~Whether `startWatchApp` or the watch button is the main path in the demo~~: decided by the spike. `startWatchApp` is the main path, the watch button the fallback.

## Spike results (2026-11-14)

A throwaway two-target project (iPhone app with the watch app embedded, bundle IDs `ro.echocare.ios` and `.watchkitapp`), signed with Alex's Personal Team, on Alex's iPhone 17 Pro (iOS 27.0.1) and Apple Watch Series 10 (watchOS 27.0), installed with `xcodebuild -allowProvisioningUpdates` and `xcrun devicectl device install app`.

| Check | Result |
|---|---|
| Install with a free team, HealthKit capability | Pass. Both signed apps carry `com.apple.developer.healthkit`; no Personal Team error |
| HealthKit authorization on phone and watch | Pass |
| `HKWorkoutSession` (`.other`, indoor) with `HKLiveWorkoutBuilder` | Pass. Heart rate every 4.4–5.6 s |
| Wrist down, screen off | Pass. About 90 s inactive: heart rate every ~5 s and `CMMotionManager` at a steady 50 Hz throughout |
| `startWatchApp(with:)` from the iPhone, watch app closed | Pass, twice. The watch's `handle(_ workoutConfiguration:)` runs and the session starts within ~0.3 s. Error 550 only when the watch app isn't installed yet |
| `sendMessage` from the watch, iPhone app terminated | Pass. iOS relaunched the app in the background (`applicationState` 2), and the reply reached the watch 190 ms after sending |
| Firebase sign-in with a real number | Not run: no iOS app registered in Firebase yet, so no `GoogleService-Info.plist` |

For the builder: the app is relaunched by WatchConnectivity before any UI, so `WCSession` has to be activated in `application(_:didFinishLaunchingWithOptions:)`, not in a view. On the demo phone, don't swipe the app away in the app switcher: iOS may not relaunch an app the user force-quit.
