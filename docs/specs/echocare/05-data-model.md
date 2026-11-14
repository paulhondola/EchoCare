# 05 · Data model

Part of the [EchoCare specification](README.md). One PostgreSQL database holds everything, and only FastAPI reaches it (G2, G8). Tables are defined in FastAPI's models (SQLAlchemy 2) and changed through migrations (Alembic).

Field lists are indicative: they show what each entity must carry, not final column names.

## 1. Entities and relationships

```mermaid
erDiagram
    USER ||--o{ GRANT : "holds"
    USER ||--o{ PUSH_TOKEN : "has"
    USER ||--o{ SENIOR : "registers, as medic"
    USER |o--o{ SENIOR : "accepts, as DAS"
    SENIOR ||--o{ GRANT : "is followed through"
    SENIOR ||--o{ CONSENT : "gives or refuses"
    SENIOR ||--o| WATCH_STATE : "wears"
    SENIOR ||--o| MEDICAL_RECORD : "has"
    SENIOR ||--o{ WATCH_READING : "checked in, last 24 h"
    SENIOR ||--o| HOME_NODE_STATE : "has at home"
    SENIOR ||--o| SENIOR_STATUS : "has current, once active"
    SENIOR ||--o{ INCIDENT : "has, one per red"
    CALL |o--o{ INCIDENT : "opened or added to"
    USER |o--o{ INCIDENT : "takes, resolves"
    SENIOR ||--o{ CALL : "receives"
    SENIOR ||--o{ EVENT : "sends, through the phone app"
    CAMPAIGN ||--o{ CALL : "queues"
    EVENT }o--o| CALL : "attached to"
    CALL ||--o{ CALL_TURN : "contains"
    CALL ||--o{ ANSWER : "yields"
    CALL ||--o{ STATUS_REPORT : "produces"
    CALL |o--o{ CONSENT : "records"
    SENIOR ||--o{ SENIOR_SUMMARY : "is summarized in"
    CALL ||--o| SENIOR_SUMMARY : "yields at most one"

    USER {
        uuid id PK
        string phone_e164 UK "+40..."
        string display_name
        string firebase_uid "empty until first sign-in"
        string practice "medics only"
        boolean on_duty "DAS only, true for one row at most"
        datetime created_at
    }
    GRANT {
        uuid id PK
        uuid user_id FK
        string role "das, medic, caregiver, senior"
        uuid senior_id FK "caregiver and senior grants"
        string relation "caregiver grants"
        uuid granted_by FK "empty for the setup script"
        datetime created_at
    }
    SENIOR {
        uuid id PK
        uuid medic_id FK
        string full_name
        string form_of_address "doamna Maria"
        string phone_e164
        boolean phone_is_landline "worked out from the number"
        string street
        string street_number
        string block
        string staircase
        string floor
        string apartment
        string intercom_code
        string key_holder
        string landmark
        string call_window "collected, unused in MVP"
        string_array equipment "smartphone, watch, home_node; null = not stated"
        string enrollment_state "draft, submitted, accepted, active, refused, wrong_number, unreachable, withdrawn"
        datetime submitted_at "the medic's submit; empty for a draft"
        datetime accepted_at "DAS's accept; empty before it"
        uuid accepted_by FK "the DAS user who accepted"
    }
    CONSENT {
        uuid id PK
        uuid senior_id FK
        string decision "given, refused, withdrawn"
        string method "call, signature, medic, das, app (the mock card)"
        string text_version
        uuid call_id FK "for methods call and app"
        json evidence "keys or words, Twilio confidence"
        json signature_strokes "for method signature"
        uuid recorded_by FK "for method signature, medic or das"
        datetime at
    }
    SENIOR_SUMMARY {
        uuid id PK
        uuid senior_id FK
        uuid call_id FK UK "the call this version came from"
        uuid previous_id FK "the version it was built on"
        json content "follow_ups, how_to_talk, trends, narrative"
        string model "the model name that wrote it"
        datetime created_at "the newest is the latest"
    }
    WATCH_STATE {
        uuid senior_id PK
        string state "ok, not_worn, offline"
        datetime last_check_in_at
        int battery
        boolean worn
        int last_pulse
        int resting_pulse
        int steps_today "since local midnight on the watch"
        int minutes_without_steps
    }
    WATCH_READING {
        bigint id PK
        uuid senior_id FK
        datetime measured_at "unique with senior_id"
        int pulse
        int resting_pulse
        int steps_today
        int battery
        boolean worn
    }
    HOME_NODE_STATE {
        uuid senior_id PK
        string state "ok, offline"
        datetime last_reading_at
        float temperature_c
        float humidity_pct
        datetime last_motion_at
        float forecast_60m_c "the node's prediction, P26"
        datetime out_of_range_since "empty while in range"
        boolean out_of_range_event_sent "one room event per stretch"
    }
    EVENT {
        uuid id PK "generated on the device"
        uuid senior_id FK
        string type "high_pulse_at_rest, inactivity, sos_button, fall, room_cold, room_heat, manual_request"
        string source "watch, home_node, phone"
        datetime measured_at
        datetime received_at
        json snapshot
        float latitude
        float longitude
        float location_accuracy_m
        datetime located_at
        uuid call_id FK "optional"
    }
    CAMPAIGN {
        uuid id PK
        string kind "heat or cold"
        string level "yellow or red warning"
        uuid started_by FK
        datetime started_at
        datetime warning_until "end of the active warning: 24 hours after the start, earlier if DAS ends it"
    }
    CALL {
        uuid id PK
        uuid senior_id FK
        string trigger "campaign, watch, home_node, manual, welcome, test (a scripted spike call, counted by no rule)"
        uuid campaign_id FK "optional"
        uuid previous_call_id FK "set on a redial"
        int attempt
        string starting_severity
        string state "queued, ringing, in_progress, completed, handed_over, dropped, unanswered, failed, canceled (a queued call that never went out)"
        datetime due_at
        datetime dialed_at "set when the scheduler hands the call to Twilio, committed before Twilio is asked; null for a call never dialed"
        string twilio_call_id
        datetime started_at
        datetime ended_at
        string final_severity
        string final_certainty
        string reason
        text summary
        string welcome_outcome "welcome calls: confirmed, not_available, wrong_number, no_answer"
        boolean handover_answered "set when DAS picked up"
    }
    CALL_TURN {
        uuid id PK
        uuid call_id FK
        int position
        string speaker "senior, agent, system, das"
        string kind "speech or keys"
        text content
        float confidence "from Twilio, when given"
        datetime at
    }
    ANSWER {
        uuid id PK
        uuid call_id FK
        string field "feeling, orientation, shelter"
        string value
        boolean clear
        text quote
        datetime at
    }
    STATUS_REPORT {
        uuid id PK
        uuid call_id FK
        string source "rules, raise_concern, alarm_tier1, alarm_tier2, request_human, trigger, unanswered, home_temperature"
        string severity
        string certainty
        string reason
        text quote
        datetime at
    }
    SENIOR_STATUS {
        uuid senior_id PK
        string code "green, yellow, red"
        string reason
        datetime since
        uuid source_call_id FK
    }
    INCIDENT {
        uuid id PK
        uuid senior_id FK
        uuid opened_by_call_id FK
        string status "open, in_progress, resolved"
        string reason
        datetime opened_at
        uuid taken_by FK
        datetime taken_at
        uuid resolved_by FK
        datetime resolved_at
        string outcome "senior_ok, team_sent, called_112, not_reached, false_alarm"
        text note
    }
    MEDICAL_RECORD {
        uuid id PK
        uuid senior_id FK "unique"
        text storage_key "S3 key of the PDF"
        uuid uploaded_by FK
        datetime uploaded_at
        string state "pending, review, confirmed, failed"
        text source_text "extracted text, never logged or served"
        jsonb items "condition, question, worrying, evidence, included"
        string model
        datetime analyzed_at
        datetime confirmed_at
        uuid confirmed_by FK
    }
    PUSH_TOKEN {
        uuid id PK
        uuid user_id FK
        string token
        datetime updated_at
    }
```

