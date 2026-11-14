# AGENTS.md: ios

One Xcode project, two apps: the iPhone and iPad app for the senior, caregiver, medic and DAS roles, and the watchOS app for the senior's watch, embedded in it. Swift 6, SwiftUI, Xcode 27.2, deployment targets iOS 26.0 and watchOS 26.0. Setup, devices and troubleshooting: [README.md](README.md).

**`ios/` is demo-only** ([ADR-007](../docs/adr/ADR-007-ios-demo-clients.md)). It ports `android/` for a demo on Apple devices, signed with a free Personal Team: no App Store, no TestFlight, no CI, no push. The Android source is the behavioural spec: each Swift screen ports the Kotlin file of the same name, with the same spec IDs in comments and the same Romanian copy. Never change `android/`, `backend/` or an API contract to make iOS easier.

## Layout

| Target or package | What | Bundle ID |
|---|---|---|
| `EchoCare` | iPhone and iPad app (`TARGETED_DEVICE_FAMILY = 1,2`), links `Shared` and `FirebaseAuth` | `$(BUNDLE_ID)`, `ro.echocare.ios` |
| `EchoCareWatch` | watchOS app, embedded in `EchoCare.app/Watch`, links `Shared`. Never calls FastAPI (G5) | `$(BUNDLE_ID).watchkitapp` |
| `EchoCareTests` | Unit tests (Swift Testing), hosted by the app | `$(BUNDLE_ID).tests` |
| `Shared/` | Local Swift package: the watch's detectors and the watch-phone messages, ported from `android/shared` | |

```
ios/
├── EchoCare.xcodeproj           written by hand; folder-synchronized groups, shared schemes, Package.resolved
├── Config/                      outside the synchronized folders, so nothing here is copied into a bundle
│   ├── Base.xcconfig            every target's settings: BUNDLE_ID, deployment targets, API_URL, REREAD_SECONDS, REAL_SMS, DEMO
│   ├── Local.xcconfig.example   what to copy
│   ├── Local.xcconfig           git-ignored: DEVELOPMENT_TEAM, optional overrides
│   ├── EchoCare-Info.plist      keys merged into the generated Info.plist (EchoCare…, URL scheme, fonts)
│   ├── EchoCareWatch-Info.plist WKApplication, WKBackgroundModes = workout-processing
│   └── *.entitlements           com.apple.developer.healthkit only
├── EchoCare/                    app sources and resources: App/, UI/, Localizable.xcstrings, GoogleService-Info.plist
├── EchoCareWatch/               watch sources
├── EchoCareTests/               app tests
└── Shared/                      Package.swift, Sources/Shared, Tests/SharedTests
```

Files dropped into `EchoCare/`, `EchoCareWatch/` or `EchoCareTests/` join their target with no project edit. An `Info.plist` placed there is also copied as a resource and fails the build ("Multiple commands produce"); Info.plist keys go in `Config/*-Info.plist`, or in `INFOPLIST_KEY_*` build settings when one exists.

## Commands

From the repository root. The simulator commands need the iOS 27.2 and watchOS 27.2 simulator runtimes (`xcodebuild -downloadPlatform iOS`).

| Task | Command |
|---|---|
| App tests on the simulator | `xcodebuild test -project ios/EchoCare.xcodeproj -scheme EchoCare -destination 'platform=iOS Simulator,name=iPhone 17'` |
| Build the watch app | `xcodebuild build -project ios/EchoCare.xcodeproj -scheme EchoCareWatch -destination 'generic/platform=watchOS Simulator'` |
| Test the shared logic (also the pre-commit hook) | `swift test --package-path ios/Shared` |
| List devices and their UDIDs | `xcrun devicectl list devices` |
| Build for the iPhone, signing on the fly | `xcodebuild build -project ios/EchoCare.xcodeproj -scheme EchoCare -configuration Debug -destination 'id=<iphone-udid>' -allowProvisioningUpdates -allowProvisioningDeviceRegistration -derivedDataPath ios/build` |
| Install the app on the iPhone | `xcrun devicectl device install app --device <iphone-udid> ios/build/Build/Products/Debug-iphoneos/EchoCare.app` |
| Install the watch app on the watch | `xcrun devicectl device install app --device <watch-udid> ios/build/Build/Products/Debug-watchos/EchoCareWatch.app` |
| Pull a file out of an app's container | `xcrun devicectl device copy from --device <udid> --domain-type appDataContainer --domain-identifier ro.echocare.ios --source Documents/<file> --destination <file>` |

If `name=iPhone 17` matches more than one simulator, use `id=<udid>` from `xcrun simctl list devices`. `ios/build/` is git-ignored; the watch app is built and signed with the iPhone build.

## Rules

- **Nothing team- or person-specific is committed.** `DEVELOPMENT_TEAM` lives only in the git-ignored `Config/Local.xcconfig`; never write it into `project.pbxproj` (a target-level setting would also override the xcconfig). Don't print its value in logs, commits or reports.
- **Settings go in `Base.xcconfig`,** target-specific ones in the target's build settings. `Local.xcconfig` is included last and overrides either file's values only where the target doesn't set them itself. In an xcconfig, `//` starts a comment: write URLs as `https:/$()/…`.
- **Android's `BuildConfig` maps onto build settings:** `API_URL`, `REREAD_SECONDS`, `REAL_SMS` reach the app as the Info.plist keys `EchoCareAPIURL`, `EchoCareRereadSeconds`, `EchoCareRealSMS`, read by `AppConfig`. Debug builds define the Swift flag `DEMO` (Wear OS `BuildConfig.DEMO`: demo timings); Release doesn't.
- **User-facing text is Romanian and lives in `Localizable.xcstrings`,** keyed by the Android `strings.xml` name (`Text("sign_in_title")`). Format arguments are Apple's (`%1$@`, `%1$lld`). The watch is a separate bundle and gets its own catalog. Code, comments and docs stay in English.
- **The look is `Theme`** (`UI/Theme.swift`): the Android palette and type scale, one dark theme, Archivo and JetBrains Mono bundled from `android/app/src/main/res/font`. Use `.textStyle(Theme.bodyLarge)` rather than system fonts.
- **Swift 6 language mode** with strict concurrency; types are not `@MainActor` by default.
- **Entitlements stay minimal:** `com.apple.developer.healthkit` only. A free Personal Team can't sign push, iCloud, App Groups or Sign in with Apple, and Xcode expands an empty `healthkit.access` into clinical records.
- **Dependencies are Swift packages,** added to `project.pbxproj` with `Package.resolved` committed. FirebaseAuth is the only remote one and only the app links it.
- **Contract changes move together:** an endpoint change updates `04-interfaces.md`, the backend, `android/app/.../Api.kt`, `dashboard/src/` and `ios/EchoCare/Api/Api.swift`.
- **The simulator proves little about the watch.** HealthKit workouts, sensors and WatchConnectivity only show on real devices (design, Spike results); say so when a change can't be checked in the simulator.
