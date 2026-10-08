# 05 · Data model

Part of the [Sentinela specification](README.md). One PostgreSQL database holds everything, and only FastAPI reaches it (G2, G8). Tables are defined in FastAPI's models (SQLAlchemy 2) and changed through migrations (Alembic).

Field lists are indicative: they show what each entity must carry, not final column names.

## 1. Entities and relationships

```mermaid
erDiagram
    USER ||--o{ GRANT : "holds"
    USER ||--o{ PUSH_TOKEN : "has"
    USER ||--o{ SENIOR : "registers, as medic"
    SENIOR ||--o{ GRANT : "is followed through"
    SENIOR ||--o{ CONSENT : "gives or refuses"
    SENIOR ||--o| WATCH_STATE : "wears"
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
        string enrollment_state "draft, submitted, accepted, active, refused, wrong_number, unreachable"
    }
    CONSENT {
        uuid id PK
        uuid senior_id FK
        string decision "given, refused, withdrawn"
        string method "call, signature, medic"
        string text_version
        uuid call_id FK "for method call"
        json evidence "keys or words, Twilio confidence"
        json signature_strokes "for method signature"
        uuid recorded_by FK "for method signature or medic"
        datetime at
    }
    WATCH_STATE {
        uuid senior_id PK
        string state "ok, not_worn, offline"
        datetime last_check_in_at
        int battery
        boolean worn
        int last_pulse
    }
    EVENT {
        uuid id PK "generated on the device"
        uuid senior_id FK
        string type "high_pulse_at_rest, inactivity, sos_button, manual_request"
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
        datetime warning_until "end of the active warning"
    }
    CALL {
        uuid id PK
        uuid senior_id FK
        string trigger "campaign, watch, manual, welcome"
        uuid campaign_id FK "optional"
        uuid previous_call_id FK "set on a redial"
        int attempt
        string starting_severity
        string state
        datetime due_at
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
        string speaker "senior, agent, system"
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
        string source "rules, raise_concern, alarm_tier1, alarm_tier2, request_human, trigger, unanswered"
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
| Consent | Every consent decision as a history: given or refused on the welcome call, an optional signature, a withdrawal recorded by the medic |
| WatchState | The watch's latest check-in, one row per senior |
| Event | A watch anomaly, a button press, or a "Sunați-mă" request, with the phone's last known location if it had one |
| Campaign | One press of the weather-warning button, and the active-warning period it opens |
| Call | One attempt to reach a senior, with its outcome. Also the scheduler's queue: a queued call with a due time is a pending timer |
| CallTurn | The transcript, one row per utterance or key press |
| Answer | What the model extracted for one of the three questions |
| StatusReport | Every severity reached during a call, with its source and the senior's words. The audit trail behind a code |
| SeniorStatus | The current code, one row per active senior |
| Incident | DAS's handling of one red: opened when the red is established, taken by a person, resolved with an outcome and a note (G16). A later red while it is still open is added to it, through the call |
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
| One grant per role and senior | Unique (`user_id`, `role`, `senior_id`) |
| One current code per senior | `senior_status.senior_id` is the primary key |
| At most one unresolved incident per senior | A unique index over `incident.senior_id` limited to rows in `open` or `in_progress` |
| An incident is taken once | Taking updates the row only where `status` is still `open`; a second taker changes nothing and is told who has it |

## 4. Notes on specific choices

**The user row exists before sign-in.** Signing in is a lookup by phone number that fills `firebase_uid` the first time. A number with no row is refused and nothing is stored.

**The current code is its own row.** Apps read `SeniorStatus` constantly and `Call` rarely. Keeping the code separate makes the most frequent read a single-row lookup.

**The call table is the timer store.** Redials, welcome-call retries and campaign calls are rows in `queued` state with a `due_at`. Nothing is held only in memory, so a restart of the FastAPI service picks up where it left off.

**"Sunați-mă" is stored as an event.** It enters the same path as a watch anomaly (D9), with type `manual_request`.

**The code and the incident are separate.** The code is what the rules concluded about the senior; the incident is what DAS did about it. Only the rules write the code; only DAS employees move an incident, apart from the automatic take when the hand-over is answered.

**Answers and status reports are separate.** An answer is what the senior said; a status report is what the rules concluded from it. Both are kept, so a code can be explained from the senior's words.

**Consent is a history, not a field.** A withdrawal is a new row, and the text version shows exactly what was agreed to.

**Only the latest check-in is kept (proposed).** There is no history of pulse readings; the system stores the minimum health data that serves its purpose.

**Location is stored only with an event.** There is no location history apart from the moments the senior's phone reported an event.

**The call window is collected and unused.** v3's registration form asks for it and campaigns will need it later; the MVP's single immediate round ignores it.

**Risk factors are not stored.** Open question 5 in the README.

## 5. Retention

| Data | Kept | Reason |
|---|---|---|
| Audio | Never stored | Twilio handles speech; FastAPI receives text only |
| Transcripts, answers and status reports | Kept | Medic and DAS review; audit of how a code was reached |
| Consent records | Kept | Proof of what was agreed and when |
| Incidents | Kept | What DAS did about each red, by whom, and the outcome |
| Events, with any location | Kept | They explain why a call was placed and where the senior was |
| Check-ins | Latest only | Data minimisation |
| Grants | Removed when revoked | A removed caregiver loses access at once |

The demo uses fictitious people only. Retention periods for a real pilot are out of scope here and need a decision with DAS as data controller.
