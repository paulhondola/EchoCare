# AGENTS.md: android/app

The phone and tablet app, `ro.echocare`. One app for four roles: after Firebase phone sign-in, the grants from `GET /me` choose which screens appear (G3). Today it signs in and opens a home per role: the medic's and the caregiver's seniors, the senior's own page, and the DAS incidents with Preiau and Rezolvă cazul (seniors §8, UC-11, UC-12). The medic registers and edits seniors with „Pacient nou” (seniors §9). Build-wide rules and commands: [../AGENTS.md](../AGENTS.md).

## Layout

```
app/src/
├── main/java/ro/echocare/
│   ├── EchoCareApp.kt    @HiltAndroidApp
│   ├── MainActivity.kt    Compose entry; starts phone verification; the sign-in screens
│   ├── Api.kt             EchoCareApi (Retrofit): one function per endpoint of 04-interfaces.md
│   ├── Modules.kt         Hilt: FirebaseAuth, and EchoCareApi with the token interceptor and 401 retry
│   ├── auth/Screen.kt     the sign-in screen state and what /me's answer leads to, tested on the JVM
│   ├── auth/AuthViewModel.kt   sign-in, GET /me, the saved role
│   ├── auth/Landing.kt    the signed-out first screen; „Intrați” leads on to the phone step
│   ├── home/Load.kt       what a list or a page shows for each answer, tested on the JVM (seniors §8.2)
│   ├── home/Routes.kt     the type-safe routes, the home of each role, the state labels
│   ├── home/HomeNav.kt    the NavHost of the signed-in app
│   ├── home/Profile.kt    the profile page from the top bar's square: switch role, alerts, Ieșire
│   ├── home/Tasks.kt      the medic home's to-do list from the patient rows, tested on the JVM
│   ├── home/MedicHome.kt  the medic's home: the code strip and the tasks
│   ├── home/Frame.kt      the shared top bar, the timed re-read, loading and failure states
│   ├── home/Seniors*.kt   the medic's and the caregiver's list of seniors
│   ├── home/Senior*.kt    one senior's page
│   ├── home/CallMe.kt     „Sunați-mă”: the request, the states after its answer, the button, tested on the JVM (UC-10)
│   ├── home/Calls.kt      the senior page's short call history and call-in-progress badge, tested on the JVM (UC-12)
│   ├── das/Incidents.kt   DAS: sorting, relative time, the senior's words, Maps link, refusals, tested on the JVM (UC-11, UC-12)
│   ├── das/Incident*.kt   the DAS home (open and in progress) and one incident's page with Preiau
│   ├── das/Resolve*.kt    „Rezolvare caz”: an outcome and a note
│   ├── enroll/Form.kt     „Pacient nou”: steps, fields, validation, what each step sends, tested on the JVM (seniors §9)
│   ├── enroll/Refusal.kt  both refusal bodies and what the form does with each, tested on the JVM (seniors §9.3)
│   ├── enroll/Enroll*.kt  the medic's four-step form
│   ├── push/Push.kt       what a push says, the refresh signal, tested on the JVM (04 §6)
│   ├── push/MessagingService.kt   Firebase Messaging: saves a new token, shows an alert in front, signals refreshes
│   ├── push/Notifications.kt      the `alerts` channel and the alert notification
│   ├── push/NotificationsPrompt.kt   asks for notifications, in Romanian, on the caregiver's, medic's and DAS home
│   ├── ui/Components.kt   the dashboard's pieces: SnButton, Chip, FieldRow, Banner, CallButton, SnTextField
│   ├── ui/Format.kt       phone numbers as people read them, tested on the JVM
│   └── ui/theme/          one dark Material 3 theme: Palette.kt (spec 07 §2.1), Type.kt, Theme.kt
├── main/res/font/         Archivo and JetBrains Mono, variable fonts (OFL licences in main/assets/licenses/)
├── main/keepRules/        R8 keep rules for release
├── debug/AndroidManifest.xml   debug only: ACCESS_LOCAL_NETWORK, cleartext HTTP to 10.0.2.2
├── test/                  JVM unit tests
└── androidTest/           instrumented tests, not run in CI
```

## Scope

- Becomes: sign-in and role picker (UC-02), the senior's „Sunați-mă” and the watch relay, caregiver alerts, the medic's tablet layout (UC-01, UC-12), Firebase push, the DAS alerts included (G4, 04 §6).
- The phone is the watch's only route to the API (G5). Watch messages arrive over the Data Layer on the paths in `:shared`.
- Permissions are enforced by FastAPI. The app hides screens; it does not guard data.

## Commands

From `android/`.

| Task | Command |
|---|---|
| Debug APK | `./gradlew :app:assembleDebug` |
| Unit tests | `./gradlew :app:testDebugUnitTest` |
| Lint | `./gradlew :app:lint` |
| Install and launch | `android run --device=emulator-5554 --apks=app/build/outputs/apk/debug/app-debug.apk --install-options=-g` |
| Grant local-network after a Studio install | `adb shell pm grant ro.echocare android.permission.ACCESS_LOCAL_NETWORK` |

## Rules

- **The base URL is `BuildConfig.API_URL + "/api/"`**; endpoint paths in `EchoCareApi` use the spec's names without `/api`. `debug` → staging (or `echocare.apiUrl`), `release` → production.
- **Decode leniently.** `Json { ignoreUnknownKeys = true }` stays. Spec enumerations (trigger, incident outcome, push `type`) are decoded as strings with a fallback, never a plain Kotlin `enum`, which crashes on a value the server adds later (ADR-001 §2.3).
- **The Firebase token goes in one OkHttp interceptor**, not per call.
- **UI strings are Romanian**, in `res/values/strings.xml`.
- **The look is the DAS dashboard's** ([07-dashboard-stitch-spec.md](../../docs/specs/echocare/07-dashboard-stitch-spec.md)): one dark theme, no rounded corners, 2dp rules under sections, button labels flush left, Archivo with JetBrains Mono for phone numbers and ids. Take colours from `Palette` (`Rosu`, `Galben`, `Verde` for the codes) and build from `ui/Components.kt` rather than stock Material buttons and cards. A colour changed in `dashboard/src/styles.css` changes in `Palette.kt` too.
- Cleartext HTTP and local-network access belong in `src/debug/` only; release talks to Railway over HTTPS.
