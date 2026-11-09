# Staging Team Seed Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Staging holds the fictional seed plus the team's four people. Every active fictional senior carries seeded summary versions that pass the real writer's checks.

**Architecture:** `seed_cast.py` reads a list of staff (several roles each) and seniors (medic and caregivers linked by phone), and keeps seeding through the apps' own service calls. `seed.py` gains the same Railway `--confirm` gate, refuses production, grants no DAS on a cloud database and writes its campaign already lapsed there. Its `History` gets per-senior summary chains and more fixed-text wellbeing history.

**Tech Stack:** Python 3.14, SQLAlchemy async, Pydantic v2, pytest against `echocare_test`, uv.

**Spec:** `docs/superpowers/specs/2026-11-09-staging-team-seed-design.md`

## Global Constraints

- No real name or real phone number in any tracked file. Examples and tests use only the `+40700000…` range (as `test_the_example_cast_is_valid_and_made_up` does).
- User-facing text (transcripts, summaries) is Romanian, gender-agreed per senior, never templated across seniors. Code and comments are English and cite spec IDs (`03 §3`, `design §6`, `ADR-001`).
- Seeded calls follow 03 §3: final severity and reason match the answers. Use the existing `cold_call` / `call` / `emergency` helpers.
- A cloud database is seeded only from inside its Railway deployment with `--confirm <APP_ENV>`. `seed.py` refuses `APP_ENV=production` always. Don't weaken any existing guard.
- On a cloud database `seed.py` grants no `das` role and deletes no grants.
- Run from `backend/`: `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run lint-imports`. Commit with the hooks on.
- Import a name from the module that defines it. No imports inside functions.

## Review Focus

1. **A seeded quote that only matches because the test reads too much.** Production gives the writer the current call's turns but only *answers* for earlier calls (`summary_input`). A trend citing an older call's turn passes a test that loads every turn, but would be rejected live. Task 3's test builds its input with `summary_input` itself.
2. **A second senior's versions chaining into Eugenia's.** Today `summarize` uses one global list. Task 3 pins per-senior chains.
3. **An answered wellbeing call left without a version.** On staging with a key, `due_calls` would send it to the paid model, and the briefing would skip it. This includes handed-over watch and manual calls. Task 4 pins it.
4. **A cast file with no, or two, DAS on duty, or a senior whose `medic` is not a medic in the file.** The hand-over rings nobody, or `register` runs as the wrong caller. Task 1 pins each refusal.
5. **`seed.py --confirm production` inside Railway.** It must refuse even though `check_target` accepts it. Task 2 pins it.

---

### Task 1: `seed_cast.py` reads lists of staff and seniors

