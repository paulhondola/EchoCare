# android: the phone and watch apps

One Gradle build that produces two APKs: the Android app for the senior, caregiver, medic and DAS roles (spec G3, G15), and the Wear OS app for the senior's watch (G5). Kotlin, Jetpack Compose, AGP 9.4, Gradle 9.6. The apps are installed on the demo devices by hand, never through the Play Store ([ADR-001](../docs/adr/ADR-001-monorepo-and-delivery.md) §2).

This is the skeleton: the phone app shows whether the API answers, and the watch app shows one screen. The features in [What is not built yet](#what-is-not-built-yet) come next.

| Module | What | Becomes |
|---|---|---|
| [app/](app/) | Phone and tablet app, package `bia.sentinela` | Phone sign-in, then the screens of the granted role: senior („Sunați-mă”, watch relay), caregiver, medic (tablet layout), DAS (red incidents) |
| [wear/](wear/) | Wear OS app, same `applicationId`, namespace `bia.sentinela.wear` | One screen and one background job: pulse and step monitoring, „Sunteți bine?”, check-ins (UC-09, UC-13) |
| [shared/](shared/) | Plain Kotlin, no Android imports | Data Layer paths, event and check-in types, the watch's threshold logic, all tested on the JVM |

## Tools

| Tool | Needed for | Install |
|---|---|---|
| Android Studio, current stable | Everything here | [developer.android.com/studio](https://developer.android.com/studio) |
| Android SDK Platform 37 | Compiling both apps | Studio → Settings → Languages & Frameworks → Android SDK |
| System images: Google Play phone (API 37), Wear OS 7.0 (API 37) | The emulators below | Same place, *SDK Platforms* tab, *Show Package Details* |
| Docker Desktop | The local API, from the repository root | See the [root README](../README.md) |

No separate JDK is needed. Gradle runs on JDK 25, which `gradle/gradle-daemon-jvm.properties` pins and Gradle downloads on its own. In Studio, leave **Settings → Build, Execution, Deployment → Build Tools → Gradle → Gradle JDK** on the embedded JDK.

`adb` and `emulator` come with the SDK but are not on the shell's path. Add them once:

```bash
echo 'export PATH="$HOME/Library/Android/sdk/platform-tools:$HOME/Library/Android/sdk/emulator:$PATH"' >> ~/.zshrc && source ~/.zshrc
```

## Set up once

**1. Get the shared keystore.** Every build, debug included, is signed with one team key (see [Design decisions](#design-decisions)). Copy `sentinela.jks` and its password from the team's password manager to a folder **outside the repository**.

**2. Point `local.properties` at it.** Studio creates `android/local.properties` with `sdk.dir` on the first sync. It is git-ignored. Add:

```properties
sentinela.keystore=/Users/you/Keys/sentinela.jks
sentinela.keystore.password=…
sentinela.key.password=…
sentinela.apiUrl=http://10.0.2.2:8000
```

| Key | What it does |
|---|---|
| `sentinela.keystore` | Absolute path to the shared keystore |
| `sentinela.keystore.password`, `sentinela.key.password` | The same password twice: the keystore is PKCS12, which has one password |
| `sentinela.apiUrl` | Optional. Overrides the API address of **debug** builds. `http://10.0.2.2:8000` is your laptop's Compose stack as seen from an emulator. Leave it out to use staging |

**3. Open `android/` in Android Studio, not the repository root.** The Gradle build starts in this folder. Studio still finds Git one level up, through the committed `.idea/vcs.xml`.

## Emulators

| AVD | Device | Image | Plays |
|---|---|---|---|
| `Senior_Phone` | Medium Phone, 1080 × 2400 | API 37, Google Play | The senior's phone: runs `app`, and later relays the watch |
| `Senior_Watch` | Wear OS Large Round, 454 × 454 | Wear OS 7.0, API 37 | The senior's watch: runs `wear` |

Emulators live in `~/.android/avd/` on each machine, so everyone creates their own. Create them in **Device Manager → +**, and name them by the role they play, so a multi-device test reads clearly. The next ones follow the same pattern:

| AVD | For |
|---|---|
| `Medic_Tablet` | The medic's layout, which targets a tablet (UC-01, UC-12) |
| `Caregiver_Phone` | Receiving yellow and red alerts |
| `DAS_Phone` | The DAS role's red incidents and the hand-over |

Keep the senior's phone on a **Google Play** image: pairing a watch emulator needs the Wear OS companion app from the Play Store. Pairing is in Device Manager → ⋮ next to the watch → *Pair Wearable*. The skeleton does not need it yet; the Data Layer will (UC-03).

If Studio's Edit dialog only changes the name it shows, `emulator -list-avds` keeps the old ID. A full rename means renaming `<id>.avd/` and `<id>.ini`, then the ID in `<id>.ini`, `config.ini` and `snapshots/default_boot/hardware.ini`, with the emulator stopped.

## Run it

**Against the local API.** From the repository root, start the stack:

```bash
docker compose up --watch
```

In Studio, choose the run configuration `app` with the device **Senior Phone**, and press Run. Android 17 blocks apps from private addresses such as `10.0.2.2` unless they hold the runtime permission `ACCESS_LOCAL_NETWORK`. Debug builds declare it, so grant it once after each fresh install:

```bash
adb shell pm grant bia.sentinela android.permission.ACCESS_LOCAL_NETWORK
```

Reopen the app. It shows **API ok (local)**. With the stack stopped, it shows **API unreachable: …**.

**Against staging.** Remove `sentinela.apiUrl` from `local.properties`, sync, and run. It shows **API ok (staging)**. Staging is public HTTPS, so no permission is needed.

**Against production.** Switch the variant to `release` (View → Tool Windows → Build Variants) and run. It shows **API ok (production)**.

**The watch.** Choose the run configuration `wear` with the device **Senior Watch**.

From the command line, with one device connected (add `-s <serial>` from `adb devices` when there are several):

```bash
./gradlew :app:installDebug
```

```bash
./gradlew :wear:installDebug
```

| Variant | API | R8 | Cleartext HTTP, local network |
|---|---|---|---|
| `debug` | staging, or `sentinela.apiUrl` | Off | Allowed, through [app/src/debug/AndroidManifest.xml](app/src/debug/AndroidManifest.xml) |
| `release` | production | On | Not allowed |

Both variants are signed with the shared key, so a release build installs over a debug build and the other way round.

## Test and lint

From `android/`. CI runs the same command ([android.yml](../.github/workflows/android.yml)):

```bash
./gradlew lint testDebugUnitTest assembleDebug
```

| Not in CI | Why |
|---|---|
| Instrumented and emulator tests | Slow and flaky on hosted runners. Background sensors and delivery only show on real hardware (spikes S5–S7) |
| Launching a release build | R8 bugs appear at run time, not at build time. Launch a release build on an emulator before it goes to the demo devices |

CI signs with the keystore from the GitHub secrets `ANDROID_KEYSTORE_BASE64` and `ANDROID_KEYSTORE_PASSWORD`, written into `local.properties`, so the build scripts behave the same as on a laptop.

## Design decisions

| Decision | Why |
|---|---|
| **One Gradle build, three modules** (`:app`, `:wear`, `:shared`) | ADR-001. The phone and watch share their `applicationId`, signing key and version in one place, so they cannot drift apart. The Data Layer only connects apps with the same package and key |
| **Same `applicationId`, different `namespace`** | `applicationId` (`bia.sentinela`) is the install identity and must match on both devices. `namespace` holds the generated `R` and `BuildConfig` classes, so it must be unique per module |
| **`:shared` is plain Kotlin** | The watch's threshold logic decides whether a senior gets a call. Without Android imports, its tests run on the JVM in CI, with no emulator (06 §5) |
| **One app for four roles** | G3. After sign-in, the grants from `GET /me` choose which screens appear. Permissions are enforced by FastAPI, not by the app |
| **The watch is not standalone** | G5. It has no identity and never calls the API: events go through the senior's signed-in phone. The manifest says `standalone=false` |
| **Started from the Studio wizard, then trimmed** | Empty Activity, Empty Wear App and Kotlin Library templates. The watch's example tile and complication are removed: the spec asks for one screen and one job |
| **Compose with Material 3; Wear Compose with Material 3 on the watch** | Studio's default for new projects, and the team's toolkit |
| **Retrofit and kotlinx.serialization** | [Api.kt](app/src/main/java/bia/sentinela/Api.kt) holds one interface, `SentinelaApi`, with one function per endpoint of [04-interfaces.md](../docs/specs/sentinela/04-interfaces.md). The base URL is `API_URL + "/api/"`, so endpoints keep the spec's names. The Firebase token will be attached in one OkHttp interceptor |
| **`ignoreUnknownKeys = true`** | An installed APK keeps talking to a newer API (ADR-001 §2.3). Spec enumerations will also be decoded as strings with a fallback, never as plain enums, which crash on an unknown value |
| **API address fixed per build type** | `debug` → staging, `release` → production (ADR-001 §2.2), as a `BuildConfig` field. Only `local.properties` can override debug |
| **No DI framework, no Navigation, no Room yet** | Each comes with the first feature that needs it. Navigation will arrive with the role screens. A local database is unlikely: all data lives in FastAPI (01 §5) |
| **One signing key for every build** | ADR-001 §2.1. Without it, watch messages are silently dropped, Firebase phone sign-in fails for unregistered keys, and installing over another build fails. The keystore is PKCS12, alias `key0`, one password |
| **R8 on the whole app in release** | The wizard's `optimization { packageScope = … }` split `kotlin.sequences` classes across packages and crashed every release build at startup with an `IllegalAccessError` |
| **`minSdk` 37 on the phone, 36 on the watch** | The newest platforms, for now. To be lowered once the demo devices are known |
| **Only shared IDE settings in Git** | [.gitignore](.gitignore) allows `.idea/.name`, `vcs.xml`, `inspectionProfiles/`, `codeStyles/` and `runConfigurations/`. Everything else in `.idea` is personal (the selected device) or rebuilt from Gradle on every sync |

## Troubleshooting

| Symptom | Cause and fix |
|---|---|
| `INSTALL_FAILED_UPDATE_INCOMPATIBLE: … signatures do not match` | The device has a build signed with another key, typically from before the shared keystore. Uninstall once: `adb uninstall bia.sentinela` |
| `Failed to read key key0 … Given final block not properly padded` | `sentinela.key.password` is wrong. Studio's New Key Store dialog lets the key password differ from the store password, which PKCS12 does not support. Recreate the keystore with `keytool -genkeypair -storetype PKCS12 -alias key0 …` |
| The build fails at signing and names the signing config `shared` | The three keystore lines are missing from `local.properties`, or the path is wrong |
| `API unreachable: failed to connect to /10.0.2.2 … after 10000ms` | `ACCESS_LOCAL_NETWORK` is not granted (see [Run it](#run-it)), or the Compose stack is down. A timeout rather than "connection refused" usually means the permission |
| `API unreachable: HTTP 404` | The API image is older than the `/api` prefix. Start it with `docker compose up --watch`, or rebuild with `docker compose up -d --build api` |
| A release build closes as soon as it opens | An R8 problem. Read the crash with `adb logcat -b crash`, and map obfuscated names back through `app/build/outputs/mapping/release/mapping.txt` |
| `adb: more than one device/emulator` | Add `-s emulator-5554` (from `adb devices`), or set `ANDROID_SERIAL` |
| `zsh: command not found: adb` | The SDK tools are not on the path; see [Tools](#tools) |

## What is not built yet

| Piece | Spec |
|---|---|
| Firebase phone sign-in, `GET /me` and the role picker; `google-services.json` and the key's SHA fingerprints in Firebase | G6, UC-02 |
| Firebase push: alerts, silent refresh, the timed re-read backstop | G4, 04 §6 |
| The four roles' screens, with Navigation; the medic's tablet layout | UC-01, UC-11, UC-12 |
| Watch monitoring, the „Sunteți bine?” prompt, check-ins, the Data Layer relay through the phone | G14, UC-03, UC-09, UC-13 |
| `android-release.yml`: signed APKs to Firebase App Distribution, the watch APK as a workflow artifact | ADR-001 §2.2 |
