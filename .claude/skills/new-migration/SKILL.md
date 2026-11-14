---
name: new-migration
description: Write an Alembic migration for a models.py change: autogenerate locally, keep it additive, update 05-data-model.md, prove the round trip.
disable-model-invocation: true
argument-hint: "<what the migration does, e.g. calls dialed_at>"
---

# New migration

The migration for: $ARGUMENTS

Old and new API copies share one schema during a deploy, so a migration only **adds** (backend/AGENTS.md "Migrations only add"). A migration already on `main` is frozen: staging has applied it, and the `frozen-migration.sh` hook refuses edits to it.

## Steps

1. **Model.** Change the owning package's `models.py` (ADR-005: only the owner writes a table). A new column is `nullable=True` or carries a `server_default`. Done when the model matches what the migration should create.
2. **Generate,** from the repo root with Compose up: `docker compose exec api alembic revision --autogenerate -m "<what>"`. `alembic/` is bind-mounted, so the file lands in `backend/alembic/versions/`.
3. **Review the generated file** line by line against the table below. Rewrite the docstring's first line as `<table>.<column>` or a short phrase, and add one or two lines on why it exists, as in `c7a4e2f95d18_calls_dialed_at.py`. Done when every `op.` call in `upgrade()` is additive and `downgrade()` undoes exactly those calls.
4. **Spec.** Update [05-data-model.md](../../../docs/specs/echocare/05-data-model.md): the entity in §1, a constraint in §3, a note in §4 if the choice is not obvious.
5. **Apply and test.** `docker compose exec api alembic upgrade head`, then `uv run pytest` in `backend/`. The test session runs `downgrade base` then `upgrade head` on `echocare_test` (`tests/conftest.py`), so a green run proves the round trip.
6. **Report** the revision id, its `down_revision`, each `op.` call, and the test result.

## Review table

| In `upgrade()` | Verdict |
|---|---|
| `add_column` nullable or with `server_default` | Keep |
| `create_table`, `create_index`, a new constraint the existing rows already satisfy | Keep |
| `add_column` with `nullable=False` and no default | Fix: add a `server_default` or make it nullable |
| `drop_column`, `drop_table`, `alter_column` rename or type change | Stop and ask the user: it needs an expand-then-contract over two deploys |
| An `op.` call for a table the model change did not touch | Autogenerate drift: remove it, and tell the user |

Run Alembic only against the local Compose database. `alembic/env.py` refuses any other host, by design.
