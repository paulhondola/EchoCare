# ios: the iPhone and watch apps, for the demo

One Xcode project that produces two apps: the iPhone and iPad app for the senior, caregiver, medic and DAS roles (spec G3, G15), and the watchOS app for the senior's watch (G5), embedded in it. Swift 6, SwiftUI, Xcode 27.2. It is a port of [android/](../android/) for a demo on Apple devices, signed with a free Personal Team and installed from a Mac, never through the App Store or TestFlight ([ADR-007](../docs/adr/ADR-007-ios-demo-clients.md)). Agents: [AGENTS.md](AGENTS.md).

This is the skeleton: the app configures Firebase and shows a placeholder, and the watch app shows one screen. The screens arrive task by task in the [iOS port plan](../docs/superpowers/plans/2026-11-14-ios-port.md); see [What is not built yet](#what-is-not-built-yet).

| Part | What | Becomes |
|---|---|---|
| [EchoCare/](EchoCare/) | iPhone and iPad app, bundle ID `ro.echocare.ios` | Phone sign-in, then the screens of the granted role, as on Android. Relays the watch to FastAPI |
| [EchoCareWatch/](EchoCareWatch/) | watchOS app, `ro.echocare.ios.watchkitapp` | A workout session with pulse, motion and steps, „Sunteți bine?”, check-ins (UC-09, UC-13) |
| [Shared/](Shared/) | Local Swift package | The watch's detectors and the watch-phone messages, ported from `android/shared`, tested on the Mac |
| [Config/](Config/) | xcconfig, Info.plist fragments, entitlements | |

## Tools

| Tool | Needed for | Install |
|---|---|---|
| Xcode 27.2 | Everything: building, signing, simulators, `xcrun devicectl` | Mac App Store, then open it once to install its components |
| iOS 27.2 and watchOS 27.2 simulator runtimes | Simulator tests and builds | `xcodebuild -downloadPlatform iOS`, `xcodebuild -downloadPlatform watchOS` |
| An Apple Account signed in to Xcode | Signing with a free Personal Team | Xcode → Settings → Apple Accounts |
| Docker Desktop | The local API, from the repository root | See the [root README](../README.md) |

Swift packages (Firebase, `Shared`) resolve on the first build; versions are pinned in `EchoCare.xcodeproj/project.xcworkspace/xcshareddata/swiftpm/Package.resolved`.

## Set up once

**1. Create `Config/Local.xcconfig`.** It plays the part of `android/local.properties` and is git-ignored:

```bash
cp ios/Config/Local.xcconfig.example ios/Config/Local.xcconfig
```

| Key | What it does |
|---|---|
| `DEVELOPMENT_TEAM` | Required on a device. Your team ID, from Xcode → Settings → Apple Accounts. Automatic signing does the rest |
| `BUNDLE_ID` | Optional. A bundle ID belongs to the team that registered it first, so `ro.echocare.ios` only signs with the demo signer's team. Anyone else picks their own; Firebase sign-in then needs an iOS app registered for it and its own `GoogleService-Info.plist` |
| `API_URL` | Optional, default staging. `http:/$()/localhost:8000` is the laptop's Compose stack from the simulator; from a device, use the Mac's Wi-Fi address. iOS asks once for local-network access |
| `REREAD_SECONDS` | Optional, default 30. How often an open screen re-reads; iOS has no push |
| `REAL_SMS` | Optional, default `NO`: sign in with Firebase's test numbers. `YES` signs in with real numbers and real SMS, through Firebase's reCAPTCHA page |

**2. Open `ios/EchoCare.xcodeproj` in Xcode** (not the repository root). The `EchoCare` and `EchoCareWatch` schemes are shared and ready.

## Run it

### On the simulator

From the repository root:

```bash
xcodebuild test -project ios/EchoCare.xcodeproj -scheme EchoCare -destination 'platform=iOS Simulator,name=iPhone 17'
```

```bash
xcodebuild build -project ios/EchoCare.xcodeproj -scheme EchoCareWatch -destination 'generic/platform=watchOS Simulator'
```

Or choose the `EchoCare` scheme and an iPhone simulator in Xcode and press Run. The simulator is fine for screens and the API; the watch's sensors, workout session and WatchConnectivity only work on real devices.

### On the iPhone and watch

**Prepare the devices once:**

1. Connect the iPhone to the Mac with a cable and trust the Mac. The watch is paired with that iPhone.
2. Turn on **Developer Mode** on the iPhone (Settings → Privacy & Security → Developer Mode) and on the watch (Settings → Privacy & Security → Developer Mode). Each restarts.
3. Keep the Mac, iPhone and watch on the same **home Wi-Fi**, not a phone hotspot: the Mac reaches the watch over the network through the iPhone.
4. Check that both show up as `connected`:

```bash
xcrun devicectl list devices
```

**Build, sign and install** (from the repository root). The first command registers the devices and creates the provisioning profiles; the watch app is built and signed with the iPhone app:

```bash
xcodebuild build -project ios/EchoCare.xcodeproj -scheme EchoCare -configuration Debug -destination 'id=<iphone-udid>' -allowProvisioningUpdates -allowProvisioningDeviceRegistration -derivedDataPath ios/build
```

```bash
xcrun devicectl device install app --device <iphone-udid> ios/build/Build/Products/Debug-iphoneos/EchoCare.app
```

```bash
xcrun devicectl device install app --device <watch-udid> ios/build/Build/Products/Debug-watchos/EchoCareWatch.app
```

**The first launch is refused** until you trust the developer: on the iPhone, Settings → General → VPN & Device Management → your Apple Account → Trust.

To read a file the app wrote, such as a log, copy it out of the app's container:

```bash
xcrun devicectl device copy from --device <udid> --domain-type appDataContainer --domain-identifier ro.echocare.ios --source Documents/<file> --destination <file>
```

### Free Personal Team limits

| Limit | What to do |
|---|---|
| Installs expire after **7 days** | Build and install again before the demo |
| At most **3 free-signed apps** per device | Remove old test apps from the iPhone |
| No push, iCloud, App Groups or Sign in with Apple | Screens re-read every `REREAD_SECONDS` instead of push |
| A bundle ID belongs to the team that registered it | One signer for the demo build; others set their own `BUNDLE_ID` |

**During a demo, don't swipe the app away** in the iPhone's app switcher: iOS relaunches the app in the background for the watch's messages, but may not relaunch an app the user force-quit.

## Test

```bash
xcodebuild test -project ios/EchoCare.xcodeproj -scheme EchoCare -destination 'platform=iOS Simulator,name=iPhone 17'
```

```bash
swift test --package-path ios/Shared
```

The second runs on the Mac with no simulator, and is the pre-commit hook for changes under `ios/Shared/` ([lefthook.yml](../lefthook.yml)). There is no iOS CI: hosted macOS runners would need the Xcode 27.2 runtimes and buy little for a demo client.

## Design decisions

| Decision | Why |
|---|---|
| **A plain Swift port, not Kotlin Multiplatform** | The design's approach A: SwiftUI maps closely onto Compose, Xcode is the only toolchain (ADR-001), nothing in `android/` changes |
| **`project.pbxproj` written by hand, folder-synchronized groups** | The project file stays small and readable; a file added to a target folder needs no project edit |
| **Settings in `Config/Base.xcconfig`, overrides in `Local.xcconfig`** | Nothing team- or person-specific is committed. `Local.xcconfig` is included last, like `local.properties` |
| **Info.plist fragments and entitlements in `Config/`** | Outside the synchronized folders, so they aren't copied as resources. The rest of Info.plist is generated from `INFOPLIST_KEY_*` settings |
| **`AppConfig` reads Info.plist** | `API_URL`, `REREAD_SECONDS` and `REAL_SMS` are build settings, as Android's `BuildConfig` fields are; Debug builds define `DEMO` for the watch's demo timings |
| **Strings keyed by the Android names** | `Localizable.xcstrings` holds every `strings.xml` entry in Romanian, so a screen port looks up the same key as the Kotlin screen |
| **The Android theme, fonts included** | `Theme` carries the palette and type scale of `android/app/.../ui/theme`; Archivo and JetBrains Mono are bundled with their OFL licences |
| **`GoogleService-Info.plist` committed** | Public client config, like Android's Firebase web config. Its Encoded App ID is the URL scheme Firebase's reCAPTCHA page returns to |
| **HealthKit entitlement only** | A free team can sign it (design, Spike results); push and the rest need a paid account |
| **The watch app has no identity** | G5: it never calls the API; the iPhone app relays its events and check-ins |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `Signing for "EchoCare" requires a development team` | `Config/Local.xcconfig` is missing or has no `DEVELOPMENT_TEAM`. See [Set up once](#set-up-once) |
| `No profiles for 'ro.echocare.ios' were found` or the bundle ID is unavailable | The bundle ID is registered to another team. Set your own `BUNDLE_ID` in `Local.xcconfig`, or build with the demo signer's team |
| `Unable to find a destination matching … name=iPhone 17` or an ambiguous match | The iOS 27.2 runtime is missing (`xcodebuild -downloadPlatform iOS`), or two simulators share the name: use `id=<udid>` from `xcrun simctl list devices` |
| "Untrusted Developer" when opening the app | Trust the developer: Settings → General → VPN & Device Management |
| The watch shows `unavailable` in `devicectl list devices` | Developer Mode is off on the watch, or the devices aren't on the same Wi-Fi as the Mac. A hotspot often fails |
| The app stops opening after a week | The free provisioning profile expired. Build and install again |
| `Multiple commands produce …/Info.plist` | An `Info.plist` was added inside `EchoCare/` or `EchoCareWatch/`. Move its keys to `Config/*-Info.plist` |

## What is not built yet

| Piece | Spec | Plan task |
|---|---|---|
| API client, Firebase token, retry on 401 | 04, auth-layer | 4 |
| Phone sign-in, landing, role routing, profile | auth-layer §8 | 5 |
| Senior home, starting the watch's workout | UC-03 | 6 |
| Watch monitoring, „Sunteți bine?”, event queue, check-ins | G14, UC-09, UC-13 | 7 |
| WatchConnectivity relay to FastAPI | 04 §3 | 8 |
| Caregiver and medic screens, medic home, iPad layout; enrollment and signature; DAS incidents | UC-01, UC-12 | 9–11 |
| ADR-007, architecture and root AGENTS.md rows | | 12 |
