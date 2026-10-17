# Campaigns and mock calls Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the campaign endpoints, a shared step that turns a call's answers into a code and an incident, a mock call answered from the senior's Android app (campaign and welcome), code chips in both clients and a „Campanii” page on the dashboard, so the whole wellbeing workflow runs without Twilio.

**Architecture:** A new feature package `app/campaigns/` owns starting, listing and ending campaigns and the lazy cancel of lapsed ones. `app/calls/` gains `ending.py` (the shared ending step, reused later by the Twilio relay through `voice/router.py`) and `mock.py` (the card's read and answer). Seniors gain code fields and two hooks so accept and withdrawal can queue or cancel calls in their own transaction without `seniors` importing `voice`. The dashboard and Android only read and post through the new endpoints.

**Tech Stack:** Python 3.14, FastAPI, SQLAlchemy 2 async with asyncpg, Postgres 18, pytest with httpx `AsyncClient`; Svelte 5 and SvelteKit 3 with Vite+; Kotlin, Compose, Retrofit, kotlinx.serialization and JUnit.

**Spec:** [docs/superpowers/specs/2026-10-17-campaigns-and-mock-calls-design.md](../specs/2026-10-17-campaigns-and-mock-calls-design.md). Read it before Task 1. §4 is the contract and §5 the ending step; every status code, reason and Romanian string below comes from there or from this plan.

## Global Constraints

- All tasks go on branch `campaigns`, which already holds the design commit. Don't push and don't open PRs.
- Backend commands from `backend/`, with Postgres up (`docker compose up -d db` from the repository root). Dashboard commands from `dashboard/`, Android from `android/`.
- `backend/AGENTS.md` applies: import a name from the module that defines it; no imports inside functions; `__init__.py` files stay empty; ORM in `models.py`, Pydantic in `schemas.py` with bodies ending in `Form` and responses in `View`, `Summary` or `Detail`; `schemas.py` imports only enums from models. `uv run lint-imports` passes **without changing a contract**. If it can't, stop and report.
- A refusal is `raise refuse(status, reason, **extra)` from `app.auth.service`, logged first with `log.info("refused <reason>: user %s, …", …)`.
- No migration. `tests/core/test_models.py::test_models_match_the_migration` (`alembic check`) keeps passing.
- API changes only add: new response fields have defaults; nothing renamed or dropped (ADR-001 §2.3).
- Comments are English and cite the spec by ID (`04 §2`, `03 §9`, `Q14`, `design §5`). Every user-facing string on the dashboard, in Android and in the call transcripts is Romanian, exactly as written in this plan.
- Test module basenames are unique across `backend/tests/`, since pytest runs without `__init__.py`. `tests/voice/test_calls.py` and `tests/calls/test_call_history.py` already exist. New: `tests/campaigns/test_campaigns.py`, `tests/calls/test_ending.py`, `tests/calls/test_mock_calls.py`.
- Commit with the hooks on: lefthook runs each folder's checks. Never `--no-verify` or `LEFTHOOK=0`. End every commit message with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The mock endpoints refuse when `get_settings().app_env is AppEnv.production` (404 `not_found`). Tests patch `get_settings` in the module that calls it.

## Review Focus

1. **DAS double-clicks „Lansează”**, so two `POST /campaigns` arrive at once. One campaign is created; one answer is 201 and the other 200 with the same id. *Test in Task 2.*
2. **The senior taps „Trimite” twice.** The second `POST /calls/{id}/mock-answer` is 409 `already_done`, and the call has one set of answers and one status report. *Test in Task 6.*
3. **A redial that isn't due yet.** `GET /profile/mock-call` answers 204, and posting an answer to it is 409 `wrong_state`. *Test in Task 6.*
4. **A landline senior in a campaign.** They have no app, so they count as `waiting` until „Încheie”, which counts them as `canceled`. *Test in Task 3.*
5. **A campaign with no active seniors**, which is staging today. 201, `progress.total` 0, nothing queued. *Test in Task 2.*

---

### Task 1: Enum members, consent texts, test fixture, seed warning

**Files:**
- Modify: `backend/app/voice/calls.py`, `backend/app/seniors/models.py`, `backend/app/voice/dialogue.py`, `backend/scripts/seed.py`, `backend/tests/conftest.py`
- Test: `backend/tests/voice/test_calls.py` (append)

**Interfaces:**
- Produces:
  - `CallState.canceled = "canceled"`. `TRANSITIONS[CallState.queued]` becomes `{ringing, failed, canceled}`, and `TRANSITIONS[CallState.canceled] = frozenset()`. `ENDED` picks it up on its own.
  - `ConsentMethod.app = "app"`, a consent given or refused on the mock card (design §4.4).
  - In `app/voice/dialogue.py`: `CONSENT_VERSION = "v1"` and `CONSENT_TEXT`, moved verbatim from `scripts/seed.py`. `CARD_CONSENT_VERSION = "v1-app"` and `CARD_CONSENT_TEXT`, exactly:
    `"Vă vom suna în zilele cu vreme extremă sau când ceasul semnalează ceva neobișnuit. Ce spuneți în apel văd medicul de familie, familia și DAS. Puteți renunța oricând. Sunteți de acord?"`
  - In `tests/conftest.py`: a fixture `add_active_senior` with `async def add(phone: str, *, landline: bool = False, medic: User | None = None) -> Senior`. It makes an `active` senior through `add_senior`, plus a `senior` grant for a mobile number. `add_senior` must accept `phone_is_landline` in `**columns`: change its `Senior(…)` call to `**{"phone_is_landline": False, **columns}`.

- [ ] **Step 1: Write the failing test** (append to `tests/voice/test_calls.py`)

```python
def test_a_queued_call_can_be_canceled_and_stays_canceled():
    assert advance(CallState.queued, CallState.canceled) is CallState.canceled
    assert CallState.canceled in ENDED
    assert not was_answered(CallState.canceled)
    assert not reachable(CallState.ringing, CallState.canceled)  # only from queued (03 §9)
```

- [ ] **Step 2: Run it and see it fail**

Run: `uv run pytest tests/voice/test_calls.py -q`
Expected: the new test FAILS with `AttributeError: canceled`.

- [ ] **Step 3: Add the enum members and the texts**

`seed.py` imports `CONSENT_TEXT` and `CONSENT_VERSION` from `app.voice.dialogue` and deletes its own copies. The seed's campaign gets `warning_until=h.ago(125) + timedelta(hours=24)` (Q4), replacing the "tomorrow at 20:00" expression.

- [ ] **Step 4: Run the backend suite**

Run: `uv run pytest -q && uv run lint-imports`
Expected: all PASS, `tests/tooling/test_scripts.py` included.

- [ ] **Step 5: Commit**

```bash
git add backend/app/voice backend/app/seniors/models.py backend/scripts/seed.py backend/tests
git commit -m "feat(voice): canceled calls, the app consent method and the card's consent text"
```

---

### Task 2: Start and list campaigns

**Files:**
- Create: `backend/app/campaigns/__init__.py` (empty), `backend/app/campaigns/schemas.py`, `backend/app/campaigns/service.py`, `backend/app/campaigns/router.py`
- Modify: `backend/app/main.py` (mount the router after `incidents_router`)
- Test: `backend/tests/campaigns/test_campaigns.py`

**Interfaces:**
- Consumes: `add_active_senior` (Task 1).
- Produces:
  - `class CampaignForm(BaseModel)`: `kind: CampaignKind`, `level: WarningLevel`.
  - `class CampaignProgress(BaseModel)`: `total`, `waiting`, `green`, `yellow`, `red`, `canceled`, all `int`.
  - `class CampaignSummary(BaseModel)`: `id: uuid.UUID`, `kind: str`, `level: str`, `started_by_name: str`, `started_at: datetime`, `warning_until: datetime`, `active: bool`, `progress: CampaignProgress`.
  - In `campaigns/service.py`: `WARNING = timedelta(hours=24)`, and `CAMPAIGN_LOCK = 20261017`, distinct from `staff.service.STAFF_LOCK`.
  - `async def campaign_summaries(session: AsyncSession, campaign_id: uuid.UUID | None = None) -> list[CampaignSummary]`: newest first (`started_at` desc, then `id`), optionally one campaign.
  - `async def start_campaign(session: AsyncSession, caller: Caller, form: CampaignForm) -> tuple[CampaignSummary, bool]`, where the bool means "created".

- [ ] **Step 1: Write the failing tests** (`tests/campaigns/test_campaigns.py`)

```python
DAS, MEDIC = "+40700000001", "+40700000002"

def signed_in(token): return {"Authorization": f"Bearer {token}"}

async def start(client, kind="cold", level="yellow", token=DAS):
    return await client.post("/api/campaigns", json={"kind": kind, "level": level}, headers=signed_in(token))

@pytest.fixture
async def das(add_user): return await add_user(DAS, Role.das, name="DAS Test")

async def test_a_campaign_queues_one_call_per_active_senior(client, db, das, add_active_senior, add_senior):
    maria = await add_active_senior("+40700000101")
    await add_senior("+40700000102", enrollment_state=EnrollmentState.accepted)   # not active
    busy = await add_active_senior("+40700000103")
    db.add(Incident(senior_id=busy.id, reason="Căzătură"))                       # unresolved
    await db.commit()
    r = await start(client)
    assert r.status_code == 201
    body = r.json()
    assert (body["kind"], body["level"], body["started_by_name"], body["active"]) == ("cold", "yellow", "DAS Test", True)
    assert body["progress"] == {"total": 1, "waiting": 1, "green": 0, "yellow": 0, "red": 0, "canceled": 0}
    started, until = (datetime.fromisoformat(body[k]) for k in ("started_at", "warning_until"))
    assert until - started == timedelta(hours=24)                                 # Q4
    calls = (await db.scalars(select(Call))).all()
    assert [(c.senior_id, c.trigger, c.attempt, c.starting_severity, c.state) for c in calls] == [
        (maria.id, CallTrigger.campaign, 1, Severity.green, CallState.queued)]

async def test_a_senior_with_a_live_call_is_skipped(client, db, das, add_active_senior):
    maria = await add_active_senior("+40700000101")
    db.add(Call(senior_id=maria.id, trigger=CallTrigger.test, starting_severity=Severity.green, due_at=datetime.now(UTC)))
    await db.commit()
    assert (await start(client)).json()["progress"]["total"] == 0

async def test_the_same_kind_and_level_answers_the_running_campaign(client, das, add_active_senior):   # Q3
    await add_active_senior("+40700000101")
    first = (await start(client)).json()
    again = await start(client)
    assert (again.status_code, again.json()["id"]) == (200, first["id"])
    other = await start(client, level="red")
    assert other.status_code == 201 and other.json()["id"] != first["id"]
    assert other.json()["progress"]["total"] == 0          # Maria's call is the first campaign's

async def test_two_presses_at_once_make_one_campaign(client, db, das):                # Review Focus 1
    a, b = await asyncio.gather(start(client), start(client))
    assert sorted([a.status_code, b.status_code]) == [200, 201]
    assert a.json()["id"] == b.json()["id"]
    assert await db.scalar(select(func.count()).select_from(Campaign)) == 1

async def test_no_active_seniors_is_still_a_campaign(client, das):                     # Review Focus 5
    r = await start(client)
    assert (r.status_code, r.json()["progress"]["total"]) == (201, 0)

async def test_the_list_is_newest_first(client, das):
    await start(client, "cold"); await start(client, "heat")
    r = await client.get("/api/campaigns", headers=signed_in(DAS))
    assert [c["kind"] for c in r.json()] == ["heat", "cold"]

@pytest.mark.parametrize("token,status", [(MEDIC, 403), ("+40700000009", 403), ("invalid", 401)])
async def test_only_das_starts_or_lists(client, das, add_user, token, status):
    await add_user(MEDIC, Role.medic)
    assert (await start(client, token=token)).status_code == status
    assert (await client.get("/api/campaigns", headers=signed_in(token))).status_code == status

async def test_a_bad_body_is_422(client, das):
    assert (await start(client, kind="rain")).status_code == 422
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/campaigns -q`
Expected: FAIL with 404 for `/api/campaigns`.

- [ ] **Step 3: Implement the package**

- `start_campaign`, in one transaction: take `pg_advisory_xact_lock(CAMPAIGN_LOCK)`. If a campaign with the same `kind` and `level` has `warning_until > now`, return it with `False`. Otherwise insert the `Campaign`, with `started_at = now` and `warning_until = now + WARNING`, both from one `now = datetime.now(UTC)`. Then queue with one `insert(Call).from_select(…)` over `Senior` where `enrollment_state == active` and no `Incident` in `UNRESOLVED` exists for the senior. The values: `trigger=campaign`, `campaign_id`, `attempt=1`, `starting_severity=green`, `state=queued`, `due_at=now`. End it with `.on_conflict_do_nothing()`, so `uq_calls_live_senior` skips a senior with a live call. Commit, and return `(summary, True)`.
- `progress` counts each senior once, by their latest attempt in the campaign: `DISTINCT ON (campaign_id, senior_id) … ORDER BY campaign_id, senior_id, attempt DESC, created_at DESC`, grouped in Python. `queued` counts as `waiting`, `canceled` as `canceled`, and an ended call by its `final_severity` name. Design §4.1 has the table.
- `started_by_name` comes from a join to `User`. `active` is `warning_until > now`.
- Router: `POST /campaigns` with `require_roles(Role.das)` and `status_code=201`. The handler takes `response: Response` and sets `response.status_code = 200` when not created. Declare `responses={200: {"model": CampaignSummary, "description": "The running campaign of that kind and level (Q3)"}}`. `GET /campaigns` with `require_roles(Role.das)`. Docstrings cite `04 §2`, Q2 and Q3.

- [ ] **Step 4: Run the tests and the contracts**

Run: `uv run pytest tests/campaigns -q && uv run lint-imports`
Expected: all PASS; the contracts are KEPT unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/campaigns backend/app/main.py backend/tests/campaigns
git commit -m "feat(campaigns): POST and GET /campaigns, one round of queued calls (UC-05)"
```

---

### Task 3: End a campaign, lapsed warnings, `warning_active`

**Files:**
- Modify: `backend/app/campaigns/service.py`, `backend/app/campaigns/router.py`, `backend/app/auth/schemas.py`, `backend/app/auth/router.py`
- Test: `backend/tests/campaigns/test_campaigns.py` (append), `backend/tests/auth/test_profile.py` (append)

**Interfaces:**
- Consumes: `campaign_summaries`, `start_campaign` (Task 2).
- Produces:
  - `async def cancel_lapsed(session: AsyncSession) -> None`: one `UPDATE calls SET state='canceled', ended_at=now`. It hits `queued` calls whose campaign has `warning_until <= now`. It doesn't commit; the caller's transaction does.
  - `async def end_campaign(session: AsyncSession, campaign_id: uuid.UUID) -> CampaignSummary`: `warning_until = least(warning_until, now)`, then cancels that campaign's `queued` calls, redials included. Commits. An unknown id is `refuse(404, "not_found")`.
  - `async def warning_active(session: AsyncSession) -> bool`.
  - `ProfileView.warning_active: bool = False`.

- [ ] **Step 1: Write the failing tests**

```python
async def end(client, campaign_id, token=DAS):
    return await client.post(f"/api/campaigns/{campaign_id}/end", headers=signed_in(token))

async def test_ending_cancels_waiting_calls_and_keeps_codes(client, db, das, add_active_senior):
    maria = await add_active_senior("+40700000101")
    db.add(SeniorStatus(senior_id=maria.id, code=Severity.yellow, reason="x", since=datetime.now(UTC)))
    await db.commit()
    c = (await start(client)).json()
    r = await end(client, c["id"])
    assert r.status_code == 200
    assert (r.json()["active"], r.json()["progress"]["canceled"], r.json()["progress"]["waiting"]) == (False, 1, 0)
    assert (await db.scalar(select(Call.state))) is CallState.canceled
    assert (await db.get(SeniorStatus, maria.id, populate_existing=True)).code is Severity.yellow
    assert (await end(client, c["id"])).json() == r.json()        # a repeat changes nothing
    assert (await start(client)).status_code == 201               # a new one may start (Q9)

async def test_a_landline_senior_waits_until_the_end(client, das, add_active_senior):  # Review Focus 4
    await add_active_senior("+40256123456", landline=True)
    c = (await start(client)).json()
    assert c["progress"]["waiting"] == 1
    assert (await end(client, c["id"])).json()["progress"]["canceled"] == 1

async def test_ending_a_lapsed_campaign_keeps_its_end(client, db, das):
    c = (await start(client)).json()
    past = datetime.now(UTC) - timedelta(hours=1)
    await db.execute(update(Campaign).values(warning_until=past)); await db.commit()
    assert datetime.fromisoformat((await end(client, c["id"])).json()["warning_until"]) == past

async def test_a_lapsed_warning_frees_its_seniors(client, db, das, add_active_senior):
    await add_active_senior("+40700000101")
    await start(client)
    await db.execute(update(Campaign).values(warning_until=datetime.now(UTC) - timedelta(seconds=1)))
    await db.commit()
    listed = (await client.get("/api/campaigns", headers=signed_in(DAS))).json()
    assert listed[0]["progress"]["canceled"] == 1
    assert (await start(client)).json()["progress"]["total"] == 1   # queued again

async def test_ending_an_unknown_campaign_is_404(client, das):
    assert (await end(client, uuid.uuid4())).json() == {"detail": {"reason": "not_found"}}
```

Append to `tests/auth/test_profile.py`. The test checks `warning_active` is false with no campaign, true after a DAS user posts one, and false again after `POST /campaigns/{id}/end`. Also assert `warning_active` is present on the profile of a caregiver.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/campaigns tests/auth/test_profile.py -q`
Expected: the new tests FAIL (405 for `/end`, a `KeyError` for `warning_active`).

- [ ] **Step 3: Implement**

`POST /campaigns`, `GET /campaigns` call `await cancel_lapsed(session)` first; `GET` commits after it. Route `POST /campaigns/{campaign_id}/end`, `require_roles(Role.das)`, docstring citing Q9. `auth/router.py`'s `profile` passes `warning_active=await warning_active(session)`. The router may import `app.campaigns.service`; `auth/service.py` must not.

- [ ] **Step 4: Run the tests and the contracts**

Run: `uv run pytest tests/campaigns tests/auth -q && uv run lint-imports`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/campaigns backend/app/auth backend/tests
git commit -m "feat(campaigns): end a campaign, lapsed warnings cancel, warning_active (Q5, Q9)"
```

---

### Task 4: Codes on the seniors rows

**Files:**
- Modify: `backend/app/seniors/schemas.py`, `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/seniors/test_seniors.py` (append)

**Interfaces:**
- Produces:
  - `Code = Annotated[str, BeforeValidator(lambda v: getattr(v, "name", v))]` in `seniors/schemas.py`. `Severity` is an `IntEnum` and would otherwise serialize as `0`.
  - `SeniorSummary` and `SeniorView` each gain `code: Code | None = None`, `reason: str | None = None`, `since: datetime | None = None`. Not `SeniorDetail`, which `IncidentDetail` embeds.
  - `async def senior_summaries(session: AsyncSession, caller: Caller, role: Role | None) -> list[SeniorSummary]`: `seniors_query`'s rows with an outer join to `SeniorStatus` on `senior_id == Senior.id` **and** `Senior.enrollment_state == active`.
  - `senior_view` fills the same three fields the same way.

- [ ] **Step 1: Write the failing tests**

```python
async def test_the_code_shows_for_an_active_senior_only(client, db, add_user, add_active_senior):
    await add_user("+40700000001", Role.das)
    maria = await add_active_senior("+40700000101")
    ion = await add_active_senior("+40700000102")
    now = datetime.now(UTC)
    db.add_all([SeniorStatus(senior_id=s.id, code=Severity.yellow, reason="Nu are căldură în casă", since=now) for s in (maria, ion)])
    ion.enrollment_state = EnrollmentState.withdrawn
    await db.commit()
    rows = {r["id"]: r for r in (await client.get("/api/seniors", headers=signed_in("+40700000001"))).json()}
    assert (rows[str(maria.id)]["code"], rows[str(maria.id)]["reason"]) == ("yellow", "Nu are căldură în casă")
    assert (rows[str(ion.id)]["code"], rows[str(ion.id)]["since"]) == (None, None)
    page = (await client.get(f"/api/seniors/{maria.id}", headers=signed_in("+40700000001"))).json()
    assert page["code"] == "yellow"

async def test_a_senior_with_no_result_has_no_code(client, add_user, add_active_senior):
    await add_user("+40700000001", Role.das)
    maria = await add_active_senior("+40700000101")
    row = (await client.get("/api/seniors", headers=signed_in("+40700000001"))).json()[0]
    assert (row["code"], row["reason"], row["since"]) == (None, None, None)
```

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors/test_seniors.py -q`
Expected: the two new tests FAIL with a `KeyError: 'code'`.

- [ ] **Step 3: Implement** `senior_summaries` and the `senior_view` change. `list_seniors` returns `await senior_summaries(session, caller, role)`. The other `SeniorSummary` answers (enrollments, submit, accept, withdraw) keep `model_validate(senior)` and so carry `None`, which is right: none of those seniors is `active`.

- [ ] **Step 4: Run the seniors and incidents tests**

Run: `uv run pytest tests/seniors tests/incidents -q`
Expected: all PASS; `GET /incidents/{id}` is unchanged.

- [ ] **Step 5: Commit**

```bash
git add backend/app/seniors backend/tests/seniors
git commit -m "feat(seniors): code, reason and since on the seniors rows (Q17)"
```

---

### Task 5: The shared ending step

**Files:**
- Create: `backend/app/calls/ending.py`
- Test: `backend/tests/calls/test_ending.py`

**Interfaces:**
- Consumes: `app.status.engine` (`CallAnswers`, `Answer`, `Question`, `Severity`, `Certainty`, `final_severity`, `next_code`, `today_in_bucharest`); `opens_incident` from `app.incidents.service`; `ConsentMethod.app`.
- Produces:
  - `def redial_delay() -> timedelta`: 20 seconds when `get_settings().demo_mode`, otherwise 20 minutes (`06 §3`).
  - `def campaign_reason(worrying: list[Question], kind: CampaignKind) -> str`. With nothing worrying: `"Se simte bine, știe ce zi este și are căldură"` (cold) or `"Se simte bine, știe ce zi este și are un loc răcoros"` (heat). Otherwise the parts in question order are `"se simte rău"`, `"nu știe ce zi este"` and `"nu are căldură în casă"` / `"nu are un loc răcoros"`, joined `", "` with `" și "` before the last, and the first letter capitalized. So: `"Se simte rău și nu are căldură în casă"`.
  - `async def conclude(session: AsyncSession, call: Call, answers: CallAnswers | None) -> Severity | None`. `call` is `in_progress` (answered) or already `unanswered`. It returns the result, or `None` when a redial was queued. It doesn't commit.
  - `async def conclude_welcome(session: AsyncSession, call: Call, *, given: bool, method: ConsentMethod, text_version: str) -> bool`. `call` is `in_progress`. It returns `False` and writes nothing when the senior is no longer `accepted`. It doesn't commit.

What `conclude` writes is design §5, step for step:
- **Answered:** the call moves `in_progress` → `completed` with `ended_at`, and gets `final_severity`, `final_certainty`, `reason = campaign_reason(…)`, and `summary = f"Apel simulat din aplicație. {reason}."`. One `StatusReport(source=rules)` with that severity, certainty and reason. Then `next_code()` over the current `SeniorStatus` and whether an `UNRESOLVED` incident exists. The status row is upserted only when the new code equals the result (otherwise a sticky red stays as it is), with `since=now` and `source_call_id`. An `Incident(status=open, opened_by_call_id, reason)` is added when `opens_incident()` holds. The campaign's `kind` comes from `call.campaign_id`; a call with no campaign uses the cold wording.
- **Unanswered, attempt 1:** `StatusReport(source=unanswered, severity=starting, reason="Nu a răspuns la prima încercare")`. Then a redial `Call`: `previous_call_id`, `attempt=2`, the same `trigger`, `campaign_id` and `starting_severity`, and `due_at = now + redial_delay()`. No code change. Returns `None`.
- **Unanswered, attempt 2:** `final_severity(starting=…, answered=False)`, which is yellow for a campaign, with reason `"Nu a răspuns de două ori"`, a `StatusReport(source=unanswered)`, and the code as above.

`conclude_welcome` updates `Senior` to `active` (given) or `refused` only where it is still `accepted`, with `.returning(Senior.id)`. Then: `welcome_outcome=confirmed`, the call `completed`, and a `Consent(decision=given|refused, method, text_version, call_id)`. On `given`, a first `SeniorStatus(code=green, reason="Consimțământ dat", since=now, source_call_id)`.

- [ ] **Step 1: Write the failing tests** (`tests/calls/test_ending.py`)

Build rows directly with `add_active_senior` and a `Call` in `in_progress`. `answers()` is a helper that builds a `CallAnswers` from `(feeling, day, shelter)` values, all `clear=True`. Pin today with `monkeypatch.setattr("app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15))`, a Thursday.

```python
async def test_clear_fine_answers_end_green(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("ok", "joi", "yes")) is Severity.green
    await db.commit()
    assert (call.state, call.final_certainty, call.reason) == (CallState.completed, Certainty.high, "Se simte bine, știe ce zi este și are căldură")
    status = await db.get(SeniorStatus, call.senior_id)
    assert (status.code, status.source_call_id) == (Severity.green, call.id)
    assert await db.scalar(select(func.count()).select_from(Incident)) == 0

async def test_unwell_and_no_heating_is_red_with_an_incident(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("unwell", "joi", "no")) is Severity.red
    await db.commit()
    incident = await db.scalar(select(Incident))
    assert (incident.status, incident.opened_by_call_id, incident.reason) == (IncidentStatus.open, call.id, "Se simte rău și nu are căldură în casă")

async def test_a_wrong_day_alone_is_yellow(db, campaign_call):
    call = await campaign_call()
    assert await conclude(db, call, answers("ok", "luni", "yes")) is Severity.yellow

async def test_heat_wording(db, campaign_call):
    call = await campaign_call(kind=CampaignKind.heat)
    await conclude(db, call, answers("ok", "joi", "no"))
    assert call.reason == "Nu are un loc răcoros"

async def test_a_red_with_an_open_incident_is_not_lowered(db, campaign_call):
    call = await campaign_call()
    db.add_all([SeniorStatus(senior_id=call.senior_id, code=Severity.red, reason="r", since=datetime.now(UTC)),
                Incident(senior_id=call.senior_id, reason="r")])
    await conclude(db, call, answers("ok", "joi", "yes")); await db.commit()
    assert (await db.get(SeniorStatus, call.senior_id, populate_existing=True)).code is Severity.red

async def test_a_first_no_answer_queues_a_redial(db, campaign_call, monkeypatch):
    monkeypatch.setattr("app.calls.ending.get_settings", lambda: SimpleNamespace(demo_mode=True))
    call = await campaign_call(state=CallState.unanswered)
    assert await conclude(db, call, None) is None
    await db.commit()
    redial = await db.scalar(select(Call).where(Call.previous_call_id == call.id))
    assert (redial.attempt, redial.state, redial.campaign_id) == (2, CallState.queued, call.campaign_id)
    assert timedelta(seconds=15) < redial.due_at - datetime.now(UTC) <= timedelta(seconds=20)
    assert await db.get(SeniorStatus, call.senior_id) is None

async def test_a_second_no_answer_is_yellow(db, campaign_call):
    first = await campaign_call(state=CallState.unanswered)
    second = await campaign_call(state=CallState.unanswered, attempt=2, previous_call_id=first.id)
    assert await conclude(db, second, None) is Severity.yellow
    assert second.reason == "Nu a răspuns de două ori"

async def test_welcome_consent_activates_with_a_green_code(db, welcome_call):
    call = await welcome_call()
    assert await conclude_welcome(db, call, given=True, method=ConsentMethod.app, text_version="v1-app")
    await db.commit()
    senior = await db.get(Senior, call.senior_id, populate_existing=True)
    consent = await db.scalar(select(Consent))
    assert (senior.enrollment_state, consent.method, consent.text_version) == (EnrollmentState.active, ConsentMethod.app, "v1-app")
    assert (await db.get(SeniorStatus, senior.id)).reason == "Consimțământ dat"

async def test_welcome_refusal_and_a_senior_no_longer_accepted(db, welcome_call):
    refused = await welcome_call()
    assert await conclude_welcome(db, refused, given=False, method=ConsentMethod.app, text_version="v1-app")
    late = await welcome_call(state=EnrollmentState.withdrawn)
    assert not await conclude_welcome(db, late, given=True, method=ConsentMethod.app, text_version="v1-app")
```

Define the fixtures in the module. `campaign_call(kind=cold, state=in_progress, **columns)` makes a campaign, an active senior and its call. `welcome_call(state=accepted)` makes a senior in that state with an `in_progress` `welcome` call.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/calls/test_ending.py -q`
Expected: FAIL at import (`app.calls.ending` doesn't exist).

- [ ] **Step 3: Implement `app/calls/ending.py`** to the interfaces above. Its module docstring says it is the seam the Twilio relay reaches through `voice/router.py` (design §5).

- [ ] **Step 4: Run the calls and status tests, and the contracts**

Run: `uv run pytest tests/calls tests/status -q && uv run lint-imports`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/calls/ending.py backend/tests/calls/test_ending.py
git commit -m "feat(calls): the shared step that ends a call into a code and an incident (03 §6, §8)"
```

---

### Task 6: The mock campaign call

**Files:**
- Create: `backend/app/calls/mock.py`
- Modify: `backend/app/calls/schemas.py`, `backend/app/calls/router.py`
- Test: `backend/tests/calls/test_mock_calls.py`

**Interfaces:**
- Consumes: `conclude` (Task 5), `cancel_lapsed` (Task 3).
- Produces:
  - `Day = Literal["luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică", "unknown"]`.
  - `class MockCallView(BaseModel)`: `call_id: uuid.UUID`, `trigger: str`, `campaign_kind: str | None = None`, `campaign_level: str | None = None`, `consent_text: str | None = None`, `text_version: str | None = None`.
  - `class MockAnswerForm(BaseModel)`: `feeling: Literal["ok", "unwell"] | None = None`, `day: Day | None = None`, `shelter: Literal["yes", "no"] | None = None`, `declined: bool = False`, `consent: bool | None = None`.
  - `async def due_mock_call(session: AsyncSession, caller: Caller) -> MockCallView | None`.
  - `async def answer_mock_call(session: AsyncSession, caller: Caller, call_id: uuid.UUID, form: MockAnswerForm) -> None`. Commits.

Behaviour (design §4.2):
- Both functions refuse with 404 `not_found` in production, then run `cancel_lapsed`.
- `due_mock_call` takes the caller's `senior` grant, or refuses 403 `not_allowed`. It returns the oldest `queued` call with `due_at <= now` that is either `campaign` with the senior `active`, or `welcome` with the senior `accepted`. Campaign calls carry the campaign's `kind` and `level`; welcome calls carry `CARD_CONSENT_TEXT` and `CARD_CONSENT_VERSION`. It commits, because of `cancel_lapsed`.
- `answer_mock_call` locks the call (`with_for_update`). Refusals, in order:
  - No such call, or not the caller's senior: 404 `not_found`.
  - State `completed` or `unanswered`: 409 `already_done`.
  - Not `queued`, `due_at > now`, or the senior not in the state above: 409 `wrong_state`.
  - A campaign answer without `declined` and missing any of the three: 422 `incomplete` with `missing` naming them in question order.
  - A welcome answer without `consent`: 422 `incomplete`, `missing=["consent"]`. (Task 7 adds the welcome path; until then, a welcome call is 409 `wrong_state`.)
- A campaign answer walks the call `queued → ringing → in_progress` with `advance()`, setting `started_at`. It writes turns and `Answer` rows, then calls `conclude()`. `declined` walks `queued → ringing → unanswered` with `ended_at`, writes one turn, then calls `conclude(…, None)`.

Transcript lines (`CallTurn`, positions from 1, `kind=speech`; senior lines without `confidence`):

| Speaker | Content |
|---|---|
| system | `"Apel simulat din aplicație, fără linie telefonică."` |
| agent | `f"Bună ziua, {form_of_address}. Sunt asistentul automat al DAS Timișoara. Vă sunăm pentru că azi e cod {galben/roșu} de {ger/caniculă}. Cum vă simțiți?"` |
| senior | `"Bine"` or `"Rău"` |
| agent | `"Ce zi este azi?"` |
| senior | the day capitalized (`"Marți"`), or `"Nu știu"` |
| agent | `"Aveți căldură în casă?"` (cold) or `"Aveți un loc răcoros?"` (heat) |
| senior | `"Da"` or `"Nu"` |
| agent | `f"Vă mulțumesc, {form_of_address}. O zi bună!"`, or on red `f"{Form_of_address}, un dispecer DAS a fost anunțat."` (first letter uppercased only) |

`declined` writes the system line and then `"Seniorul a ales „Nu acum”."`, speaker system. `Answer` rows: `field`, `value` (the form's value; `unknown` for „Nu știu”), `clear=True`, `quote` the senior's line.

- [ ] **Step 1: Write the failing tests** (`tests/calls/test_mock_calls.py`)

The fixture `queued` makes a DAS user, an active senior `+40700000101` with a senior grant, and a cold/yellow campaign through `POST /campaigns`, and returns the senior. `SENIOR = "+40700000101"`.

```python
async def test_the_card_shows_the_due_campaign_call(client, queued):
    r = await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))
    assert r.status_code == 200
    assert r.json() | {"call_id": None} == {"call_id": None, "trigger": "campaign", "campaign_kind": "cold",
                                             "campaign_level": "yellow", "consent_text": None, "text_version": None}

async def test_answers_go_through_the_rules(client, db, queued, monkeypatch):
    monkeypatch.setattr("app.calls.ending.today_in_bucharest", lambda: date(2026, 10, 15))
    call_id = (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).json()["call_id"]
    r = await answer(client, call_id, {"feeling": "unwell", "day": "joi", "shelter": "no"})
    assert r.status_code == 204
    t = (await client.get(f"/api/calls/{call_id}/transcript", headers=signed_in(DAS))).json()
    assert t["state"] == "completed" and t["final_severity"] == "red"
    assert [a["field"] for a in t["answers"]] == ["feeling", "orientation", "shelter"]
    assert t["turns"][1]["content"].endswith("azi e cod galben de ger. Cum vă simțiți?")
    assert (await client.get("/api/incidents", headers=signed_in(DAS))).json()[0]["reason"] == "Se simte rău și nu are căldură în casă"
    assert (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).status_code == 204

async def test_a_second_tap_is_already_done(client, db, queued):                     # Review Focus 2
    call_id = (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).json()["call_id"]
    body = {"feeling": "ok", "day": "unknown", "shelter": "yes"}
    assert (await answer(client, call_id, body)).status_code == 204
    again = await answer(client, call_id, body)
    assert (again.status_code, again.json()) == (409, {"detail": {"reason": "already_done"}})
    assert await db.scalar(select(func.count()).select_from(Answer)) == 3

async def test_not_now_hides_the_card_until_the_redial(client, queued):               # Review Focus 3
    call_id = (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).json()["call_id"]
    assert (await answer(client, call_id, {"declined": True})).status_code == 204
    assert (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).status_code == 204
    redial = (await client.get(f"/api/seniors/{queued.id}/calls", headers=signed_in(SENIOR))).json()[0]
    assert redial["state"] == "queued"
    r = await answer(client, redial["id"], {"declined": True})
    assert (r.status_code, r.json()) == (409, {"detail": {"reason": "wrong_state"}})

async def test_missing_answers_are_incomplete(client, queued):
    call_id = (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).json()["call_id"]
    r = await answer(client, call_id, {"feeling": "ok"})
    assert (r.status_code, r.json()) == (422, {"detail": {"reason": "incomplete", "missing": ["day", "shelter"]}})

async def test_someone_elses_call_is_not_found(client, add_active_senior, queued):
    await add_active_senior("+40700000102")
    call_id = (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).json()["call_id"]
    r = await answer(client, call_id, {"declined": True}, token="+40700000102")
    assert r.status_code == 404

async def test_only_a_senior_reads_a_card(client, queued):
    assert (await client.get("/api/profile/mock-call", headers=signed_in(DAS))).json() == {"detail": {"reason": "not_allowed"}}

async def test_no_mock_in_production(client, queued, monkeypatch):                    # Q10
    monkeypatch.setattr("app.calls.mock.get_settings", lambda: SimpleNamespace(app_env=AppEnv.production))
    assert (await client.get("/api/profile/mock-call", headers=signed_in(SENIOR))).status_code == 404
    assert (await answer(client, uuid.uuid4(), {"declined": True})).status_code == 404
```

`answer(client, call_id, body, token=SENIOR)` posts to `/api/calls/{call_id}/mock-answer`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/calls/test_mock_calls.py -q`
Expected: FAIL with 404 for `/api/profile/mock-call`.

- [ ] **Step 3: Implement `calls/mock.py` and the two routes**

`GET /profile/mock-call` goes in `calls/router.py` with `response_model=MockCallView` and `responses={204: {"description": "No call is due"}}`. It returns `Response(status_code=204)` when `due_mock_call` gives `None`. `POST /calls/{call_id}/mock-answer` has `status_code=204`. Both use `current_caller`; the grant checks are in the service.

- [ ] **Step 4: Run the calls tests and the contracts**

Run: `uv run pytest tests/calls -q && uv run lint-imports`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/calls backend/tests/calls/test_mock_calls.py
git commit -m "feat(calls): the mock campaign call, read and answered from the senior's app (Q8, Q10, Q14)"
```

---

### Task 7: Welcome call and withdrawal

**Files:**
- Modify: `backend/app/calls/service.py`, `backend/app/calls/mock.py`, `backend/app/seniors/service.py`, `backend/app/seniors/router.py`
- Test: `backend/tests/calls/test_mock_calls.py` (append), `backend/tests/seniors/test_enrollments.py` (append), `backend/tests/seniors/test_consents.py` (append)

**Interfaces:**
- Consumes: `conclude_welcome` (Task 5), `answer_mock_call` (Task 6).
- Produces:
  - `Hook = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]` in `seniors/service.py`.
  - `accept(session, caller, senior_id, *, then: Hook | None = None)` and `withdraw_consent(session, caller, senior_id, *, then: Hook | None = None)`. Each awaits `then(session, senior.id)` after its reach checks and before `move()`, so a refused move rolls the hook back with it.
  - `async def queue_welcome_call(session: AsyncSession, senior_id: uuid.UUID) -> None` in `calls/service.py`: an insert of `trigger=welcome`, `attempt=1`, `starting_severity=green`, `due_at=now` with `on_conflict_do_nothing()`. No commit.
  - `async def cancel_queued_calls(session: AsyncSession, senior_id: uuid.UUID) -> None`: that senior's `queued` calls → `canceled` with `ended_at`. No commit.
  - The seniors router passes `then=queue_welcome_call` to `accept` and `then=cancel_queued_calls` to `withdraw_consent`. Update `accept_senior`'s docstring: the welcome call is queued now (04 §2).
  - `answer_mock_call` handles `welcome`. It walks `queued → ringing → in_progress` and writes three turns: the system line, the agent's `CARD_CONSENT_TEXT`, and the senior's `"Da"` or `"Nu"`. A fourth agent line follows: on yes `"Vă mulțumim. Nu vă vom cere niciodată bani sau date. O zi bună!"`, on no `"Am înțeles. Nu vă vom mai suna. O zi bună!"`. Then it calls `conclude_welcome(…, given=form.consent, method=ConsentMethod.app, text_version=CARD_CONSENT_VERSION)`, and when that returns `False` it refuses 409 `wrong_state`.

- [ ] **Step 1: Write the failing tests**

In `tests/seniors/test_enrollments.py`:
- `test_accepting_queues_the_welcome_call`: one `welcome` call, `queued`, `due_at` within a second of now.
- `test_a_repeated_accept_queues_nothing_more`: the second accept is 409 `already_done`, and there's still one call.

In `tests/seniors/test_consents.py`:
- `test_withdrawal_cancels_queued_calls`: an active senior with a queued campaign call → after withdrawal the call is `canceled`.
- `test_a_refused_withdrawal_cancels_nothing`: a `submitted` senior gets 409 `wrong_state`, and its queued call stays `queued`.

Append to `test_mock_calls.py`:

```python
async def test_the_welcome_card_and_consent(client, db, add_user, add_senior):
    das = await add_user(DAS, Role.das)
    senior = await add_senior("+40700000106", enrollment_state=EnrollmentState.submitted, street="Str. Daliei", street_number="1")
    herself = await add_user("+40700000106")
    db.add(Grant(user_id=herself.id, role=Role.senior, senior_id=senior.id)); await db.commit()
    await client.post(f"/api/seniors/{senior.id}/accept", headers=signed_in(DAS))
    card = (await client.get("/api/profile/mock-call", headers=signed_in("+40700000106"))).json()
    assert (card["trigger"], card["text_version"], card["consent_text"]) == ("welcome", "v1-app", CARD_CONSENT_TEXT)
    r = await answer(client, card["call_id"], {"consent": True}, token="+40700000106")
    assert r.status_code == 204
    row = (await client.get(f"/api/seniors/{senior.id}", headers=signed_in(DAS))).json()
    assert (row["enrollment_state"], row["code"]) == ("active", "green")

```

Move the setup above into a fixture, `welcome_card`, that returns the card. Add `test_welcome_needs_a_consent_answer`: posting `{"declined": True}` to the welcome card's call is `(422, {"detail": {"reason": "incomplete", "missing": ["consent"]}})`, and the senior stays `accepted`. Add `test_welcome_no_refuses`: `{"consent": False}` gives 204, the senior `refused` with no code, and a consent row `refused` with method `app`.

- [ ] **Step 2: Run them and see them fail**

Run: `uv run pytest tests/seniors tests/calls -q`
Expected: the new tests FAIL.

- [ ] **Step 3: Implement** the hooks, the two `calls/service.py` functions, the router wiring and the welcome path.

- [ ] **Step 4: Run the whole backend suite and the contracts**

Run: `uv run pytest -q && uv run lint-imports && uv run ruff check . && uv run ruff format --check .`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app backend/tests
git commit -m "feat(seniors): accept queues the welcome call, withdrawal cancels calls; the welcome card (Q11)"
```

---

### Task 8: Spec documents and the README

**Files:**
- Modify: `docs/specs/echocare/04-interfaces.md`, `05-data-model.md`, `03-status-model.md`, `06-operations.md`, `02-use-cases.md`, `docs/specs/auth-layer.md`, `backend/README.md`

- [ ] **Step 1: Make each change in the table of design §8.** In `04 §1` and `§2`, write the rows for every endpoint in Tasks 2 to 7, with their exact "who", answers and refusals. Mark the two mock rows **(demo only, refused in production)**. Don't touch `07-dashboard-stitch-spec.md`.
- [ ] **Step 2: Add `+40700000006` / `666666`, "a second senior, for the welcome card", to the test-number table in `backend/README.md`.**
- [ ] **Step 3: Check the docs against the code**

Run: `rg -n "canceled|warning_active|mock-call|mock-answer|v1-app|ConsentMethod|campaigns/\{" docs/specs backend/README.md`
Expected: every new term appears in the files design §8 names, and nowhere contradicts §4 of the design.

- [ ] **Step 4: Commit**

```bash
git add docs/specs backend/README.md
git commit -m "docs(spec): 04, 05, 03, 06, 02 and auth-layer match campaigns and mock calls"
```

---

### Task 9: Dashboard: the „Campanii” page and code chips

**Files:**
- Create: `dashboard/src/utils/campaigns.ts`, `dashboard/src/utils/campaigns.test.ts`, `dashboard/src/features/campaigns/Campaigns.svelte`, `dashboard/src/features/campaigns/index.ts`, `dashboard/src/routes/campaigns/+page.svelte`
- Modify: `dashboard/src/services/api.ts`, `dashboard/src/utils/labels.ts`, `dashboard/src/features/shell/Sidebar.svelte`, `dashboard/src/features/seniors/Seniors.svelte`, `dashboard/src/features/seniors/SeniorDetails.svelte`, `dashboard/src/features/incidents/IncidentDetails.svelte`, `dashboard/AGENTS.md` (the layout tree gains `campaigns/`)

**Interfaces:**
- Consumes: `GET`/`POST /campaigns`, `POST /campaigns/{id}/end` (Tasks 2–3); the code fields (Task 4).
- Produces, in `api.ts`:
  - `CampaignKind = "heat" | "cold"`, `WarningLevel = "yellow" | "red"`.
  - `interface Campaign` mirroring `CampaignSummary`, with `progress: { total; waiting; green; yellow; red; canceled: number }`.
  - `fetchCampaigns(signal?) => Promise<Campaign[]>`.
  - `startCampaign(kind, level) => Promise<{ campaign: Campaign; created: boolean }>`, where `created` is `r.status === 201`.
  - `endCampaign(id) => Promise<Campaign>`.
  - `SeniorSummary` and `SeniorView` gain `code: "green" | "yellow" | "red" | null`, `reason: string | null`, `since: string | null`, all optional (`?`) so an older API still type-checks.
- In `labels.ts`: `CODES: Record<string, { label: string; tone: Tone }>`, with `green` „Cod verde” / verde, `yellow` „Cod galben” / galben, `red` „Cod roșu” / rosu. And `code(c: string | null | undefined): { label; tone } | null`.
- In `utils/campaigns.ts`: `KIND_LABELS = { heat: "Caniculă", cold: "Ger" }`, `LEVEL_LABELS = { yellow: "Cod galben", red: "Cod roșu" }`, and `progressParts(p): { key; label; n; tone }[]`. Its labels, in order: „în așteptare” (muted), „verde”, „galben”, „roșu”, „anulate” (muted). Zero counts are dropped.

- [ ] **Step 1: Write the failing test** (`utils/campaigns.test.ts`)

```ts
import { describe, expect, it } from "vitest";
import { progressParts } from "./campaigns";

describe("progressParts", () => {
  it("lists the non-zero counts in order", () => {
    expect(progressParts({ total: 5, waiting: 2, green: 1, yellow: 0, red: 1, canceled: 1 }).map((p) => [p.label, p.n]))
      .toEqual([["în așteptare", 2], ["verde", 1], ["roșu", 1], ["anulate", 1]]);
  });
  it("is empty for a campaign that queued nobody", () => {
    expect(progressParts({ total: 0, waiting: 0, green: 0, yellow: 0, red: 0, canceled: 0 })).toEqual([]);
  });
});
```

- [ ] **Step 2: Run it and see it fail**

Run: `npx vp test`
Expected: FAIL, `./campaigns` not found.

- [ ] **Step 3: Implement the helpers, then the page and chips**

- **`Campaigns.svelte`:** `PageHeader title="Campanii meteo"`.
  - A start form: two choice groups, kind (Caniculă / Ger) and level (Cod galben / Cod roșu), and a `sn-btn` „Lansează”.
  - After a start: „Campanie lansată: {total} seniori de sunat.” when created, „Campania rulează deja.” when not.
  - The list from a page-local `poll(fetchCampaigns, 5_000, describe)`. Each row: kind and level labels, „pornită de {name}”, `time.format(started_at)`, „Avertizare până la {time}” and an „Activă” / „Încheiată” chip. Then a total and `progressParts` as tinted chips, and „Încheie” on active rows.
  - Refusals show as „Nu am putut trimite ({message}).”, like `Staff.svelte`. After any command, `reload()`.
- **Sidebar:** a new item `{ href: "/campaigns", label: "Campanii", icon: "zap", count: null }` after „Personal”.
- **Seniors and SeniorDetails:** a code chip (`TONE_CHIP[code.tone]`) with the reason beside it, where the enrollment chip is. Nothing when `code()` is `null`. Replace the comment that says the API sends no codes; leave the tabs as they are.
- **IncidentDetails:** `STATES` gains `canceled: "anulat"`.

- [ ] **Step 4: Run the dashboard checks**

Run: `npx vp check && npx svelte-check --tsgo --fail-on-warnings && npx vp test && npm run build`
Expected: all PASS with no warnings.

- [ ] **Step 5: Commit**

```bash
git add dashboard
git commit -m "feat(dashboard): Campanii page and code chips (Q12, Q17)"
```

---

### Task 10: Android: new fields, code chips, warning line

**Files:**
- Modify: `android/app/src/main/java/ro/echocare/Api.kt`, `.../home/Routes.kt`, `.../home/SeniorsScreen.kt`, `.../home/SeniorScreen.kt`, `.../home/SeniorViewModel.kt`, `android/app/src/main/res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/ApiTest.kt` (append), `.../home/RoutesTest.kt` (append)

**Interfaces:**
- Produces:
  - `SeniorRow` and `SeniorPage` gain `val code: String? = null`, `val reason: String? = null`, `val since: String? = null`.
  - `Me` gains `@SerialName("warning_active") val warningActive: Boolean = false`.
  - In `Routes.kt`: `CODE_LABELS = mapOf("green" to R.string.code_green, "yellow" to R.string.code_yellow, "red" to R.string.code_red)` and `CODE_TONES` (`Tone.Verde`, `Tone.Galben`, `Tone.Rosu`).
  - `@Composable fun CodeLabel(code: String?, reason: String?)` in `SeniorsScreen.kt`, next to `StateLabel`. It draws the chip and the reason in `Palette.FgMuted`, and nothing for a code this build doesn't know.
  - `SeniorViewModel` gains `var warning by mutableStateOf(false)`, read from `api.me()` only when `id == null`.
- Strings: `code_green` „Cod verde”, `code_yellow` „Cod galben”, `code_red` „Cod roșu”, `warning_active` „Avertizare meteo în vigoare”.

- [ ] **Step 1: Write the failing tests**

- `ApiTest.aRowWithACodeIsDecoded`: the existing row JSON plus `"code": "yellow", "reason": "Nu are căldură în casă", "since": "2026-10-17T10:00:00Z"` decodes to those values. The existing row test still passes without them.
- `ApiTest.anOldProfileHasNoWarning`: `{"display_name": "X", "grants": []}` decodes with `warningActive == false`.
- `RoutesTest.everyCodeHasALabelAndATone`: `CODE_LABELS.keys == CODE_TONES.keys == setOf("green", "yellow", "red")`.

- [ ] **Step 2: Run them and see them fail**

Run: `./gradlew :app:testDebugUnitTest`
Expected: compile errors on the missing fields and maps.

- [ ] **Step 3: Implement**

`SeniorCard` and `SeniorDetails` show `CodeLabel` under `StateLabel`, and the card's left bar takes the code's tone when there is one. On the senior's own home (`id == null`), a `Banner(stringResource(R.string.warning_active), Tone.Galben)` shows above the page while `vm.warning` is true.

- [ ] **Step 4: Run the Android checks**

Run: `./gradlew ktlintCheck lint testDebugUnitTest assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 5: Commit**

```bash
git add android
git commit -m "feat(android): code chips and the warning line (Q5, Q17)"
```

---

### Task 11: Android: the mock card

**Files:**
- Create: `android/app/src/main/java/ro/echocare/home/MockCall.kt`
- Modify: `Api.kt`, `home/SeniorViewModel.kt`, `home/SeniorScreen.kt`, `res/values/strings.xml`
- Test: `android/app/src/test/java/ro/echocare/home/MockCallTest.kt`

**Interfaces:**
- Consumes: `GET /profile/mock-call`, `POST /calls/{id}/mock-answer` (Tasks 6–7).
- Produces:
  - `@Serializable data class MockCall(@SerialName("call_id") val callId: String, val trigger: String, @SerialName("campaign_kind") val kind: String? = null, @SerialName("campaign_level") val level: String? = null, @SerialName("consent_text") val consentText: String? = null)`.
  - `@Serializable data class MockAnswer(val feeling: String? = null, val day: String? = null, val shelter: String? = null, val declined: Boolean = false, val consent: Boolean? = null)`.
  - In `EchoCareApi`: `@GET("profile/mock-call") suspend fun mockCall(): Response<MockCall>` (a 204 has no body), and `@POST("calls/{id}/mock-answer") suspend fun mockAnswer(@Path("id") id: String, @Body body: MockAnswer): Response<Unit>`.
  - `DAYS = listOf("luni", "marți", "miercuri", "joi", "vineri", "sâmbătă", "duminică")` in `MockCall.kt`, the server's values (design §4.2).
  - `fun campaignAnswer(feeling: String?, day: String?, shelter: String?): MockAnswer?` returns `null` until all three are chosen.
  - `@Composable fun MockCallCard(call: MockCall, onAnswer: (MockAnswer) -> Unit)`.
  - `SeniorViewModel`: `var mock by mutableStateOf<MockCall?>(null)`, read with each `reread(null)`. On a 204, a 404 or any failure it is `null`, so a production server simply shows no card. Also `fun answer(body: MockAnswer)`, which posts, clears `mock` and rereads, whatever the result (a 409 just re-reads).
- Strings: `mock_calling` „DAS Timișoara vă sună”, `mock_note` „Apel simulat: răspundeți aici în loc de telefon.”, `mock_warning` „Cod %1$s de %2$s”, `level_yellow` „galben”, `level_red` „roșu”, `kind_cold` „ger”, `kind_heat` „caniculă”. Then `q_feeling` „Cum vă simțiți?”, `feeling_ok` „Bine”, `feeling_unwell` „Rău”, `q_day` „Ce zi este azi?`, one string per day („Luni” to „Duminică”), and `day_unknown` „Nu știu”. Then `q_shelter_cold` „Aveți căldură în casă?”, `q_shelter_heat` „Aveți un loc răcoros?”, `yes` „Da”, `no` „Nu”, `mock_send` „Trimite răspunsurile”, `mock_later` „Nu acum”, and `welcome_title` „Apel de bun venit DAS”. Reuse an existing `yes`/`no` if `strings.xml` has one.

- [ ] **Step 1: Write the failing tests** (`MockCallTest.kt`)

```kotlin
class MockCallTest {
    // The same settings as NetworkModule: defaults (the nulls, declined = false) are not sent.
    private val json = Json { ignoreUnknownKeys = true }

    @Test fun anAnswerNeedsAllThree() {
        assertNull(campaignAnswer("ok", null, "yes"))
        assertEquals(MockAnswer(feeling = "ok", day = "marți", shelter = "yes"), campaignAnswer("ok", "marți", "yes"))
    }

    @Test fun answersAreSentAsTheServerReadsThem() {
        assertEquals("""{"declined":true}""", json.encodeToString(MockAnswer(declined = true)))
        assertEquals("""{"consent":false}""", json.encodeToString(MockAnswer(consent = false)))
        assertEquals(
            """{"feeling":"unwell","day":"sâmbătă","shelter":"no"}""",
            json.encodeToString(campaignAnswer("unwell", "sâmbătă", "no")!!)
        )
    }

    @Test fun aWelcomeCallIsDecoded() {
        val call = json.decodeFromString<MockCall>("""{"call_id": "c1", "trigger": "welcome", "consent_text": "Sunteți de acord?", "text_version": "v1-app"}""")
        assertEquals(MockCall("c1", "welcome", consentText = "Sunteți de acord?"), call)
    }

    @Test fun theDaysAreTheServers() { assertEquals(7, DAYS.size); assertEquals("sâmbătă", DAYS[5]) }
}
```

- [ ] **Step 2: Run them and see them fail**

Run: `./gradlew :app:testDebugUnitTest --tests ro.echocare.home.MockCallTest`
Expected: compile errors.

- [ ] **Step 3: Implement the card**

The card sits at the top of the senior's own home, above `SeniorDetails`, when `vm.mock != null`. It has a `Banner`-toned header with `mock_calling` and, for a campaign, `mock_warning`, then `mock_note`.
- **Campaign:** three question blocks with large `SnButton`s, the chosen one highlighted. „Trimite răspunsurile” is enabled once `campaignAnswer(…)` isn't null; „Nu acum” sends `MockAnswer(declined = true)`.
- **Welcome:** `welcome_title`, `call.consentText`, „Da” → `MockAnswer(consent = true)`, „Nu” → `MockAnswer(consent = false)`.

The question shown for shelter follows `call.kind` (`heat` → `q_shelter_heat`, else `q_shelter_cold`).

- [ ] **Step 4: Run the Android checks**

Run: `./gradlew ktlintCheck lint testDebugUnitTest assembleDebug`
Expected: BUILD SUCCESSFUL.

- [ ] **Step 5: Commit**

```bash
git add android
git commit -m "feat(android): the mock call card on the senior's home (Q8, Q11)"
```

---

### Task 12: Manual check of the whole workflow

**Files:** none, unless a step fails. Then fix it in the task that owns the code, with a test, and commit there.

- [ ] **Step 1: Every folder's checks, from each folder**

Run: `uv run pytest -q && uv run lint-imports` (backend), `npm run check && npx vp test && npm run build` (dashboard), `./gradlew ktlintCheck lint testDebugUnitTest assembleDebug` (android).
Expected: all PASS.

- [ ] **Step 2: Bring up the stack**

Run, from the repository root: `docker compose up --watch -d`, then `cd backend && uv run python scripts/seed.py --reset`, then `curl localhost:8000/api/health`.
Expected: `{"status":"ok","env":"local"}`.

- [ ] **Step 3: Run the nine steps of design §9's manual-check table**, dashboard in the browser pane at http://localhost:5173 and Android on an emulator. `local.properties` has `echocare.apiUrl=http://10.0.2.2:8000`. `+40700000006` / `666666` must already be a Firebase test number.
- [ ] **Step 4: Report each of the nine steps as checked or not checked, with what was seen.** A step that couldn't be run (no emulator, no test number yet) is reported as not checked, never as passed.
