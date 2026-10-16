# EchoCare Monorepo Rename Design

## Overview
This design specifies the end-to-end renaming of the Sentinela monorepo to **EchoCare**.
The change touches every tier of the project: Android and Wear OS applications (`ro.echocare`), FastAPI backend (`echocare-backend`), SvelteKit dashboard (`echocare-dashboard`), local Docker Compose infrastructure, Railway configuration, CI workflows, and project specifications.

## 1. Naming & Namespace Architecture

| Component | Previous Value | New Value | Notes |
|---|---|---|---|
| Project / Brand | Sentinela | EchoCare | Displayed across titles, UI branding, docs |
| Android Package (:app) | `bia.sentinela` | `ro.echocare` | Application ID and namespace |
| Wear OS Package (:wear) | `bia.sentinela.wear` | `ro.echocare.wear` | Namespace; applicationId stays `ro.echocare` |
| Shared Library (:shared) | `bia.sentinela.shared` | `ro.echocare.shared` | Plain Kotlin library |
| Gradle Root Project | `Sentinela` | `EchoCare` | In `android/settings.gradle.kts` |
| Firebase Project ID | `sentinela-8f474` | `echocare-app` | Project ID placeholder |
| Backend PyPI Package | `sentinela-backend` | `echocare-backend` | In `backend/pyproject.toml` |
| Backend Logger Names | `sentinela.*` | `echocare.*` | Root and sub-loggers in `backend/app/` |
| Postgres DB & User | `sentinela` | `echocare` | Local and CI database |
| Postgres Test DB | `sentinela_test` | `echocare_test` | Isolated test database |
| MinIO / S3 Bucket | `sentinela` | `echocare` | Local default bucket |
| Dashboard NPM Package | `sentinela-dashboard` | `echocare-dashboard` | In `dashboard/package.json` |
| Dashboard DaisyUI Theme | `sentinela` | `echocare` | Custom dark theme in `styles.css` |
| Railway Project Name | `Sentinela` | `EchoCare` | In `.railway/railway.ts` |
| Railway NPM Package | `sentinela-railway` | `echocare-railway` | In `.railway/package.json` |
| Specifications Directory | `docs/specs/sentinela/` | `docs/specs/echocare/` | MVP specs folder |

---

## 2. Infrastructure & Local Stack

### 2.1 Docker Compose (`compose.yaml`)
- **Postgres Service**:
  - `POSTGRES_USER: echocare`
  - `POSTGRES_PASSWORD: echocare`
  - `POSTGRES_DB: echocare`
  - Health check: `pg_isready -U echocare`
  - Database initialization config creates `echocare_test`: `CREATE DATABASE echocare_test;`
- **Backend API Service**:
  - `DATABASE_URL: postgresql://echocare:echocare@db:5432/echocare`
  - `S3_BUCKET_NAME: ${S3_BUCKET_NAME:-echocare}`
- **MinIO Service**:
  - Bucket init script ensures bucket `echocare` is created on startup.

### 2.2 Environment Files
- `backend/.env.example`:
  - `DATABASE_URL=postgresql://echocare:echocare@localhost:5432/echocare`
  - `S3_BUCKET_NAME=echocare`
- `.railway/railway.ts`:
  - Project name: `project("EchoCare", ...)`
  - Environment variables: `VITE_FIREBASE_AUTH_DOMAIN: "echocare-app.firebaseapp.com"`, `VITE_FIREBASE_PROJECT_ID: "echocare-app"`

---

## 3. Backend Service (`backend/`)

### 3.1 Metadata & Application Setup
- `pyproject.toml`: `name = "echocare-backend"`
- `app/main.py`:
  - `FastAPI(title="EchoCare", ...)`
  - Log level configuration: `logging.getLogger("echocare")`, `logging.getLogger("echocare.incidents")`

### 3.2 Logging Namespaces
Update logger initializations across all modules:
- `app/auth/service.py`: `logging.getLogger("echocare.auth")`
- `app/auth/service.py`: `FIREBASE_PROJECT_ID = "echocare-app"`
- `app/core/storage.py`: `logging.getLogger("echocare.storage")`
- `app/incidents/service.py`: `logging.getLogger("echocare.incidents")`
- `app/seniors/service.py`: `logging.getLogger("echocare.seniors")`
- `app/voice/dialogue.py`: `logging.getLogger("echocare.voice")`
- `app/voice/router.py`: `logging.getLogger("echocare.voice")`
- `app/voice/service.py`: `logging.getLogger("echocare.voice")`
- `app/voice/session.py`: `logging.getLogger("echocare.voice")`
- `app/voice/twilio.py`: `logging.getLogger("echocare.twilio")`

### 3.3 Test Suite & Scripts
- `tests/conftest.py`:
  - Set test DB URL: `postgresql://echocare:echocare@localhost:5432/echocare_test`
  - Set public test base URL: `https://echocare.test`
- `tests/core/test_settings.py`: Update connection URL checks to `echocare`.
- `tests/core/test_storage.py`: Update bucket name assertions to `echocare-test`.
- `tests/auth/test_profile.py`: Assert on `echocare.auth` logger.
- `tests/seniors/test_reach.py`: Assert on `echocare` logger.
- `tests/voice/test_relay.py` and `test_voice.py`: Update expected mock URLs to `https://echocare.test/...` and `wss://echocare.test/...`.
- `scripts/seed.py`: Update connection strings and documentation comments.

---

## 4. Web Dashboard (`dashboard/`)

