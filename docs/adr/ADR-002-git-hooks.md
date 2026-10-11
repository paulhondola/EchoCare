# ADR-002: Git hooks with lefthook, Vite+ for the dashboard, ktlint for Android

**Status:** Proposed
**Date:** 2026-10-11
**Deciders:** the team of four (owners of backend, dashboard, Android, Wear OS)
**Builds on:** [ADR-001](ADR-001-monorepo-and-delivery.md), mainly §2.4 and §2.5

## Context

Each folder has its own checks, and CI runs them only after a push (ADR-001). A formatting slip or a broken test shows up minutes later, on GitHub, and can hold back a deploy. The team wants the same checks to run on the developer's machine when they commit.

The forces at play:

1. **A red workflow holds back deploys.** Railway's Wait for CI waits for every workflow on a commit (ADR-001 §2.4), so a red Android build skips an API deploy. Catching it before the push is the main payoff.
2. **The folders are not equally equipped.** Measured on 2026-10-11:

   | Folder | Format | Lint | Tests | Type check | Time |
   |---|---|---|---|---|---|
   | `backend/` | `ruff format` | `ruff check` | `pytest`, 4 tests, no database | none | about 1 s for all three |
   | `dashboard/` | none | none | none | `tsc --noEmit` | 0.7 s |
   | `android/` | none | Android lint | `testDebugUnitTest` | the Kotlin compiler | Gradle: 12.7 s cold start, 0.5 s with a warm daemon, plus the tasks |
   | `.railway/` | none | none | none | none | |

3. **Gradle is too slow for every commit.** Lint and unit tests add tens of seconds on top of Gradle's start-up.
4. **The dashboard is on TypeScript 7.** typescript-eslint 8.71.1, the current release, declares `typescript >=4.8.4 <6.1.0`. ESLint with type-aware rules would mean downgrading TypeScript.
5. **Watch paths redeploy services.** Any file under `backend/` or `dashboard/` redeploys that service on staging after merge, and an `api` redeploy drops live calls (ADR-001 §1). Hook configuration should not live there.
6. **No root `package.json` or task runner** (ADR-001, option C). A hook manager that needs one is out.
7. **Hooks cannot be enforced.** They live in each clone and are skipped with `--no-verify`. CI stays the gate; hooks only bring its verdict forward.
8. **Four people, five weeks** (ADR-001 force 5). Each tool added is one more thing that can break.

## Decision

**One `lefthook.yml` at the repository root runs fast checks on commit and the Gradle checks on push, each only for the folders the change touches.** The dashboard moves to Vite+, which bundles a formatter (oxfmt), a linter (oxlint) and type checking. Android gets ktlint through its Gradle plugin. CI runs the same tools, so a commit that skips the hooks is still checked.

### What runs when

| A commit touches | On commit | On push |
|---|---|---|
| `backend/` | `ruff check --fix`, then `ruff format`, then `pytest`, about 1 s | nothing |
| `dashboard/` | `vp check --fix`: format, lint, type check, about 1 s | nothing |
| `android/` | `ktlintFormat`: 1–3 s with a warm daemon, about 13 s cold | `ktlintCheck lint testDebugUnitTest :shared:test` |
| only docs, `.railway/`, `.github/` | nothing | nothing |

Formatters fix files and stage the result (`stage_fixed`), so a formatting slip never blocks a commit. A lint error, a type error or a failing test does.

### `lefthook.yml`

```yaml
# Git hooks for the whole repository (ADR-002). One toolchain per folder (ADR-001).
# Install once per clone: brew install lefthook && lefthook install
# Fast checks on commit, Gradle on push. A job runs only when its glob matches.
min_version: 2.2.0

pre-commit:
  parallel: true
  jobs:
    - name: backend
      root: backend/
      glob: "*.py"
      group:
        piped: true # fix, then format, then test: they touch the same files
        jobs:
          - run: uv run ruff check --fix {staged_files}
            stage_fixed: true
          - run: uv run ruff format {staged_files}
            stage_fixed: true
          - run: uv run pytest -q

    - name: dashboard
      root: dashboard/
      glob: "*.{ts,tsx,js,json,css,html}"
      # ponytail: whole project, since a type change can break a file you did not stage.
      # Pass {staged_files} for format and lint if this gets slow.
      # --no: fail when npm ci was never run, instead of downloading some other vp
      run: npx --no vp check --fix
      stage_fixed: true

    - name: android
      root: android/
      glob: "*.{kt,kts}"
      run: ./gradlew -q ktlintFormat
      stage_fixed: true

pre-push:
  jobs:
    - name: android
      root: android/
      glob: "*.{kt,kts,xml,toml,properties,pro}"
      run: ./gradlew ktlintCheck lint testDebugUnitTest :shared:test
```