## 2. What each entity is for

| Entity | Purpose |
|---|---|
| User | One row per phone number that has been granted anything. Created at grant time, before the person signs in; the Firebase account is attached at first sign-in. A DAS user's phone is also their hand-over number |
| Grant | One role for one user, and for caregiver and senior grants the senior it applies to. A user may hold several. Replaces the earlier role field, caregiver link and invite |
| Senior | The enrolled person, registration details, structured address and enrollment state |
| Consent | Every consent decision as a history: given or refused on the welcome call (or on the mock card in the senior's app, method `app`), an optional signature, a withdrawal recorded by the medic or DAS. For method `call`, `evidence` holds what decided it: `{"digits": "1"}` for a key, or `{"speech": "Da.", "confidence": 0.91}` for words (#48) |
| SeniorSummary | One version of what the summary agent knows about a senior, written after each answered call from that call and the version before it. Never updated or deleted by the app; the newest is the latest (design `2026-11-08-senior-summary-agents` §4) |
| MedicalRecord | A senior's medical record PDF and the check questions drawn from it, one current row per senior; a new upload replaces its content and resets `state` (`pending`, `review`, `confirmed`, `failed`). `items` is a JSONB list of `{condition, question, worrying, evidence, included}`; `source_text` is the extracted text, kept for re-analysis and never logged or served (design `2026-11-13-medical-record-profile` §5.1) |
| WatchState | The watch's latest check-in, one row per senior |
| WatchReading | One check-in, kept 24 hours for the dashboard's pulse line (ADR-006) |
| HomeNodeState | The home node's latest room reading and when the room went out of range, one row per senior with a node **(P20, proposed)** |
| Event | A watch anomaly, a fall, a button press on the watch or the home node, a room out of range, or a "Sunați-mă" request, with its source and the phone's last known location if it had one |
| Campaign | One press of the weather-warning button, and the active-warning period it opens: 24 hours from the press, cut short when DAS ends the campaign |
| Call | One attempt to reach a senior, with its outcome. Also the scheduler's queue: a queued call with a due time is a pending timer |
| CallTurn | The transcript, one row per utterance or key press, in the order said: the senior, the agent, the system, and after a hand-over the DAS employee |
| Answer | What the model extracted for one of the three questions |
| StatusReport | Every severity reached during a call, with its source and the senior's words. The audit trail behind a code |
| SeniorStatus | The current code, one row per active senior |
| Incident | DAS's handling of one red or one hand-over: opened when the red is established or the call is handed over, taken by a person, resolved with an outcome and a note (G16). A later red or hand-over while it is still open is added to it, through the call |
| PushToken | Where to deliver pushes for a user, one row per device |

FastAPI writes every entity. Apps change data only through the endpoints in [04-interfaces.md](04-interfaces.md).

## 3. Constraints in the database

Several rules from the other files are enforced by the database itself, so they hold even if the code has a bug.

| Rule | Constraint |
|---|---|
| One person per phone number | Unique `user.phone_e164` |
| At most one DAS employee on duty (P10) | A unique index over `user` limited to rows where `on_duty` is true |
| Never two live calls for one senior | A unique index over `call.senior_id` limited to rows in `queued`, `ringing` or `in_progress`. A command that hits it returns the existing call |
| An event is processed once | `event.id` is the primary key; inserts ignore a duplicate |
| One room event per out-of-range stretch | `home_node_state.out_of_range_event_sent` is set in the same transaction that inserts the event, only where it was false |
| One medical record per senior | Unique `medical_record.senior_id` |
| One grant per role and senior | Unique (`user_id`, `role`, `senior_id`) |
| One current code per senior | `senior_status.senior_id` is the primary key |
| At most one unresolved incident per senior | A unique index over `incident.senior_id` limited to rows in `open` or `in_progress` |
| An incident is taken once | Taking updates the row only where `status` is still `open`; a second taker changes nothing and is told who has it |
| At most one senior grant per user ([auth-layer.md](../auth-layer.md) AL7), so one mobile number signs in as one senior ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE10) | A unique index over `grant.user_id` limited to rows with role `senior`. Saving a second senior with that mobile is refused with `phone_taken` |