### 4.1 Branding & Shell
- `src/ui/Brand.svelte`: Change brand mark to `ECHOCARE`.
- `src/app.html`: `<title>EchoCare DAS</title>`
- `src/features/shell/Shell.svelte`: Dynamic title template `... EchoCare DAS`.

### 4.2 Styling & Theming
- `src/styles.css`:
  - Rename custom DaisyUI theme definition: `name: "echocare";`
  - Update comment references to the `echocare` theme.

### 4.3 Package & Build
- `package.json` & `package-lock.json`: `"name": "echocare-dashboard"`.
- Update build commands and documentation tags from `sentinela-dashboard` to `echocare-dashboard`.

---

## 5. Android & Wear OS (`android/`)

### 5.1 Package Directory Moves
Move source trees:
- `android/app/src/main/java/bia/sentinela/` → `android/app/src/main/java/ro/echocare//`
- `android/app/src/test/java/bia/sentinela/` → `android/app/src/test/java/ro/echocare//`
- `android/app/src/androidTest/java/bia/sentinela/` → `android/app/src/androidTest/java/ro/echocare//`
- `android/wear/src/main/java/bia/sentinela/wear/` → `android/wear/src/main/java/ro/echocare/wear/`
- `android/shared/src/main/java/bia/sentinela/shared/` → `android/shared/src/main/java/ro/echocare/shared/`
- Remove empty `bia/` parent directories.

### 5.2 Kotlin Source Updates
- In all files under `:app`, `:wear`, and `:shared`:
  - Replace `package bia.sentinela...` with `package ro.echocare...`
  - Replace `import bia.sentinela...` with `import ro.echocare...`
- Class & interface renaming:
  - `SentinelaApp.kt` → `EchoCareApp.kt` (`class EchoCareApp : Application()`)
  - `SentinelaApi` → `EchoCareApi`
  - `SentinelaTheme` → `EchoCareTheme`
  - `SentinelaColors` → `EchoCareColors`
  - `SentinelaShapes` → `EchoCareShapes`
- XML Themes & Strings:
  - `android/app/src/main/res/values/themes.xml`: `<style name="Theme.EchoCare" parent="...">`
  - `android/app/src/main/res/values/strings.xml`: `<string name="app_name">EchoCare</string>`
  - `android/wear/src/main/res/values/strings.xml`: `<string name="app_name">EchoCare</string>`
- AndroidManifest.xml (`:app` & `:wear`):
  - Application name: `android:name=".EchoCareApp"`
  - Theme: `android:theme="@style/Theme.EchoCare"`

### 5.3 Build Configuration
- `android/settings.gradle.kts`: `rootProject.name = "EchoCare"`
- `android/app/build.gradle.kts`:
  - `namespace = "ro.echocare"`
  - `defaultConfig.applicationId = "ro.echocare"`
  - Keystore property keys: `echocare.keystore`, `echocare.keystore.password`, `echocare.key.password`
  - Local API override property: `echocare.apiUrl`
  - Default debug API URL: `https://echocare-api-staging.up.railway.app`
- `android/wear/build.gradle.kts`:
  - `namespace = "ro.echocare.wear"`
  - `defaultConfig.applicationId = "ro.echocare"`
  - Keystore properties updated to `echocare.keystore`
- `android/app/google-services.json`:
  - `project_id`: `"echocare-app"`
  - `storage_bucket`: `"echocare-app.firebasestorage.app"`
  - `android_client_info.package_name`: `"ro.echocare"`

### 5.4 Wearable Data Layer (`ro.echocare.shared.DataLayer`)
Update Data Layer URIs:
- `EVENT = "/echocare/event"`
- `CHECK_IN = "/echocare/check-in"`
- `RECEIVED = "/echocare/received"`

---

## 6. Specifications, CI & Workflows

### 6.1 Specs & Guides
- Move directory `docs/specs/sentinela/` → `docs/specs/echocare/`.
- Update all internal markdown links and cross-references across:
  - `README.md`
  - `AGENTS.md` (root, `backend/`, `dashboard/`, `android/`, `wear/`, `shared/`, `.railway/`)
  - `docs/adr/ADR-001-monorepo-and-delivery.md` and related ADRs
  - Reference texts and commands mentioning `sentinela` (e.g. `docker compose exec db createdb -U echocare echocare_test`).

### 6.2 GitHub Workflows
- `.github/workflows/backend.yml`:
  - Service container Postgres envs: `POSTGRES_USER: echocare`, `POSTGRES_PASSWORD: echocare`, `POSTGRES_DB: echocare_test`.
  - Health command: `pg_isready -U echocare`.
- `.github/workflows/android.yml`:
  - Keystore decoding path: `$RUNNER_TEMP/echocare.jks`.
  - Gradle properties: `echocare.keystore`, `echocare.keystore.password`, `echocare.key.password`.

---

## 7. Verification Plan

Each component must pass verification using its native toolchain:
1. **Infra**: `docker compose config` exits cleanly with valid syntax.
2. **Backend**:
   - `uv run ruff check`
   - `uv run ruff format --check`
   - `uv run lint-imports`
   - `uv run pytest` (all unit and integration tests passing against `echocare_test`)
3. **Dashboard**:
   - `npx --no vp check`
   - `npx --no -- svelte-check --tsgo --fail-on-warnings`
   - `npm run build`
4. **Android**:
   - `./gradlew ktlintCheck`
   - `./gradlew testDebugUnitTest :shared:test`
   - `./gradlew assembleDebug`