`lefthook validate` (2.2.1) accepts this file. Three behaviours still need a test with real commits (action item 3):
- nested jobs in a group inherit its `root` and `glob`;
- `{staged_files}` arrive relative to `root`;
- a job whose glob matches nothing is skipped, including on push, where lefthook matches against the files in the pushed commits.

The push check is CI's Android command without `assembleDebug`. Compile errors still surface, because the unit tests compile the main sources. Packaging errors (manifest merging, resources, signing) are left to CI.

### `dashboard/`: Vite+

Vite+ 1.1.0 (`vite-plus` on npm) is one dev dependency that brings Vite, Vitest 5, oxlint 1.87, oxfmt 0.72 and `oxlint-tsgolint`, a type checker built on TypeScript 7's Go compiler. It accepts `typescript ^7` and Node 26.

- **Migration:** `npx vp migrate --no-hooks` from `dashboard/`, then review every change it makes. Expected result:

  ```ts
  // vite.config.ts
  import react from "@vitejs/plugin-react";
  import { defineConfig } from "vite-plus";

  export default defineConfig({
    plugins: [react()],
    server: { port: 5173 },
    // type checking through tsgolint replaces tsc --noEmit
    lint: { options: { typeAware: true, typeCheck: true } },
  });
  ```

  Scripts become `dev: vp dev`, `build: vp build`, `preview: vp preview`, plus a new `check: vp check`. `build` stops type checking; `check` does it instead, and CI runs both.
- **Formatting:** oxfmt's defaults (Prettier-compatible) match the current code: 2 spaces, double quotes, semicolons. No `fmt` options unless the migration's reformat shows a difference.
- **Tests:** none yet. Vitest is there for the first component with real logic (`vp test`).
- **`typescript` stays a dev dependency**, for the editor's TypeScript service.
- **The Dockerfile stays unchanged:** its `npm run build` and `npm run dev -- --host 0.0.0.0` now call `vp`.

### `android/`: ktlint

- `gradle/libs.versions.toml`: `ktlint = "14.2.0"` under `[versions]` and `ktlint = { id = "org.jlleitschuh.gradle.ktlint", version.ref = "ktlint" }` under `[plugins]`.
- Root `build.gradle.kts`: `alias(libs.plugins.ktlint) apply false`. `:app`, `:wear` and `:shared` each add `alias(libs.plugins.ktlint)` to their `plugins {}` block, as with the other plugins.
- The plugin version fixes the ktlint version, so laptops and CI format the same way.
- A new `android/.editorconfig`:

  ```editorconfig
  root = true

  [*.{kt,kts}]
  # Android Studio's own formatter agrees with this style, so Reformat Code and the hook do not fight
  ktlint_code_style = android_studio
  # Compose functions are PascalCase
  ktlint_function_naming_ignore_when_annotated_with = Composable
  ```

`ktlintFormat` cannot take a list of files, so it formats the whole Android project. `stage_fixed` restages only the files that were staged; any other file it reformats stays as an unstaged change in the working tree.

### CI

| Workflow | Change |
|---|---|
| `dashboard.yml` | `npm ci`, then **`npx vp check`**, then `npm run build`. It keeps `actions/setup-node`; `vp` comes from the dashboard's own dependencies, so `voidzero-dev/setup-vp` is not needed |
| `android.yml` | `./gradlew` **`ktlintCheck`** `lint testDebugUnitTest` **`:shared:test`** `assembleDebug` |
| `backend.yml` | unchanged |

