# .railway: Railway infrastructure as code

[railway.ts](railway.ts) declares the whole Railway project, `Sentinela`, for both environments: the `Sentinela API` and `DAS Dashboard` services, the `Postgres` database, the S3-compatible `Storage` bucket, and every setting and variable. That covers the GitHub source and branch, root directory, watch paths, Dockerfile builder, Wait for CI, migrations before deploy, health check, draining and variables.

| Environment | Deploys from | Used by |
|---|---|---|
| `staging` | `main` | The team, Android debug builds |
| `production` | `release` | The demo, Android release builds |

**Railway never reads this folder during a deploy.** Deploys happen when commits reach the branch. This file changes the *settings*, and a person applies it. A change merged to `main` does nothing on Railway until someone applies it to each environment.

## Set up once

```bash
railway login
```

From `.railway/`, link the folder to the project. Pick the workspace, `Sentinela` and an environment when asked:

```bash
railway link
```

```bash
npm ci
```

## Preview and apply

From `.railway/`. Always name the environment: without `--environment`, these commands target whichever environment the folder is linked to. They have no `-e` short flag.

```bash
railway config plan --environment staging
```

Read the plan, then:

```bash
railway config apply --environment staging
```

Before applying, check the plan for:
- **`to destroy`.** A resource missing from the file is deleted, the Postgres volume included. Apply refuses destructive changes unless you confirm them.
- **Variables being removed.** The file manages variables (`variables: managed`), so apply deletes any variable it does not declare.

Values are hidden in the plan; add `--show-values` to see them.

## Secrets

Secrets are never written into `railway.ts`. Set the value in Railway once per environment (`--stdin` keeps it out of shell history):

```bash
railway variable set TWILIO_AUTH_TOKEN --stdin -s api -e staging
```

Then declare it in `railway.ts`, so apply keeps it:

```ts
TWILIO_AUTH_TOKEN: preserve(),
```

The Firebase web config is not a secret. It ships in the browser bundle, so it is written into `railway.ts` as plain values.

## Things the file does not do

**Public domains.** Generate one per service and environment:

```bash
railway domain -s api -e staging
```

```bash
railway domain -s dashboard -e staging
```

Then add the dashboard's domain to Firebase → Authentication → Settings → Authorized domains.

**Creating environments.** Create one with the command below. Its branch also needs an entry in `BRANCH` in `railway.ts`; the file refuses environments it does not know.

```bash
railway environment new production
```

**Wait for CI.** It appears in the Railway UI (service → Settings → Source) only after the branch has a GitHub workflow that runs `on: push`. If `plan` keeps showing `source.checkSuites (null → true)` after an apply, check the toggle there.

## Why TypeScript

Railway deprecated `railway.toml`: new services cannot use it, and existing files stop being read on 2026-12-01. Its replacement can be written in TypeScript, which is generally available, or in Python or Go, which are in beta. This folder has its own `package.json`, so the SDK never touches `dashboard/package-lock.json`, where a change would redeploy the dashboard. See [ADR-001](../docs/adr/ADR-001-monorepo-and-delivery.md).
