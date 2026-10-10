# AGENTS.md: android/wear

The Wear OS app for the senior's watch: `applicationId` `bia.sentinela`, namespace `bia.sentinela.wear`. Today it is one screen. Build-wide rules and commands: [../AGENTS.md](../AGENTS.md).

## Layout

```
wear/src/main/
├── java/bia/sentinela/wear/presentation/
│   ├── MainActivity.kt    Compose for Wear OS entry
│   └── theme/             Wear Material 3 theme
├── keepRules/             R8 keep rules for release
├── res/
└── AndroidManifest.xml    standalone=false
```

## Scope

- Becomes one screen and one background job: pulse and step monitoring, the „Sunteți bine?” prompt, check-ins (G14, UC-09, UC-13). Thresholds come from `:shared`.
- **The watch is not standalone** (G5). It has no identity and never calls the API. Everything goes to the senior's phone over the Wearable Data Layer, on the paths in `bia.sentinela.shared.DataLayer`.
- No tiles or complications; the spec asks for one screen and one job.

## Commands

From `android/`.

| Task | Command |
|---|---|
| Debug APK | `./gradlew :wear:assembleDebug` |
| Lint | `./gradlew :wear:lint` |
| Start the watch emulator | `android emulator start Senior_Watch` |
| Install and launch | `android run --device=emulator-5556 --apks=wear/build/outputs/apk/debug/wear-debug.apk` |

Check the serial with `android emulator list --long`; the watch is not always `emulator-5556`.

## Rules

- **Keep the signing block identical to `:app`'s**, and the `applicationId` the same. Otherwise the Data Layer drops every message without an error (ADR-001 §2.1).
- **Threshold logic belongs in `:shared`**, not here, so it is tested on the JVM in CI.
- **No network code.** No Retrofit, OkHttp or API URLs in this module.
- Sensors and background delivery can't be verified on an emulator (spikes S5–S7); say so when a change depends on them.
- UI strings are Romanian, in `res/values/strings.xml`.
