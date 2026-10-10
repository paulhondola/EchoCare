# AGENTS.md: android

One Gradle build, two APKs: the phone app for the senior, caregiver, medic and DAS roles, and the Wear OS app for the senior's watch. Kotlin, Jetpack Compose, AGP 9.4, Gradle 9.6 on JDK 25 (downloaded by Gradle). Setup, emulators and troubleshooting: [README.md](README.md).

## Layout

| Module | What | Agent guide |
|---|---|---|
| `:app` | Phone and tablet app, `applicationId` and namespace `bia.sentinela` | [app/AGENTS.md](app/AGENTS.md) |
| `:wear` | Wear OS app, same `applicationId`, namespace `bia.sentinela.wear` | [wear/AGENTS.md](wear/AGENTS.md) |
| `:shared` | Plain Kotlin, no Android imports, used by both | [shared/AGENTS.md](shared/AGENTS.md) |

```
android/
├── settings.gradle.kts           includes :app, :wear, :shared
├── build.gradle.kts              plugins only
├── gradle/libs.versions.toml     every dependency and plugin version
├── gradle/gradle-daemon-jvm.properties   pins JDK 25
├── local.properties              git-ignored: sdk.dir, keystore, optional sentinela.apiUrl
└── .idea/                        only .name, vcs.xml, inspectionProfiles/, codeStyles/, runConfigurations/ are committed
```

## Commands

From `android/`. CI ([android.yml](../.github/workflows/android.yml)) runs the first one.

| Task | Command |
|---|---|
| Lint, JVM unit tests, debug APKs (CI) | `./gradlew lint testDebugUnitTest assembleDebug` |
| Build one APK | `./gradlew :app:assembleDebug` / `./gradlew :wear:assembleDebug` |
| Release APK (R8 on) | `./gradlew :app:assembleRelease` |
| Test only the shared logic | `./gradlew :shared:test` |
| List modules, variants, APK paths | `android describe --project_dir=.` |
| Start / list emulators | `android emulator start Senior_Phone` / `android emulator list --long` |
| Install and launch (`-g` grants local-network) | `android run --device=emulator-5554 --apks=app/build/outputs/apk/debug/app-debug.apk --install-options=-g` |
| Read the screen as JSON | `android layout --device=emulator-5554 --flat` |
| Screenshot | `android screen capture --device=emulator-5554 -o phone.png` |
| Search Android docs | `android docs search "<keywords>"` |

`android run` does not compile; build first. Pass `--device` (or `adb -s`) when more than one emulator is running. For a debug build to reach the laptop's Compose stack, `local.properties` needs `sentinela.apiUrl=http://10.0.2.2:8000`; without it, debug talks to staging.

## Rules

- **Every build needs the shared keystore.** Debug and release, phone and watch, are signed with one key from `local.properties`. Without it the build fails at signing; ask the user rather than inventing a debug key or disabling signing. Never commit `*.jks` or `local.properties`.
- **Dependencies go through `libs.versions.toml`**, never as inline coordinates.
- **The phone and watch stay in lockstep.** Same `applicationId`, same signing block, same version, or the Data Layer silently drops messages (ADR-001 §2.1).
- **Release builds use R8.** A release-only crash is an R8 problem; launch a release build before calling one done. Keep rules go in `<module>/src/main/keepRules/`.
- **No DI framework, Navigation or Room yet.** Each arrives with the first feature that needs it. Data lives in FastAPI, not on the device.
- **CI has no emulator tests.** Sensors and delivery only show on real hardware (spikes S5–S7); say so when a change can't be verified on the JVM.
