# AGENTS.md: .railway

Railway infrastructure as code. [railway.ts](railway.ts) declares the whole `Sentinela` project for both environments: the `api` and `dashboard` services, `Postgres`, and every setting and variable. Details: [README.md](README.md).

## Layout

```
.railway/
├── railway.ts         the project: services, sources, watch paths, health checks, variables
├── package.json       its own, so the SDK never touches dashboard/package-lock.json
└── package-lock.json
```

| Environment | Deploys from |
|---|---|
| `staging` | `main` |
| `production` | `release` |

## Scope

- Railway settings only. Railway never reads this folder during a deploy; a person applies it. A merged change does nothing until someone applies it to each environment.
- Not here: public domains, creating environments, the Wait for CI toggle. See the README.

## Commands

From `.railway/`. Read-only commands are safe; everything else changes live infrastructure.

| Task | Command | Safe for an agent |
|---|---|---|
| Install the SDK | `npm ci` | Yes |
| Preview changes | `railway config plan --environment staging` | Yes, read-only |
| Apply changes | `railway config apply --environment staging` | Only when the user asks, after they have read the plan |
| Logs | `railway logs -s api -e staging` | Yes |
| Set a secret | `railway variable set NAME --stdin -s api -e staging` | No: the user does it |

Always pass `--environment` to `config plan` and `config apply`; without it they target whichever environment the folder is linked to. They have no `-e` short flag.

## Rules

- **Read the plan before any apply**, and stop if it shows `to destroy` (a missing resource is deleted, the Postgres volume included) or variables being removed (`variables: managed` deletes undeclared ones).
- **Secrets never go in `railway.ts`.** Set them in Railway, then declare them with `preserve()` so apply keeps them.
- **A new environment needs an entry in `BRANCH`**; the file throws for environments it does not know.
- **Watch paths matter.** `api` watches `/backend/**` and `dashboard` watches `/dashboard/**`. Widening them makes unrelated changes redeploy the API and drop live calls.