**Files:**
- Modify: `backend/scripts/seed_cast.py` (the `Cast` model, `seed_cast`, the module docstring, `main`'s description)
- Modify: `backend/cast.example.json`
- Modify: `backend/README.md` (the "Seed the cast" section, around lines 158–175)
- Test: `backend/tests/tooling/test_seed_cast.py`

**Interfaces:**
- Produces, in `scripts/seed_cast.py`:
  - `class StaffEntry(BaseModel)`: `display_name: str`, `phone: str`, `roles: list[Literal["das", "medic"]]` (1–2 items, no repeats), `practice: str | None = None`, `on_duty: bool = False`. Method `forms(self) -> list[StaffGrantForm]`, one per role. A `model_validator(mode="after")` builds them, so a landline, or a medic role without a practice, is refused exactly as `POST /staff` refuses it. `phone` is normalized to E.164.
  - `class SeniorEntry(SeniorForm)`: adds `medic: str` (a phone, normalized with `app.core.phones.normalize`) and `caregivers: list[CaregiverForm] = []`.
  - `class Cast(BaseModel)`: `staff: list[StaffEntry]` (min 1), `seniors: list[SeniorEntry] = []`. Its validator refuses:
    - two staff entries with the same phone
    - a count of `on_duty: true` other than exactly one
    - `on_duty` on an entry without `das`
    - a senior whose `medic` is not the phone of a staff entry holding `medic`
    - a senior without `street` and `street_number` (the existing rule, now per senior)
  - `check_target(confirm: str | None) -> str` and `read_cast(source: str) -> Cast`, unchanged.
  - `async def seed_cast(cast: Cast) -> list[str]`, same contract: one line per thing done, numbers masked, idempotent.

- [ ] **Step 1: Rewrite the tests for the new shape**

Replace `CAST` with the new shape. Use made-up numbers: A `+40700000201` das+medic, practice `"CMI Test"`, on duty. B `+40700000202` das. Seniors C `+40700000203` and D `+40700000205`, both with `medic: "+40700000201"`. C has caregiver B (`relation: "fiul"`), D has a caregiver `+40700000204`.

```python
async def test_the_cast_is_seeded_once(db):
    first = await seed_cast(Cast.model_validate(CAST))
    counts = (await count(db, User), await count(db, Grant), await count(db, Senior))
    second = await seed_cast(Cast.model_validate(CAST))
    assert await roles(db, "+40700000201") == {Role.das, Role.medic}
    assert await roles(db, "+40700000202") == {Role.das, Role.caregiver}
    assert (await user(db, "+40700000201")).on_duty
    assert not (await user(db, "+40700000202")).on_duty
    a = await user(db, "+40700000201")
    for phone in ("+40700000203", "+40700000205"):
        s = await db.scalar(select(Senior).where(Senior.phone_e164 == phone))
        assert (s.enrollment_state, s.medic_id) == (EnrollmentState.submitted, a.id)
        assert await roles(db, phone) == {Role.senior}
    assert await roles(db, "+40700000204") == {Role.caregiver}
    assert (await count(db, User), await count(db, Grant), await count(db, Senior)) == counts
    assert not any(p in line for line in first + second
                   for p in ("+40700000203", "+40700000205"))
    assert any("already" in line for line in second)
```

Keep `test_a_number_another_medic_registered_is_left_alone`: the other senior is left alone, and the rest of the cast is still seeded (D submitted, B still `das`). Keep the three `check_target` tests and the stdin test as they are, adapted to the new shape. Make `test_a_bad_cast_is_refused` parametrized over these mutations of `CAST`, each expecting `SystemExit` matching `"cast"`:
- B's phone is a landline, `"0256 123 456"`
- A without `practice`
- no entry `on_duty`
- both A and B `on_duty`
- C's `medic` is B's phone
- C without `street_number`
- A and B with the same phone

`test_the_example_cast_is_valid_and_made_up`: every staff, senior and caregiver phone in `cast.example.json` starts with `+40700000`.

- [ ] **Step 2: Run them, expect failures**

Run: `uv run pytest tests/tooling/test_seed_cast.py -v`
Expected: FAIL. `Cast` has no `staff` field.

- [ ] **Step 3: Implement the models and `seed_cast`**

`seed_cast`:
1. For each staff entry, for each form from `forms()`, call the existing `staff()` helper and collect the user ids by phone.
2. Call `set_on_duty` with the on-duty entry's user id.
3. For each senior, build the `Caller` for its medic, as the code does today, then run today's register → `grant_caregiver` (`already_done` tolerated) → submit steps.

A senior registered by another medic adds the "left as it is" line and moves on to the next senior, instead of `return`. Update the docstring and the argparse description to "staff and seniors".

- [ ] **Step 4: Rewrite `cast.example.json` in the new shape**

Use made-up people only: the Firebase test numbers `+40700000001` (das+medic, on duty), `+40700000003` (das), and seniors `+40700000005` and `+40700000006` with caregiver `+40700000004`.

- [ ] **Step 5: Run the tests, expect a pass**

Run: `uv run pytest tests/tooling/test_seed_cast.py -v`
Expected: all PASS.

- [ ] **Step 6: Update the README's "Seed the cast" section**

Describe the new shape: one person may hold `das` and `medic`, a caregiver may also be staff, exactly one DAS is `on_duty`. Say that production uses the same shape and its file needs rewriting once.

- [ ] **Step 7: Run the whole backend check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
Expected: all green.

```bash
git add backend/scripts/seed_cast.py backend/cast.example.json backend/README.md backend/tests/tooling/test_seed_cast.py
git commit -m "seed_cast: lists of staff with several roles, and seniors with their medic and caregivers (ADR-001, staging seed design §4.1)"
```

---

### Task 2: `seed.py` may run on staging, without DAS and with a lapsed campaign

**Files:**
- Modify: `backend/scripts/seed.py` (`build`, `seed`, `main`, module docstring)
- Modify: `backend/README.md` (the mock data section: the staging run and the §6 checklist from the spec)
- Test: `backend/tests/tooling/test_scripts.py`

**Interfaces:**
- Consumes: `check_target(confirm: str | None) -> str` from `scripts.seed_cast` (Task 1, unchanged). Import it as `from scripts.seed_cast import check_target`, since `seed.py` already puts `backend/` on `sys.path`.
- Produces:
  - `def build(now: datetime, users: dict[str, uuid.UUID], *, cloud: bool = False) -> History`. With `cloud=True`, `STAFF_GRANTS` entries whose role is `Role.das` are skipped, and the campaign's `warning_until` is in the past: `started_at = ago(125)`, `warning_until = ago(5)`. With `cloud=False`, nothing changes.
  - `async def seed(reset: bool = False, now: datetime | None = None, confirm: str | None = None) -> str`. It calls `check_target(confirm)`, raises `SystemExit` naming production when `get_settings().app_env == "production"`, and passes `cloud=not is_local_db(url)` to `build`.
  - `main` adds `--confirm`.

- [ ] **Step 1: Write the failing tests**

Replace `test_seed_refuses_a_cloud_database` with these:

```python
def fake_users() -> dict[str, uuid.UUID]:
    return {p.phone: uuid.uuid4() for p in seed_script.people()}

def test_cloud_build_grants_no_das_and_lapses_the_campaign():
    now = datetime.now(UTC)
    h = seed_script.build(now, fake_users(), cloud=True)
    assert Role.das not in {g["role"] for g in h.grants}
    assert h.campaign.warning_until < now

def test_local_build_keeps_das_and_a_running_campaign():
    now = datetime.now(UTC)
    h = seed_script.build(now, fake_users())
    assert Role.das in {g["role"] for g in h.grants}
    assert h.campaign.warning_until > now

async def test_seed_refuses_a_cloud_database_from_a_laptop(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.delenv("RAILWAY_DEPLOYMENT_ID", raising=False)
    with pytest.raises(SystemExit, match="inside the api container"):
        await seed(confirm="staging")

async def test_seed_refuses_production_even_confirmed(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "database_url", "postgresql://u@postgres.railway.internal/r")
    monkeypatch.setattr(s, "app_env", "production")
    monkeypatch.setenv("RAILWAY_DEPLOYMENT_ID", "d-1")
    with pytest.raises(SystemExit, match="production"):
        await seed(confirm="production")
```

If `build` reaches for users outside `people()` (the seniors' own numbers), extend `fake_users` with `{s.phone: uuid.uuid4() for s in SENIORS}` rather than changing `build`.

- [ ] **Step 2: Run them, expect failures**

Run: `uv run pytest tests/tooling/test_scripts.py -k "cloud or production or local_build" -v`
Expected: FAIL. `build()` takes no `cloud`, and `seed()` takes no `confirm`.

- [ ] **Step 3: Implement `build(..., cloud=)`, `seed(..., confirm=)` and `--confirm`**

Update the module docstring: it runs locally, or on staging from inside Railway with `--confirm staging`. Production is refused, and on a cloud database nobody gets DAS and the campaign is already over.

- [ ] **Step 4: Run the seed tests, expect a pass**

Run: `uv run pytest tests/tooling/test_scripts.py -v`
Expected: all PASS, the existing seed tests included.

- [ ] **Step 5: Document the staging run in the README**

Add the command `railway ssh -s api -e staging -- python scripts/seed.py --confirm staging` (plus `--reset`), then `seed_cast.py`, in either order. Add the spec §6 checklist as written:
- `DEEPINFRA_API_KEY`
- `DIAL_ALLOWLIST` set to the four numbers
- the four numbers verified in Twilio
- real-SMS sign-in
- revoke any DAS grant other than A's and B's
- campaign clutter is accepted

- [ ] **Step 6: Run the whole backend check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add backend/scripts/seed.py backend/README.md backend/tests/tooling/test_scripts.py
git commit -m "seed: run on staging with --confirm, never production; no DAS and a lapsed campaign on a cloud database (staging seed design §4.2, §4.3)"
```

---

### Task 3: Per-senior summary chains, checked with the writer's production input

**Files:**
- Modify: `backend/scripts/seed.py` (`History.__init__` comment, `History.summarize`)
- Test: `backend/tests/tooling/test_scripts.py` (`test_seeded_citations_are_real`, `test_seed_writes_a_chain_of_versions`)

**Interfaces:**
- Consumes: `summary_input(session, call_id) -> tuple[uuid.UUID, uuid.UUID | None, SummaryInput]` from `app.memory.service`, and `citation_errors(data, content) -> list[str]` from `app.memory.writer`.
- Produces: `History.summarize(senior: str, call: Call, **content)`, same signature. `previous_id` is the latest version *of that senior*, and the id is `seed_id("summary", senior, str(n))` with `n` counted per senior, so Eugenia's ids stay the same.

- [ ] **Step 1: Generalize the tests**

Add a helper `async def all_versions(db) -> dict[uuid.UUID, list[SummaryVersion]]`, giving each senior's versions ordered by `created_at`.

- `test_seed_writes_a_chain_of_versions`: keep the Eugenia assertions, and add that for **every** senior `chain[0].previous_id is None`, each later `previous_id` is the one before it in the same senior's list, and no version's `previous_id` points at another senior's version.
- `test_seeded_citations_are_real`, for every senior and every version `v`:

```python
_, _, data = await summary_input(db, v.call_id)
data = dataclasses.replace(data, previous=previous_content)  # the version before v, or None
assert citation_errors(data, SummaryContent.model_validate(v.content)) == [], (senior, i)
```

`summary_input` reads the latest version as `previous`, so the test swaps in the one before `v`. Drop the hand-built `CallFacts` code. The production input carries only answers for earlier calls (Review Focus 1). If Eugenia's existing trend fails under it, the seed is wrong, not the test: change her cited quote to one her earlier call's `Answer.quote` holds, or carry it from the previous version.

Also add a pure test that fails on today's global chain. It uses `fake_users()` from Task 2:

```python
def test_a_second_seniors_first_version_starts_its_own_chain():
    h = seed_script.build(datetime.now(UTC), fake_users())
    maria = next(c for c in h.calls
                 if c.senior_id == h.seniors["maria"].id and c.ended_at)
    h.summarize("maria", maria, follow_ups=[], how_to_talk=[], trends=[],
                narrative="Doamna Maria se descurcă.")
    assert h.summaries[-1].previous_id is None
    assert h.summaries[-1].id == seed_script.seed_id("summary", "maria", "1")
```

- [ ] **Step 2: Run them, expect one failure**

Run: `uv run pytest tests/tooling/test_scripts.py -k "chain or citations" -v`
Expected: `test_a_second_seniors_first_version_starts_its_own_chain` FAILS, because `previous_id` is Eugenia's last version. The others PASS, unless Step 1's note about Eugenia applies.

- [ ] **Step 3: Make `summarize` chain and number per senior**

- [ ] **Step 4: Run the seed tests and commit**

Run: `uv run pytest tests/tooling/test_scripts.py -v`
Expected: all PASS.

```bash
git add backend/scripts/seed.py backend/tests/tooling/test_scripts.py
git commit -m "seed: summary chains per senior, checked against the writer's own input (design §6, staging seed design §4.5)"
```

---

### Task 4: Summaries for the fictional seniors who already have answered calls

Seniors: `maria`, `ion`, `elena`, `gheorghe`, `ana`, `florica`, `aurelia`. Eugenia stays as she is.

**Files:**
- Modify: `backend/scripts/seed.py` (`build`; a function per senior like `decline()` if `build` grows unreadable)
- Test: `backend/tests/tooling/test_scripts.py`

**Interfaces:**
- Consumes: `History.summarize` (Task 3), `cold_call`, `call`, `emergency`, `status`, `incident`.
- Produces: nothing new for later tasks.

- [ ] **Step 1: Write the failing tests**

```python
async def test_every_answered_wellbeing_call_has_a_version(db):
    await seed(reset=True)
    missing = await db.scalars(
        select(Call.id).join(Senior, Senior.id == Call.senior_id)
        .where(SEEDED_SENIOR, Senior.enrollment_state == EnrollmentState.active,
               Call.trigger.in_(WELLBEING), Call.state.in_(ENDED_ANSWERED),
               ~exists().where(SummaryVersion.call_id == Call.id))
    )
    assert list(missing) == []

async def test_latest_trends_show_every_direction(db):
    await seed(reset=True)
    directions = set()
    for chain in (await all_versions(db)).values():
        directions |= {t.direction for t in
                       SummaryContent.model_validate(chain[-1].content).trends}
    assert directions >= {"worse", "better", "steady"}
```

Take `SEEDED_SENIOR` from `seed_script.SEEDED`, `WELLBEING` from `app.voice.models`, and `ENDED_ANSWERED` from `app.memory.service`.

- [ ] **Step 2: Run them, expect failures**

Run: `uv run pytest tests/tooling/test_scripts.py -k "every_answered or every_direction" -v`
Expected: FAIL. Maria's and the others' answered calls have no versions, and there's no `better` or `steady`.

- [ ] **Step 3: Write the history**

For each of the seven seniors:
- Add 2–4 earlier answered wellbeing calls, between their welcome call and their existing calls. Date campaign calls before that senior's incident opened (03 §8).
- Call `summarize` for every answered wellbeing call, in call order, including the existing ones and the handed-over watch and manual calls. Maria's `emergency` with `answered=True` counts.

Follow-ups, trends and narrative build on each senior's existing story (spec §4.4). Ana's latest version holds a `better` trend about her recovery after the palpitations. One other senior holds a `steady` trend. Every trend cites 2–4 calls within the writer's reach: the current call, the 5 earlier answered wellbeing calls, or quotes carried from the previous version. Quotes copy the senior's own words exactly. For an earlier call, copy an answer's quote. Keep `how_to_talk` to at most 3 short items, as Eugenia's are.

- [ ] **Step 4: Run the seed tests, expect a pass**

Run: `uv run pytest tests/tooling/test_scripts.py -v`
Expected: all PASS, including Task 3's chain and citation tests, now over eight seniors.

- [ ] **Step 5: Check locally on the dashboard**

Run, from the repository root: `docker compose up --watch db dashboard`, then `cd backend && uv run python scripts/seed.py --reset && uv run uvicorn app.main:app --reload`. Sign in as `+40700000001`. Open Ana's and Maria's senior pages: each shows a briefing with dated citations, and Ana shows a `better` observation.

- [ ] **Step 6: Run the whole backend check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add backend/scripts/seed.py backend/tests/tooling/test_scripts.py
git commit -m "seed: earlier wellbeing calls and summary versions for seniors with answered calls (staging seed design §4.4)"
```

---

### Task 5: Summaries for the active fictional seniors with no answered calls

Seniors: `vasile`, `dumitru`, `teodor`, `viorica`, `gavril`, `margareta`.

**Files:**
- Modify: `backend/scripts/seed.py`, and its module docstring (the senior count and "one of them, Eugenia…" now that every active senior has versions)
- Test: `backend/tests/tooling/test_scripts.py`

**Interfaces:**
- Consumes: as Task 4.

- [ ] **Step 1: Write the failing test**

```python
async def test_every_active_seeded_senior_has_a_briefing(db):
    await seed(reset=True)
    chains = await all_versions(db)
    active = await db.scalars(select(Senior.id).where(
        seed_script.SEEDED, Senior.enrollment_state == EnrollmentState.active))
    assert all(s in chains for s in active)
```

- [ ] **Step 2: Run it, expect a failure**

Run: `uv run pytest tests/tooling/test_scripts.py -k briefing -v`
Expected: FAIL. These six have no versions.

- [ ] **Step 3: Write the history**

Give each of the six 2–4 quiet answered wellbeing calls, before their existing events and incidents, each with its version. For Vasile, they come before his two unanswered campaign calls. Mostly green, no trend required. Their incident dossier then has a briefing.

- [ ] **Step 4: Run the seed tests, expect a pass**

Run: `uv run pytest tests/tooling/test_scripts.py -v`
Expected: all PASS.

- [ ] **Step 5: Check one open incident's dossier locally**

With the stack from Task 4, open Dumitru's incident on the board. Its briefing shows above or beside the transcript, with dated citations.

- [ ] **Step 6: Run the whole backend check and commit**

Run: `uv run pytest -q && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`

```bash
git add backend/scripts/seed.py backend/tests/tooling/test_scripts.py
git commit -m "seed: quiet earlier wellbeing calls and versions for every active senior (staging seed design §4.4)"
```