**`:shared:test` closes a gap in ADR-001 §2.5.** That section, and the comment in `android.yml`, say the `:shared` unit tests run on every Android pull request. They do not: `:shared` is a plain Kotlin module, whose task is `test`, and `testDebugUnitTest` exists only in the Android modules. It is harmless today, because `:shared` has no tests yet, but it would hide the watch threshold tests 06 §5 asks for.

CI does not run lefthook. It runs the tools directly.

### Who owns the git hooks

Git reads hooks from one directory: `.git/hooks/`, or `core.hooksPath` when it is set. Vite+ ships its own hook manager: `vp config` and `vp hooks enable` set `core.hooksPath` to `.vite-hooks/`. From then on, git stops reading `.git/hooks/`, and lefthook's hooks stop running without any error.

**Lefthook owns the hooks for the whole repository**, since it also serves Python and Kotlin. So:
- the migration runs with `--no-hooks`, and no `.vite-hooks/` folder is committed;
- `package.json` has no `prepare` or `postinstall` script that runs `vp config`;
- `dashboard/AGENTS.md` says that `vp config` is only run with `--no-hooks`, and how to undo it otherwise: `vp hooks disable`, then `lefthook install`.

`vp staged` (lint-staged inside Vite+) is not used either. It would add a second layer that stashes and restages files inside lefthook's.

### Escape hatches and editors