## 4. Notes on specific choices

**The user row exists before sign-in.** Signing in is a lookup by phone number that fills `firebase_uid` the first time. A number with no row is refused and nothing is stored. The phone number stays the lookup key; if a different Firebase account later signs in with the number, `firebase_uid` is replaced and a warning logged ([auth-layer.md](../auth-layer.md) AL4).

**The current code is its own row.** Apps read `SeniorStatus` constantly and `Call` rarely. Keeping the code separate makes the most frequent read a single-row lookup.

**The call table is the timer store.** Redials, welcome-call retries and campaign calls are rows in `queued` state with a `due_at`. Nothing is held only in memory, so a restart of the FastAPI service picks up where it left off. A queued call that will never go out, because its campaign ended, its warning lapsed or the senior withdrew consent, becomes `canceled`: an ended state, not live, so it frees the senior's slot for the next call ([03-status-model.md](03-status-model.md) section 9).

**`dialed_at` says a call was handed to Twilio.** The scheduler sets it and commits before it asks Twilio, so a crash or a timeout can leave a dialed call without a `twilio_call_id` but never lets it be dialed twice. It decides four things: the dialer picks only queued calls without it; cancelling (a lapsed or ended campaign, a withdrawal) touches only calls without it, since a dialed call ends through Twilio; the mock card ignores a dialed call and `POST /calls/{id}/mock-answer` refuses it (`wrong_state`); and the sweep counts a call as stuck from it (06 §2). A scripted `test` call is stamped as it is created, so the scheduler never picks it up. The column is nullable and added only, so old copies, which have no scheduler, ignore it (ADR-001 §2.3).

