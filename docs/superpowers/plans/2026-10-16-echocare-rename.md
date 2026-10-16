# EchoCare Monorepo Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rename the entire Sentinela repository to EchoCare across Android (`ro.echocare`), FastAPI backend (`echocare-backend`), SvelteKit dashboard (`echocare-dashboard`), local infrastructure, and specifications.

**Architecture:** Execute an atomic, layer-by-layer rename starting with local Docker Compose infrastructure and database configurations, moving to the FastAPI backend and SvelteKit dashboard, refactoring the Android and Wear OS package structures to `ro.echocare`, and finishing with documentation, CI workflows, and multi-tier verification.

**Tech Stack:** Python 3.14 (uv, FastAPI, pytest), Svelte 5 / SvelteKit 3 (Vite, Tailwind v4, DaisyUI 5), Kotlin / Android SDK 37 (Jetpack Compose, Wear OS, Hilt, Gradle), Docker Compose, PostgreSQL 18.

**Spec:** [docs/superpowers/specs/2026-10-16-echocare-rename-design.md](file:///Users/paulhondola/Developer/Sentinela-Test/docs/superpowers/specs/2026-10-16-echocare-rename-design.md)

## Global Constraints
- Android app package and namespace is `ro.echocare`; wear namespace is `ro.echocare.wear` with `applicationId = "ro.echocare"`; shared library is `ro.echocare.shared`.
- Firebase: Project ID is `echocare-app`.
- Backend: Package is `echocare-backend`, title is `EchoCare`, loggers are `echocare.*`.
- Database: Database name and user are `echocare`, test database is `echocare_test`.
- Dashboard: Package is `echocare-dashboard`, DaisyUI theme is `echocare`, brand text is `ECHOCARE`.
- Specifications: Folder is `docs/specs/echocare/`.
- User-facing text: UI strings in Romanian remain Romanian; brand name is `EchoCare`.

## Review Focus
- Docker Compose & Local DB: `echocare` user and `echocare_test` creation must allow migrations and tests to run smoothly without manual interventions.
- Android Google Services Plugin: `google-services.json` must match package name `ro.echocare` and project `echocare-app` so `:app:processDebugGoogleServices` succeeds.
- Wearable Data Layer URI: URIs must match across phone and watch (`/echocare/*`), otherwise watch check-in and event messages are dropped.
- Dashboard Styling: Custom DaisyUI theme identifier `echocare` must match what Tailwind/DaisyUI loads so components style properly.
- Backend Loggers: All loggers must use `echocare.*` so log level settings in `main.py` work consistently.

---

### Task 1: Infrastructure & Local Stack Configuration

**Files:**
- Modify: `compose.yaml`
- Modify: `backend/.env.example`
- Modify: `.railway/railway.ts`
- Modify: `.railway/package.json`

**Interfaces:**
- Produces: Postgres service running user/database `echocare` and initializing `echocare_test`; default S3 bucket `echocare`.

- [ ] **Step 1: Update Postgres & MinIO configuration in `compose.yaml`**
  - Set `POSTGRES_USER: echocare`, `POSTGRES_PASSWORD: echocare`, `POSTGRES_DB: echocare`.
  - Update healthcheck command: `pg_isready -U echocare`.
  - Update `create-test-db` inline sql content to: `CREATE DATABASE echocare_test;`.
  - Update `api` service environment: `DATABASE_URL: postgresql://echocare:echocare@db:5432/echocare`.
  - Update `S3_BUCKET_NAME: ${S3_BUCKET_NAME:-echocare}` and MinIO create-bucket entrypoint command.

- [ ] **Step 2: Update `backend/.env.example`**
  - Change default `DATABASE_URL` to `postgresql://echocare:echocare@localhost:5432/echocare`.
  - Change default commented `S3_BUCKET_NAME` to `echocare`.

- [ ] **Step 3: Update `.railway/` project settings**
  - In `.railway/railway.ts`, change project name to `project("EchoCare", ...)` and Firebase config defaults to `echocare-app.firebaseapp.com` / `echocare-app`.
  - In `.railway/package.json`, change `"name": "sentinela-railway"` to `"name": "echocare-railway"`.

- [ ] **Step 4: Verify compose file syntax**
  - Run: `docker compose config`
  - Expected: Clean configuration output with `echocare` variables and exit code 0.

- [ ] **Step 5: Commit changes**
  ```bash
  git add compose.yaml backend/.env.example .railway/
  git commit -m "chore: rename infrastructure and local database to echocare"
  ```

---

### Task 2: Backend Service Renaming

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/main.py`
- Modify: `backend/app/auth/service.py`
- Modify: `backend/app/core/storage.py`
- Modify: `backend/app/incidents/service.py`
- Modify: `backend/app/seniors/service.py`
- Modify: `backend/app/voice/dialogue.py`
- Modify: `backend/app/voice/router.py`
- Modify: `backend/app/voice/service.py`
- Modify: `backend/app/voice/session.py`
- Modify: `backend/app/voice/twilio.py`
- Modify: `backend/tests/conftest.py`
- Modify: `backend/tests/core/test_settings.py`
- Modify: `backend/tests/core/test_storage.py`
- Modify: `backend/tests/auth/test_profile.py`
- Modify: `backend/tests/seniors/test_reach.py`
- Modify: `backend/tests/voice/test_relay.py`
- Modify: `backend/tests/voice/test_voice.py`
- Modify: `backend/scripts/seed.py`

**Interfaces:**
- Produces: FastAPI app with title `EchoCare`, package `echocare-backend`, `echocare.*` loggers, and test suite targeting `echocare_test`.

- [ ] **Step 1: Update package metadata and app entrypoint**
  - In `backend/pyproject.toml`, change `name = "sentinela-backend"` to `name = "echocare-backend"`.
  - In `backend/app/main.py`, change `title="Sentinela"` to `title="EchoCare"`, and update loggers to `echocare` and `echocare.incidents`.

- [ ] **Step 2: Update all logger definitions and Firebase project ID in `backend/app/`**
  - `app/auth/service.py`: `log = logging.getLogger("echocare.auth")`, `FIREBASE_PROJECT_ID = "echocare-app"`.
  - `app/core/storage.py`: `log = logging.getLogger("echocare.storage")`.
  - `app/incidents/service.py`: `log = logging.getLogger("echocare.incidents")`.
  - `app/seniors/service.py`: `log = logging.getLogger("echocare.seniors")`.
  - `app/voice/dialogue.py`: `log = logging.getLogger("echocare.voice")`.
  - `app/voice/router.py`: `log = logging.getLogger("echocare.voice")`.
  - `app/voice/service.py`: `log = logging.getLogger("echocare.voice")`.
  - `app/voice/session.py`: `log = logging.getLogger("echocare.voice")`.
  - `app/voice/twilio.py`: `log = logging.getLogger("echocare.twilio")`.

- [ ] **Step 3: Update test fixtures, test assertions, and scripts**
  - In `backend/tests/conftest.py`: update test DB URL to `postgresql://echocare:echocare@localhost:5432/echocare_test` and `PUBLIC_BASE_URL` to `"https://echocare.test"`.
  - In `backend/tests/core/test_settings.py`: replace test strings referencing `sentinela` database with `echocare`.
  - In `backend/tests/core/test_storage.py`: change test database URL to `echocare_test`, bucket to `echocare-test`, and assert on `echocare-test`.
  - In `backend/tests/auth/test_profile.py`: change `logger="sentinela.auth"` to `logger="echocare.auth"`.
  - In `backend/tests/seniors/test_reach.py`: change `logger="sentinela"` to `logger="echocare"`.
  - In `backend/tests/voice/test_relay.py` & `test_voice.py`: update expected test URLs `https://sentinela.test` and `wss://sentinela.test` to `echocare.test`.
  - In `backend/scripts/seed.py`: update connection strings and docstrings from `sentinela` to `echocare`.

- [ ] **Step 4: Run backend formatting and tests**
  - Run: `cd backend && uv run ruff check && uv run ruff format --check && uv run lint-imports && uv run pytest`
  - Expected: All checks pass, 0 errors, all unit tests green.

- [ ] **Step 5: Commit changes**
  ```bash
  git add backend/
  git commit -m "feat(backend): rename service, loggers and tests to echocare"
  ```

---

### Task 3: Web Dashboard Renaming

**Files:**
- Modify: `dashboard/package.json`
- Modify: `dashboard/package-lock.json`
- Modify: `dashboard/src/app.html`
- Modify: `dashboard/src/features/shell/Shell.svelte`
- Modify: `dashboard/src/ui/Brand.svelte`
- Modify: `dashboard/src/styles.css`

**Interfaces:**
- Produces: SvelteKit dashboard branded as `ECHOCARE` with DaisyUI theme `echocare` and package name `echocare-dashboard`.

- [ ] **Step 1: Update branding and page titles**
  - In `dashboard/src/ui/Brand.svelte`, update text from `SENTINELA` to `ECHOCARE`.
  - In `dashboard/src/app.html`, change title `<title>Sentinela DAS</title>` to `<title>EchoCare DAS</title>`.
  - In `dashboard/src/features/shell/Shell.svelte`, change page title suffix from `Sentinela DAS` to `EchoCare DAS`.

- [ ] **Step 2: Update theme identifier and package metadata**
  - In `dashboard/src/styles.css`, change DaisyUI theme `name: "sentinela";` to `name: "echocare";` and update accompanying comments.
  - In `dashboard/package.json` and `dashboard/package-lock.json`, change `"name": "sentinela-dashboard"` to `"name": "echocare-dashboard"`.

- [ ] **Step 3: Run dashboard checks and build**
  - Run: `cd dashboard && npx --no vp check && npx --no -- svelte-check --tsgo --fail-on-warnings && npm run build`
  - Expected: Check passes with 0 errors and 0 warnings, build succeeds.

- [ ] **Step 4: Commit changes**
  ```bash
  git add dashboard/
  git commit -m "feat(dashboard): rename branding, titles and theme to echocare"
  ```

---

### Task 4: Android & Wear OS Package & File Structure Migration

**Files:**
- Move & Rename:
  - `android/app/src/main/java/bia/sentinela/` → `android/app/src/main/java/ro/echocare/`
  - `android/app/src/test/java/bia/sentinela/` → `android/app/src/test/java/ro/echocare/`
  - `android/app/src/androidTest/java/bia/sentinela/` → `android/app/src/androidTest/java/ro/echocare/`
  - `android/wear/src/main/java/bia/sentinela/wear/` → `android/wear/src/main/java/ro/echocare/wear/`
  - `android/shared/src/main/java/bia/sentinela/shared/` → `android/shared/src/main/java/ro/echocare/shared/`
  - `android/app/src/main/java/ro/echocare/SentinelaApp.kt` → `android/app/src/main/java/ro/echocare/EchoCareApp.kt`
- Modify:
  - `android/settings.gradle.kts`
  - `android/app/build.gradle.kts`
  - `android/wear/build.gradle.kts`
  - `android/app/google-services.json`
  - `android/app/src/main/AndroidManifest.xml`
  - `android/app/src/main/res/values/strings.xml`
  - `android/app/src/main/res/values/themes.xml`
  - `android/wear/src/main/res/values/strings.xml`
  - `android/shared/src/main/java/ro/echocare/shared/DataLayer.kt`
  - All moved Kotlin files in `:app`, `:wear`, `:shared`

**Interfaces:**
- Produces: Android `:app` with `namespace = "ro.echocare"`, `:wear` with `namespace = "ro.echocare.wear"`, `:shared` with `ro.echocare.shared`, app named `EchoCare`, and matching Google Services client.

- [ ] **Step 1: Move directory structures**
  - Move directories using git mv:
    - `mkdir -p android/app/src/main/java/ro && git mv android/app/src/main/java/bia/sentinela android/app/src/main/java/ro/echocare`
    - `mkdir -p android/app/src/test/java/ro && git mv android/app/src/test/java/bia/sentinela android/app/src/test/java/ro/echocare`
    - `mkdir -p android/app/src/androidTest/java/ro && git mv android/app/src/androidTest/java/bia/sentinela android/app/src/androidTest/java/ro/echocare`
    - `mkdir -p android/wear/src/main/java/ro/echocare && git mv android/wear/src/main/java/bia/sentinela/wear android/wear/src/main/java/ro/echocare/wear`
    - `mkdir -p android/shared/src/main/java/ro/echocare && git mv android/shared/src/main/java/bia/sentinela/shared android/shared/src/main/java/ro/echocare/shared`
    - Rename `git mv android/app/src/main/java/ro/echocare/SentinelaApp.kt android/app/src/main/java/ro/echocare/EchoCareApp.kt`
    - Remove leftover empty `bia/` directories.

- [ ] **Step 2: Update package names, imports, and classes in Kotlin files**
  - Replace `package bia.sentinela` with `package ro.echocare`.
  - Replace `import bia.sentinela.` with `import ro.echocare.`.
  - In `EchoCareApp.kt`: rename class `SentinelaApp` to `EchoCareApp`.
  - In `ro/echocare/Api.kt`: rename interface `SentinelaApi` to `EchoCareApi`, and update references in `Modules.kt`, `SeniorViewModel.kt`, `SeniorsViewModel.kt`, `ApiTest.kt`.
  - In `ro/echocare/ui/theme/Theme.kt`: rename `SentinelaTheme` to `EchoCareTheme`, `SentinelaColors` to `EchoCareColors`, `SentinelaShapes` to `EchoCareShapes`.
  - In `ro/echocare/wear/presentation/theme/Theme.kt`: rename `SentinelaTheme` to `EchoCareTheme`.
  - In `ro/echocare/shared/DataLayer.kt`: update URIs to `/echocare/event`, `/echocare/check-in`, `/echocare/received`.

- [ ] **Step 3: Update Android XML resources and Manifests**
  - In `android/app/src/main/res/values/strings.xml`: change `<string name="app_name">Sentinela</string>` to `<string name="app_name">EchoCare</string>`.
  - In `android/wear/src/main/res/values/strings.xml`: change `<string name="app_name">Sentinela</string>` to `<string name="app_name">EchoCare</string>`.
  - In `android/app/src/main/res/values/themes.xml`: change style `Theme.Sentinela` to `Theme.EchoCare`.
  - In `android/app/src/main/AndroidManifest.xml`: set `android:name=".EchoCareApp"` and `android:theme="@style/Theme.EchoCare"`.

- [ ] **Step 4: Update Gradle scripts and Google Services configuration**
  - In `android/settings.gradle.kts`: change `rootProject.name = "Sentinela"` to `rootProject.name = "EchoCare"`.
  - In `android/app/build.gradle.kts`:
    - `namespace = "ro.echocare"`
    - `defaultConfig.applicationId = "ro.echocare"`
    - Signing config & localProps: `echocare.keystore`, `echocare.keystore.password`, `echocare.key.password`.
    - API URL prop: `echocare.apiUrl` with fallback `https://echocare-api-staging.up.railway.app`.
  - In `android/wear/build.gradle.kts`:
    - `namespace = "ro.echocare.wear"`
    - `defaultConfig.applicationId = "ro.echocare"`
    - Signing config: `echocare.keystore` etc.
  - In `android/app/google-services.json`:
    - Change `"project_id": "sentinela-8f474"` to `"project_id": "echocare-app"`.
    - Change `"storage_bucket": "sentinela-8f474.firebasestorage.app"` to `"storage_bucket": "echocare-app.firebasestorage.app"`.
    - Change `"package_name": "bia.sentinela"` to `"package_name": "ro.echocare"`.

- [ ] **Step 5: Run Android formatting and unit tests**
  - Run: `cd android && ./gradlew ktlintFormat && ./gradlew ktlintCheck testDebugUnitTest :shared:test`
  - Expected: ktlint passes, all unit tests in `:app` and `:shared` pass.

- [ ] **Step 6: Commit changes**
  ```bash
  git add android/
  git commit -m "feat(android): refactor package and namespaces to ro.echocare"
  ```

---

### Task 5: Specifications, Documentation & CI Workflows

**Files:**
- Move: `docs/specs/sentinela/` → `docs/specs/echocare/`
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `backend/README.md`
- Modify: `dashboard/AGENTS.md`
- Modify: `dashboard/README.md`
- Modify: `android/AGENTS.md`
- Modify: `android/app/AGENTS.md`
- Modify: `android/wear/AGENTS.md`
- Modify: `android/shared/AGENTS.md`
- Modify: `.railway/AGENTS.md`
- Modify: `.railway/README.md`
- Modify: `docs/adr/ADR-001-monorepo-and-delivery.md`
- Modify: `.github/workflows/backend.yml`
- Modify: `.github/workflows/android.yml`

**Interfaces:**
- Produces: Updated markdown documentation pointing to `docs/specs/echocare/` and CI workflows running against `echocare` services.

- [ ] **Step 1: Move spec directory**
  - Run: `git mv docs/specs/sentinela docs/specs/echocare`

- [ ] **Step 2: Update documentation and AGENTS.md files**
  - Replace references to `Sentinela` with `EchoCare` in `README.md` and `AGENTS.md` summaries.
  - Update all links pointing to `docs/specs/sentinela/` to `docs/specs/echocare/`.
  - Update CLI examples (e.g. `docker compose exec db createdb -U echocare echocare_test`).
  - Update module AGENTS.md (`android/wear/AGENTS.md`, `android/shared/AGENTS.md`, `dashboard/AGENTS.md`, `backend/AGENTS.md`) with `ro.echocare` packages and `echocare` themes.

- [ ] **Step 3: Update CI workflows**
  - In `.github/workflows/backend.yml`:
    - Service container: `POSTGRES_USER: echocare`, `POSTGRES_PASSWORD: echocare`, `POSTGRES_DB: echocare_test`.
    - Health check: `pg_isready -U echocare`.
  - In `.github/workflows/android.yml`:
    - Keystore target: `$RUNNER_TEMP/echocare.jks`.
    - Gradle properties: `echocare.keystore`, `echocare.keystore.password`, `echocare.key.password`.

- [ ] **Step 4: Commit changes**
  ```bash
  git add docs/ README.md AGENTS.md backend/ dashboard/ android/ .railway/ .github/
  git commit -m "docs: rename specifications and documentation to echocare"
  ```

---

### Task 6: End-to-End Multi-Tier Verification

**Files:**
- None (Verification across all tiers)

- [ ] **Step 1: Check git grep for unintended residual references**
  - Run: `git grep -i "sentinela" | grep -v "docs/specs/esti-bine" | grep -v "unihack.md" | grep -v "docs/superpowers/plans" | grep -v "docs/superpowers/specs"`
  - Verify that only historical notes (the old hackathon brief / legacy v3 notes) remain.

- [ ] **Step 2: Verify Backend toolchain**
  - Run: `cd backend && uv run ruff check && uv run ruff format --check && uv run lint-imports && uv run pytest`
  - Expected: PASS

- [ ] **Step 3: Verify Dashboard toolchain**
  - Run: `cd dashboard && npx --no vp check && npx --no -- svelte-check --tsgo --fail-on-warnings && npm run build`
  - Expected: PASS

- [ ] **Step 4: Verify Android toolchain**
  - Run: `cd android && ./gradlew ktlintCheck testDebugUnitTest :shared:test assembleDebug`
  - Expected: PASS

- [ ] **Step 5: Verify lefthook pre-commit hooks**
  - Run: `lefthook run pre-commit`
  - Expected: All hooks succeed.
