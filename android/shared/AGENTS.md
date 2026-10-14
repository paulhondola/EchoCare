# AGENTS.md: android/shared

Plain Kotlin shared by `:app` and `:wear`. A `java-library` module with no Android imports, so its tests run on the JVM in CI with no emulator (06 §5). Build-wide rules: [../AGENTS.md](../AGENTS.md).

## Layout

```
shared/src/main/java/bia/sentinela/shared/
├── DataLayer.kt      Wearable Data Layer message paths: EVENT, CHECK_IN, RECEIVED
└── FallDetector.kt   Fall detection from the accelerometer (P19), thresholds from spike S13
```

Tests go in `shared/src/test/java/bia/sentinela/shared/`.

## Scope

- Becomes: Data Layer paths, the event and check-in types the watch sends the phone, and the watch's threshold logic that decides whether a senior gets a call (G14, UC-09).
- Anything both apps must agree on lives here, so phone and watch can't drift apart.
- Not here: Android APIs, Compose, networking, anything only one app uses.

## Commands

From `android/`.

| Task | Command |
|---|---|
| Unit tests | `./gradlew :shared:test` |
| Build | `./gradlew :shared:build` |

CI runs `:shared:test` by name: this module is plain Kotlin, so `testDebugUnitTest` does not include it.

## Rules

- **No `android.*` or `androidx.*` imports.** The module would stop compiling as plain JVM Kotlin, and the CI tests that guard the threshold logic would go with it.
- **Threshold logic needs a test.** It decides whether a senior is called; every rule gets a JVM unit test.
- **Data Layer paths and payloads are a wire format** between two separately installed APKs. Add new paths and fields; don't rename or repurpose existing ones.
- Java/Kotlin target is 11, matching both apps.
