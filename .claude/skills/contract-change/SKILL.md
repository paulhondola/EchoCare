---
name: contract-change
description: Use when adding or changing an API endpoint, or a request or response field, so 04-interfaces.md, the backend and both clients change together.
---

# Contract change

An endpoint is one contract across four places: the spec row, the backend, the Android app, the dashboard (AGENTS.md "Contract changes move together"). This change lands as one PR across components on purpose (ADR-001 §2.4). Installed APKs lag the API, so every change is **additive** (ADR-001 §2.3).

## Steps

1. **Spec first.** Find the endpoint's row in [04-interfaces.md](../../../docs/specs/echocare/04-interfaces.md): §1 reads, §2 commands, §3 the phone app. Edit the row, or add one. A new refusal reason also goes in §0 "Refusals". Done when the row says exactly what the code will do.
2. **Backend.** In `backend/app/<package>/`: the body or response in `schemas.py` (`Form` for a body; `View`, `Summary` or `Detail` for a response), the rule in `service.py`, the plumbing in `router.py`. Add a test in `backend/tests/<package>/`. Done when `uv run ruff check . && uv run lint-imports && uv run pytest` passes in `backend/`.
3. **Find every caller.** Search for the path in `android/app/src/main/java/` and `dashboard/src/`. Done when you hold a list of every call site, or have confirmed there are none.
4. **Android.** `android/app/src/main/java/ro/echocare/Api.kt`: a new response field gets a default, so a response from an older API copy still decodes. A field holding a growing enumeration (trigger, outcome, push `type`, status) decodes as a `String` with a fallback. Done when `./gradlew ktlintCheck testDebugUnitTest` passes in `android/`.
5. **Dashboard.** The types in `dashboard/src/services/api.ts` and every caller from step 3. Done when `npm run check` passes in `dashboard/`.
6. **Report** the spec row, each file changed and each check's result. If a client needs no change, name it and say why.

## Additive means

| Change | Allowed |
|---|---|
| New response field | Yes. Old clients ignore it (`ignoreUnknownKeys = true` in `Modules.kt`) |
| New request field | Only optional, with a server-side default |
| New enum value | Yes. Clients already fall back on unknown values |
| New endpoint | Yes |
| Rename, drop, retype a field; make an optional field required | No. Add the new field beside the old one; the old one leaves only after every device has updated |
