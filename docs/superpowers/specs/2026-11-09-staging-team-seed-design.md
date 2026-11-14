# Staging team seed and seeded summaries

Status: draft, 2026-11-09. Branch `staging-team-seed`, cut from `63-senior-summary-agents` (PR #64), because it seeds `summary_versions`, which only exists there.

Spec: ADR-001 (staging holds the team's phones), 03 §3 and §8, 05 §5, 06 §4, the summary agents design (`2026-11-08-senior-summary-agents-design.md` §4 and §6).

## 1. Intent

Two things, for one reason: the team wants to see the summary agent work end to end, on real devices, before the demo.

- **A. Staging gets the four of us.** Two team members are DAS (one also a medic, one also a caregiver), and two are seniors. They use real Android phones and Wear OS watches and get real Twilio calls. The two seniors start with **no history**: real calls build their transcripts, the summary agent writes their memory, and the next call uses it. The team then reads what the model wrote. That is the test.
- **B. The fictional seed gets deeper.** Today only Eugenia Tudor has summary versions. Every other fictional senior with answered calls has none, so the dashboard briefing and the incident dossier come up empty for them. Each active fictional senior gets a few weeks of earlier wellbeing calls, each with the summary version the agent would have written. The same fictional data goes on staging too, where it fills the dashboard and is never rung.

## 2. Goals, non-goals, anti-goals

**Goals**
- One run on staging gives the full fictional cast plus the team's four people, with the right roles.
- Only the team's four numbers can ever ring. `DIAL_ALLOWLIST` on staging holds exactly those four.
- Every active fictional senior with answered calls shows a briefing on the dashboard: narrative, open topics, how-to-talk notes and, for some, trend notes.
- `seed.py --reset` on staging refreshes the fictional data and leaves the team's real seniors and their real call history alone.

**Non-goals**
- Seeded history for the two team seniors. The model writes it.
- Changing the summary agent, the dialer or the allowlist code.
- Seeding production with fictional data.

**Anti-goals: a failure even if it works**
- A real name or real phone number in Git.
- Any fictional number rung from staging. The made-up `+40 700…` numbers sit in Romania's 070x range, which is premium-rate as far as we know.
- Anyone outside the team reading the team seniors' data on staging. The Firebase test numbers and their codes are published in `backend/README.md`, so a test number holding `das` on staging could read everything. On staging only A and B hold DAS (§4.3).
- Seeded summaries that the real writer would reject: a quote that isn't in the senior's transcript, or a citation to another senior's call.

## 3. The people (decided with the user)

| Who | Roles | Notes |
|---|---|---|
| A | DAS + medic | Starts on duty, so the hand-over rings A. Medic of both team seniors |
| B | DAS + caregiver | Caregiver of the team senior(s) the file says |
| C | senior | Own name, own address, own phone and watch |
| D | senior | Same |

The user writes all real data (names, numbers, addresses, practice, relations) into the git-ignored `backend/cast.json`. Nothing about them goes into `seed.py` or any other tracked file.

## 4. How

### 4.1 `seed_cast.py` reads a list, not four fixed slots

Today `Cast` holds exactly one medic, one DAS, one senior and one caregiver, one role each. The new shape:

```json
{
  "staff": [
    {"display_name": "…", "phone": "+40…", "roles": ["das", "medic"], "practice": "…", "on_duty": true},
    {"display_name": "…", "phone": "+40…", "roles": ["das"]}
  ],
  "seniors": [
    {
      "full_name": "…", "form_of_address": "…", "phone": "+40…",
      "street": "…", "street_number": "…", "call_window": "10:00–18:00",
      "medic": "+40… (a staff phone that holds medic)",
      "caregivers": [{"display_name": "…", "relation": "fiu", "phone": "+40…"}]
    }
  ]
}
```

- Each staff entry is checked as `StaffGrantForm` is today, once per role. Each senior is checked as `SeniorForm`, each caregiver as `CaregiverForm`, so the file is refused exactly where the API would refuse it.
- People refer to each other by phone. The checks refuse a `medic` phone that isn't a staff entry holding `medic`, and more or fewer than one `on_duty: true` among DAS staff. One DAS on duty at a time is a rule of `set_on_duty` (auth/service.py), and the hand-over rings that person.
- A caregiver whose phone is also a staff entry (B) gets the caregiver grant on top. The grants table already allows it: unique per (user, role, senior).
- The steps stay the ones the apps take: `grant_staff`, `set_on_duty`, `register` as the senior's medic, `grant_caregiver`, `submit`. A second run adds nothing. The existing guards stay: a senior registered by another medic is left alone, and so on.
- Each team senior ends **submitted**, as today. A accepts them on the dashboard, and the welcome call rings their phone (consent included). There is no periodic wellbeing dialer: after that, a wellbeing call comes only from a campaign a DAS starts, a watch event, or „Sunați-mă” in the senior's app. Those calls build their history.
- `register()` gives them uuidv7 ids, so `seed.py --reset`, which deletes only uuid5 seniors, never touches them or their calls.
- **Production** uses the same script and the same new shape. Its cast (1 medic, 1 DAS, 1 senior, 1 caregiver) fits in it. `cast.example.json` moves to the new shape with made-up people, and its test keeps checking that it is valid and made up. The old four-slot shape is dropped, not kept alongside: the file lives outside Git and is rewritten once. *(My call.)*

### 4.2 `seed.py` may run on staging

- Today it refuses any non-local database (seed.py:1639). It takes the same gate as `seed_cast.py`: a cloud database only from inside its Railway deployment, and only with `--confirm <APP_ENV>`. It also refuses `APP_ENV=production` even with `--confirm`: fictional data never goes to production. Share `check_target` between the two scripts rather than copying it; how is the builder's call.
- On a cloud database the seeded cold campaign is written **already lapsed** (its `warning_until` in the past). Otherwise it runs for 24 hours after every seed run, `--reset` pushes its end out each time, and a cold/yellow campaign A starts during that time answers the seeded one and queues nothing (04 §2). Locally it stays running, as today. *(My call, from the builder check.)*
- On staging: `railway ssh -s api -e staging -- python scripts/seed.py --confirm staging` (add `--reset` for fresh times), then `seed_cast.py` as today. Either order works.

### 4.3 No fictional or test-number DAS on a cloud database

On a cloud database, `seed.py` grants **no `das` role** to anyone: not `DAS Test` (`+40700000001`), and not `Cristian Pavel` (`+40700000301`). (`seed.py` never grants the `+40700000003` test number anything; a grant it holds on staging was made by hand.) Their users are still made, so incidents they took keep their `taken_by`. Medic, caregiver and senior grants on fictional seniors stay as they are, because those only reach fictional data. Locally nothing changes.

**Decided with the user:** on staging, DAS is held only by A and B, who sign in with real SMS verification. No test number holds DAS there. The seed only stops granting it. It deletes no grants on a cloud database. Any test-number or fictional DAS grant already on staging is revoked by hand, as a step on the §6 checklist *(my call on who revokes, to keep "leave cloud environments alone")*.

### 4.4 Deeper fictional history

For each active fictional senior except Eugenia, who stays as she is:

- Add 2–4 earlier **answered wellbeing calls** (trigger in `WELLBEING`: campaign, watch or manual) before the calls they already have, spread over the weeks since their welcome call. Each has a transcript, answers and a final severity that follow 03 §3, through the existing `cold_call` helper or its siblings, as commit `77077b7` made the seed do.
- Each answered wellbeing call, old and new, gets the `SummaryVersion` it would have produced, chained with `previous_id`, through the existing `History.summarize`. Today `summarize` chains to the last version of *any* senior and numbers ids with one global counter. It must chain and number per senior, or the second senior's chain links into Eugenia's. Fixed Romanian text, no model call, so `--reset` stays repeatable and needs no key.
- The stories build on what each senior already has. Ion's headache and cold flat, Ana's palpitations and then her recovery, Florica's fall and the next day, Aurelia's dizziness and broken heater, Gheorghe's missing heat. Seniors whose open incident came from the watch or the app (Dumitru, Teodor, Viorica, Gavril, Margareta) get quiet earlier calls, so their incident dossier has a briefing.
- Across the cast, the latest versions should show each trend direction at least once besides Eugenia's `worse`: at least one `better` (Ana fits) and one `steady`. Most seniors have no trend: a trend needs two to four cited calls (`Trend.evidence`).
- Campaigns skip a senior with an unresolved incident (03 §8), so every added campaign call is dated before that senior's incident opened.
- Romanian agrees in gender („doamna”/„domnul”, „căzută”/„căzut”). Write each line for its senior; don't template it.

### 4.5 Seeded summaries pass the writer's own checks

One test walks every seeded `SummaryVersion` and asserts what the real writer enforces: each quote in a follow-up, trend or citation appears in a transcript of that senior's calls (after the same normalization the writer uses), each `call_id` is that senior's, and the content validates as `SummaryContent`. It also asserts that every seeded answered wellbeing call of an active senior has a version. On staging with `DEEPINFRA_API_KEY` set, `due_calls` would otherwise send any unsummarized seeded call inside its window to the paid model. That way a typo in seeded Romanian fails CI instead of showing a quote nobody said.

## 5. Constraints

- **No secrets or real people in Git** (AGENTS.md). `backend/cast.json` is already git- and docker-ignored.
- **Leave cloud environments alone.** Building this changes nothing on Railway. Setting `DIAL_ALLOWLIST`, `DEEPINFRA_API_KEY` and running either script on staging is the user's call, or done only when they say so.
- **Don't bypass the environment guards**. The new gate in `seed.py` gets tests like `test_seed_cast.py`'s: a laptop is refused a cloud database, `--confirm` must name the environment, production is refused.
- **User-facing text is Romanian**, code and comments English. Cite spec IDs in comments as the rest of the seed does.
- Any change under `backend/` redeploys staging's `api` after merge and drops live calls.

## 6. Outside this change, but the e2e run fails without them

- **`DEEPINFRA_API_KEY` on staging.** Without it no summaries are written (commit `77077b7`), so the main thing under test is silently missing.
- **Twilio trial accounts call only verified numbers.** All four numbers need verifying in Twilio, A's included, because the hand-over rings A.
- **Real-SMS sign-in on the devices.** #50 hit Play Integrity and `TOO_MANY_ATTEMPTS` before.
- **`DIAL_ALLOWLIST`** on staging set to the four numbers.
- **Revoke any DAS grant on staging** held by anyone but A and B (test numbers, `DAS Test`, `Cristian Pavel`). Check the staff list on the dashboard after seeding.
- **Campaign clutter is accepted** *(decided with the user)*. A campaign started on staging queues calls for every active fictional senior too. The allowlist keeps them silent, they sit queued in the campaign's progress, and they settle when the warning lapses. „Sunați-mă” and the watch reach only C or D.

The backend README's "Seed the cast" section documents the new file shape, the staging `seed.py` run, and this checklist.

## 7. Done when

- Locally: `seed.py --reset` runs, every active fictional senior with answered calls has a briefing on the dashboard, and the trend notes show `worse`, `better` and `steady` across the cast.
- The seeded-summaries test (§4.5), the `seed.py` gate tests and the new `seed_cast.py` shape tests pass. `uv run pytest`, `ruff` and `lint-imports` are green.
- `seed_cast.py` with a made-up four-person file in the new shape gives A das+medic on duty, B das+caregiver, and C and D submitted with their medic and caregivers. A second run adds nothing.
- On staging, once the user runs it: C's phone rings for the welcome call after A accepts, and after a wellbeing call the dashboard shows the summary the model wrote.

## 8. Left to the builder

- Story text, the number of added calls per senior, and their dates, within §4.4.
- How `check_target` is shared.
- Field names inside the new cast shape, beyond what §4.1 fixes.