**"Sunați-mă" is stored as an event.** It enters the same path as a watch anomaly (D9), with type `manual_request`.

**The code and the incident are separate.** The code is what the rules concluded about the senior; the incident is what DAS did about it. Only the rules write the code; only DAS employees move an incident, apart from the automatic take when the hand-over is answered.

**Answers and status reports are separate.** An answer is what the senior said; a status report is what the rules concluded from it. Both are kept, so a code can be explained from the senior's words.

**Consent is a history, not a field.** A withdrawal is a new row, and the text version shows exactly what was agreed to.

**The latest check-in, plus 24 hours of readings.** The watch state holds the latest check-in; `watch_readings` keeps each check-in for 24 hours, so DAS can see the pulse trend behind an alert ([ADR-006](../../adr/ADR-006-das-sees-watch-health.md)), and the scheduler deletes older ones. Nothing older is kept; the system stores the minimum health data that serves its purpose. The home node keeps only its latest room reading, and a room event keeps the reading that caused it as its snapshot.

**Location is stored only with an event.** There is no location history apart from the moments the senior's phone reported an event.

**The call window is collected and unused.** v3's registration form asks for it and campaigns will need it later; the MVP's single immediate round ignores it.

**Risk factors are not stored.** Open question 5 in the README.

## 5. Retention

| Data | Kept | Reason |
|---|---|---|
| Audio | Never stored | Twilio handles speech; FastAPI receives text only |
| Transcripts, answers, status reports and senior summaries | Kept until the senior is erased | Medic and DAS review; audit of how a code was reached |
| Consent records | Kept until the senior is erased | Proof of what was agreed and when |
| Incidents | Kept until the senior is erased | What DAS did about each red, by whom, and the outcome |
| Events, with any location | Kept until the senior is erased | They explain why a call was placed and where the senior was |
| Check-ins | Latest, plus 24 hours of readings (ADR-006) | Data minimisation |
| Room readings | Latest only | Data minimisation |
| Grants | Removed when revoked | A removed caregiver loses access at once |

**Declared equipment** (design 2026-11-14). `seniors.equipment` holds what the medic ticked at registration (UC-01): `smartphone` (the EchoCare app on the senior's own phone, not merely a mobile), `watch` and `home_node`, in that order. `[]` means the senior only takes calls. `null` means not stated, for seniors registered before the field existed, and every screen treats it as before. An edit that leaves it out or sends null keeps it, so a senior never goes back to `null`.

**Erasure** (GDPR Art. 17, design 2026-11-14). `POST /seniors/{id}/erase` ([04-interfaces.md](04-interfaces.md) §2) deletes the senior and every row about them in one transaction, each table through its owner (ADR-005), children first: status reports and the code, events and incidents, consents, summaries and watch data, calls with their turns and answers, the medical record, the senior, and the users of the senior and caregivers left with no grant, unless another row still names them (a former medic or DAS employee). The medical record's PDF is deleted from the file store after the commit. In our database and file store, only a log line with the senior's id and who erased it remains. Outside our database and file store, Twilio's call logs (numbers and times), database backups until they rotate, and the Firebase sign-in account (auth-layer AL11) are not touched; a pilot needs a retention setting or a deletion request for each. It is refused while a call is live or an incident unresolved.

The demo uses fictitious people only. Retention periods for a real pilot are out of scope here and need a decision with DAS as data controller.