- `git commit --no-verify` or `LEFTHOOK=0 git commit` skips the hooks. CI still checks the change.
- **Git GUIs** (Android Studio's commit dialog, VS Code) may start hooks without `/opt/homebrew/bin` on the `PATH`, so `uv` and `npx` are not found. Each developer who hits this adds a `lefthook-local.yml`, which `.gitignore` excludes:

  ```yaml
  # lefthook-local.yml, not committed
  rc: ~/.lefthookrc # a shell file with: export PATH="/opt/homebrew/bin:$PATH"
  ```

- A clone without `lefthook install` runs no hooks. CI catches what it misses.
- `min_version` stops an older lefthook with a message to upgrade.

## Options considered

### Hook manager

| Option | Assessment |
|---|---|
| **Lefthook (chosen)** | One Go binary from Homebrew, no runtime. One YAML file. `root`, `glob` and `{staged_files}` map onto one folder per toolchain. Runs folders in parallel. Restages fixed files |
| pre-commit (the Python framework) | Installs each tool into its own environment, apart from `uv.lock`, `package-lock.json` and `libs.versions.toml`, so the hook's ruff can differ from CI's. Gradle has no first-class support |
| Husky with lint-staged | Needs a root `package.json` (force 6) |
| Vite+'s own hooks (`vp staged`) | The hook manager for the whole repository would live inside `dashboard/` and be installed by its `npm ci`. Backend and Android developers would need the dashboard's dependencies to commit |
| No hooks, CI only | Today's setup. Feedback comes minutes later and a red build holds back deploys (force 1) |

### Where the slow checks run

| Option | Assessment |
|---|---|
| **Fast checks on commit, Gradle on push (chosen)** | Every commit takes about 1–3 s. Android breakage is still caught before it reaches GitHub |
| Everything on commit | Every Android commit waits for Gradle lint and unit tests |
| Everything on commit except Android lint, which stays CI-only | The slowest step is skipped, but unit tests still run on every commit, and lint errors surface only on GitHub |

### Dashboard tools

| Option | Assessment |
|---|---|
| **Vite+ (chosen)** | One dependency for formatting, lint, type checks, tests and the build. Type-aware lint rules (such as unhandled promises) work on TypeScript 7 through tsgolint. Replaces the `vite` package with Vite+'s own build of it, so the React plugin's `vite ^8` requirement must still resolve (risk 1) |
| Biome | One dependency for formatting and lint, independent of the TypeScript compiler. Its few type-aware rules rely on Biome's own partial type inference, and it does not type check, so `tsc --noEmit` stays a separate step |
| ESLint with Prettier | The most common choice, with the React hooks rules. typescript-eslint does not support TypeScript 7 (force 4) |

### Kotlin formatting

| Option | Assessment |
|---|---|
| **ktlint through its Gradle plugin (chosen)** | Version pinned in `libs.versions.toml`, as `android/AGENTS.md` requires, so laptops and CI agree. Formats the whole project, in 1–3 s with a warm daemon |
| ktlint from Homebrew | About 1 s on the staged files only. The version is per machine, so laptops and CI can disagree on formatting |
| Check on push only | Instant commits, but every formatting fix needs one more commit |

### Hook file layout

| Option | Assessment |
|---|---|
| **One root `lefthook.yml` (chosen)** | Every hook in one file, outside every Railway watch path, so changing a hook never redeploys anything |
| A root file that pulls in one `lefthook.yml` per folder | Each folder owns its hooks, but changing the backend's redeploys `api` and drops live calls (force 5) |
| Hooks that call a `check` script in each folder, shared with CI | Laptops and CI cannot drift. The scripts work on whole folders, not on staged files |

## Consequences

**Easier**
- Formatting, lint and test failures show up at commit or push time, before Wait for CI can hold back a deploy.
- Formatting is never discussed in review: the hooks and CI apply one style per folder.
- The dashboard gets a linter with type-aware rules on TypeScript 7, and a test runner ready for its first test.
- `:shared`'s tests run in CI from the first one written.

**Harder**
- Each clone needs `brew install lefthook && lefthook install`. A clone without it runs no hooks, and CI is the only check.
- Vite+ replaces the `vite` package. A Vite plugin that checks Vite's version can fail to install until Vite+ supports it.
- Two hook managers are within reach. Anyone who runs `vp config` without `--no-hooks` silently turns lefthook's hooks off.
- Android commits pay Gradle's start-up, about 13 s when no daemon is running.

**To revisit**
- `pytest` on commit, once tests need the `sentinela_test` database. The hook would fail whenever Compose is not running; move those tests to pre-push or mark them.
- Passing `{staged_files}` to `vp check`, if the dashboard grows enough to make whole-project checks slow.
- A type checker for the backend (mypy, pyright or ty). There is none today, and this ADR does not add one.
- Formatting `.railway/railway.ts`, if it starts changing often.

## Action items

Three commits, in this order: the tools first, so the first hook run meets formatted code. They touch separate folders, so they can also be three pull requests, with the hooks last (ADR-001 §2.4).

1. [ ] **Dashboard on Vite+.** `npx vp migrate --no-hooks` and the config above; `dashboard.yml`; `dashboard/AGENTS.md` (commands, the hooks rule; drop "no linter or test runner yet"); the migration's reformat. Check, and stop to report if any of these fails without a clean fix:
   1. `npm ci` resolves `@vitejs/plugin-react`'s `vite ^8` requirement against Vite+'s `vite` package;
   2. `npx vp check` and `npm run build` pass;
   3. `docker build dashboard` succeeds: the image is Alpine (musl) and needs Vite+'s native binaries for it;
   4. `docker compose up --watch dashboard` serves on `localhost:5173`, with `--host 0.0.0.0` passed through to `vp dev`.
2. [ ] **ktlint for Android.** The plugin, `android/.editorconfig`, `ktlintFormat` over the existing `.kt` files, `android.yml`, `android/AGENTS.md`. Check: `./gradlew ktlintCheck lint testDebugUnitTest :shared:test assembleDebug` passes locally. Then check that `lint` and the unit tests also pass without the signing key in `local.properties`, which decides whether pre-push needs it.
3. [ ] **Lefthook.** `lefthook.yml`; `lefthook-local.yml` in `.gitignore`; lefthook in the README's Tools table and `lefthook install` in its setup steps; root `AGENTS.md` (layout, commands, the hooks rule). Check with commits in a throwaway worktree:
   - a misformatted `.py`, `.tsx` and `.kt` file are each fixed and restaged;
   - a type error in `dashboard/` and a failing test in `backend/` each block the commit;
   - a backend-only commit never starts Gradle;
   - a docs-only commit runs nothing;
   - a partially staged file keeps its unstaged changes;
   - a push of an `android/` change runs the Gradle checks, and a push without one does not.
4. [ ] Update ADR-001 §2.5's Android CI command to match `android.yml`.
5. [ ] Each team member: `brew install lefthook`, then `lefthook install` in their clone.
