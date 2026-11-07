# Real welcome and wellbeing calls, and the hand-over to DAS — design

Date: 2026-10-26. Status: drafted from [issue #48](https://github.com/paulhondola/EchoCare/issues/48) and four decisions taken with the user; approved 2026-10-26. Builds on #47 (PR #55), whose dialer places the calls.

## Intent

Real phone calls replace the mock card end to end. Today a dialed welcome call says one stand-in sentence and hangs up, so a senior reached by phone stays `accepted` forever, and a wellbeing call can only echo what it hears. This change gives the welcome call its UC-04 steps, so consent is recorded by key or by voice. It gives a wellbeing call its greeting and a way out to a person. When the senior presses 9 or says a tier 1 alarm phrase, the call is handed to the on-duty DAS phone, and answering that phone takes the incident. It is proven on the local stack with the team's phones, through the ngrok tunnel.

## Goals

- The welcome call asks identity, then consent, by key or by voice (`<Gather>`). Its outcome makes the senior `active` with code green, `refused`, `wrong_number` or `unreachable`, through the same `calls.ending.conclude_welcome` the mock card uses.
- A wellbeing call connects to ConversationRelay with a greeting built from its trigger, and names the hand-over address.
- Key 9, at any point in a wellbeing call, starts a hand-over (04 §5). A tier 1 alarm phrase does too, and makes the code red at once (your call: tier 1 is in this change).
- **Every hand-over opens an incident** (your call), or joins the senior's unresolved one, so the DAS phone that rings already shows who is calling. Answering takes it for the on-duty employee.
- The hand-over dials the on-duty phone with its ring time. Nobody on duty, or nobody answering, gets a spoken message and a hang-up.
- Twilio's real callback bodies, recorded on the local stack, replace the documented ones in the test fixtures.

## Done when

On the local stack with the ngrok tunnel and the team's phones:

- Accepting a senior rings their phone. Pressing 1 twice records consent by key, and the senior shows `active` with code green.
- A wellbeing call where the senior presses 9 rings the on-duty phone. Answering it shows the incident as taken by that employee on the dashboard.
- Saying „am căzut” on a wellbeing call turns the senior red and rings the on-duty phone the same way.

The same on staging is the person's run (see Non-goals).

## Non-goals

- **Staging** (your call). This change touches no Railway environment. A person sets staging's Twilio variables, applies `.railway/railway.ts`, and runs S1, S3, S8 and S11 there. The 06 §6 answers are written from the local runs and from what the person reports.
- **The model's side of the conversation.** A wellbeing call still echoes what it hears after its greeting, as the S1 session does, until the agent loop issue. An answered wellbeing call that ends `completed` still sets no code.
- **Tier 2 phrases.** The confirmation question of 03 §4 belongs with the agent loop. A tier 2 match is kept in the transcript and acts on nothing here.
- **The medic's „Sună din nou”** (`POST /seniors/{id}/welcome-call`, 04 §2). A senior who ends `wrong_number` or `unreachable` waits for it. *My call:* it is listed in the spec but not in #48; a follow-up.
- **Push alerts** on red or on a hand-over. No push sender exists yet.
- **The caregiver notice SMS** (S10, 04 §4.5) and inbound calls.

## Anti-goals

- A consent recorded from anything but key 1, or an exact „da” or „sunt de acord” (G7).
- A DAS phone that rings with no incident to show.
- A red lost because the line dropped between the phrase and the hand-over. The red, the report and the incident are written before the session is closed.
- The senior left in silence. Every branch says something in Romanian before it hangs up, and a failure says `SORRY`, never Twilio's English error.
- A real phone number in the repository, a commit, a doc or a fixture.

## Constraints

- Old clients and old copies talk to new servers (ADR-001 §2.3). `POST /voice/welcome` keeps its address, since calls dialed by the previous copy point there. No migration is needed: `calls.welcome_outcome`, `calls.handover_answered`, `consents.evidence` and the senior states `wrong_number` and `unreachable` already exist.
- Only a table's owner writes it (ADR-005): `calls` → `voice`, `seniors` and `consents` → `seniors`, `incidents` → `incidents`, `senior_statuses` and `status_reports` → `codes`. `calls/ending.py` composes their functions.
- Layers (`pyproject.toml`): `agent` imports only `voice` and `status`. The relay session cannot write a code or an incident itself. The router hands it a function that does (§4).
- Twilio's callbacks are all signed and checked, the new ones included: the `<Gather>` actions, the `<Connect>` action and the `<Dial>` and `<Number>` callbacks.
- Real numbers (your call): the demo cast's numbers go only into the local database and the git-ignored `backend/.env`, for live tests. Tests and fixtures use `+40700000xxx`. Recorded bodies have numbers and SIDs replaced before they are saved.
- User-facing text is Romanian. Code, comments and docs are English and cite the spec by ID.

## Design

### 1. Which flow answers

`POST /voice/answer` reads the call's trigger. A welcome call gets the welcome flow (§2); every other trigger gets the wellbeing flow (§3), and a `test` call keeps the S1 echo greeting. `POST /voice/welcome` stays and runs the welcome flow too, so the dialer's choice of address and the answer's choice agree. An unknown call, or a database that cannot be read, answers `SORRY` as today.

### 2. The welcome call (UC-04, G7)

A fixed script in TwiML, each question one `<Gather input="dtmf speech" numDigits="1" language="ro-RO" actionOnEmptyResult="true">` with its `<Say>` inside. The `<Say>` uses the configured voice (`TWILIO_TTS_PROVIDER` and `TWILIO_VOICE`, so `Google.ro-RO-Wavenet-A`), the same voice the relay speaks with (*my call*). Each `action` is a signed callback carrying `?call=<id>`, plus which try it is.

1. **Picked up.** The call moves to `in_progress` (a skip ahead from `ringing`, as the status callback would), then gets the identity question: „Bună ziua. Sunt asistentul automat al DAS Timișoara. Vorbesc cu {form of address}? Dacă da, apăsați 1 sau spuneți «da». Dacă {form of address} nu poate veni acum la telefon, apăsați 2. Dacă ați primit acest apel din greșeală, apăsați 3.”
2. **`POST /voice/welcome/identity`.** Key 1 or the exact word „da” → the consent question. Key 2 → not available. Key 3 → wrong number. Anything else, or silence: the first time, the question again, opened by „Nu v-am auzit.”; the second time, silent twice.
3. **The consent question** is `CONSENT_TEXT`, version `v1`, already in `voice/dialogue.py`.
4. **`POST /voice/welcome/consent`.** Key 1, or an utterance that is exactly „da”, „sunt de acord” or „da, sunt de acord” once normalized (diacritics and punctuation removed, as `status.alarms.normalize` does) → given. Key 2, or exactly „nu” or „nu sunt de acord” → refused. Key 0 → the text again, which does not count as unclear. Anything else, or silence: once more, then unclear twice. *My call:* the exact phrase list; S3 may widen or narrow it.
5. **Given or refused** goes through `conclude_welcome` with method `call`, text version `v1`, and the evidence in `consents.evidence`: the key or the words, and Twilio's `Confidence` for speech. Given makes the senior `active` with code green; refused makes them `refused`. The call then hears the anti-scam close and hangs up.

Every ending marks the call `completed` first, so Twilio's later `completed` does not turn it into `dropped` (03 §9). Then it says its sentence and hangs up:

| Ending | `welcome_outcome` | Then | Said (*my call*, wording to review) |
|---|---|---|---|
| Consent given | `confirmed` | senior `active`, code green | „Vă mulțumim. Vă rugăm să salvați acest număr. Nu vă vom cere niciodată bani sau date. La revedere.” |
| Consent refused | `confirmed` | senior `refused` | „Am înțeles. Vă rugăm să salvați acest număr. Nu vă vom cere niciodată bani sau date. La revedere.” |
| Key 2, not available | `not_available` | retry rule | „Vă mulțumim. Vom suna din nou mai târziu. La revedere.” |
| Key 3, wrong number | `wrong_number` | senior `wrong_number` | „Ne cerem scuze pentru deranj. La revedere.” |
| Silent twice at identity | `no_answer` | retry rule | „Nu v-am auzit. La revedere.” |
| Consent unclear twice | `confirmed` | retry rule | „Nu v-am înțeles. La revedere.” |

**The welcome retry rule** (UC-04's last rows, *my call* on the shared cap). It applies to the three "retry rule" rows above, and also to a welcome call that ends `unanswered` or `failed` through the status callback, voicemail detection or the sweep. It applies as well to one that ends `dropped`, a hang-up partway through the script, which is as good as silence (*my call*, added while planning). Today `settle` moves those and concludes nothing. Attempt 1 queues attempt 2 after the redial delay (20 minutes, 20 seconds in demo mode). Attempt 2 makes the senior `unreachable`. A senior who is no longer `accepted` (DAS withdrew them in between) is left as they are, with nothing written, as `conclude_welcome` already does.

Two more calls of mine:
- A welcome call that ends `unanswered` or `failed` gets `welcome_outcome` `no_answer`.
- The ending call is marked ended before its retry is queued, in the same transaction, so the retry never meets a live call for the same senior (05 §3).

### 3. The wellbeing call

The answer is `<Connect action="/voice/handoff?call=<id>"><ConversationRelay … welcomeGreeting=…/></Connect>`, with the attributes it has today. The greeting is built from the trigger (04 §4.2):

- **campaign:** „Bună ziua, {form of address}. Sunt asistentul DAS Timișoara. Vă sun pentru că azi e cod {galben | roșu} de {ger | caniculă}. Nu vă cer niciodată bani sau date. Cum vă simțiți azi?”
- **watch** (*my call* on the wording): „… Vă sun pentru că ceasul a semnalat ceva neobișnuit. Nu vă cer niciodată bani sau date. Cum vă simțiți?”
- **manual**, the senior's „Sunați-mă” (*my call*): „… Vă sun pentru că ați cerut să vorbim. Nu vă cer niciodată bani sau date. Cum vă simțiți?”
- **test:** the S1 greeting, unchanged.

The campaign's kind and level are read in the router's layer, since `voice` cannot import `campaigns`. After the greeting the session echoes, and key 0 ends it `completed`, as today.

### 4. Starting a hand-over

**What starts one.** Key 9 at any time, or a `prompt` whose sentence `status.alarms.check` finds tier 1, and only tier 1: a negated phrase is demoted to tier 2 and starts nothing (03 §4). A `test` call never hands over. Its key 9 and alarm phrases are echoed like anything else, since no rule counts a test call (05 §1) (*my call*, added while planning).

**What it writes, before anything is sent back.** One transaction, through a function the router passes into the session, built in `calls`:

- A status report: source `alarm_tier1` with severity red, or `request_human` with severity yellow.
- The code: red for tier 1. For key 9, at least yellow: it never lowers a code, so a red stays red.
- An incident, opened, or the senior's unresolved one joined (your call).
- The call ends `handed_over`, with the final severity and the reason.

Reasons (*my call*): tier 1 „A spus: «{the senior's words}»”, truncated to the column; key 9 „A cerut un operator (tasta 9)”. If the call is no longer `in_progress` when this runs, nothing is written and nothing changes: a second 9 is a no-op.

**What is said, then sent.** One `text`: „Vă conectez acum cu un operator, rămâneți pe fir.”, or `SELF_HARM_HANDOVER` for the `self_harm` condition. Then `end` with `handoffData`, a JSON string naming the call and the reason. Since the call is already `handed_over`, a hang-up during the line leaves it so (03 §9). The relay no longer marks a call `completed` when it sends an `end` carrying hand-over data.

### 5. The hand-over callbacks (04 §4.2, §4.4)

**`POST /voice/handoff`**, the `<Connect>` action. Twilio calls it whenever the session ends.

- No `HandoffData`: the session ended normally, so `<Hangup/>`.
- Otherwise it reads who is on duty (a read in `auth`):
  - Nobody on duty: „Un coleg vă va suna înapoi în cel mai scurt timp.”, then hang up.
  - The on-duty number is not on `DIAL_ALLOWLIST`: the same message, logged as refused, with the number masked (*my call*: the allowlist guards every number we ring, staff included).
  - Otherwise: `<Dial callerId=TWILIO_FROM_NUMBER timeout=… action="/voice/handoff-result?call=<id>"><Number url="/voice/handoff-answered?call=<id>&user=<on-duty user id>">…</Number></Dial>`. The timeout is the on-duty ring time: 30 seconds, 15 in demo mode (06 §3).

**`POST /voice/handoff-answered`**, the `<Number url>`, which Twilio fetches when the on-duty phone picks up and before it connects the two:

- It takes the call's incident for the user named in the address (`incidents.take`): `open` → `in_progress`.
- An incident already taken by someone, from the dashboard in the meantime, stays theirs.
- It sets the call's `handover_answered` to true, and answers an empty `<Response/>`, which connects.

**`POST /voice/handoff-result`**, the `<Dial>` action:

- `DialCallStatus` `completed`: `<Hangup/>`.
- Anything else (`no-answer`, `busy`, `failed`, `canceled`): `handover_answered` false, unless it is already true. Then the call-back message, and hang up. The incident stays open at the top of the dashboard.

The senior's own call keeps its `handed_over` state through all of this. Twilio's final `completed` for it changes nothing.

### 6. Fixtures and spikes

- **Fixtures.** The real bodies of every callback, the new ones included, are copied from the ngrok inspector's API (`http://localhost:4040/api/requests/http`) after the local runs. Numbers are replaced with `+40700000xxx`, and SIDs with placeholders of the same shape. They are saved into `backend/tests/voice/fixtures/twilio_callbacks.json`, keeping its existing keys and adding new ones. The tests sign them with their own token and address, as now.
- **S1** is answered from this session's local calls and the ones in this change: callbacks verify under the IE1 token, voicemail detection runs in IE1, `ro-RO` connects with Google `ro-RO-Wavenet-A`, speech comes back as text. How it sounds, and the alarm phrases' transcripts, are the person's to add.
- **S3** (does `<Gather>` in `ro-RO` hear „da” and „nu”?): tried locally on the demo phones, about ten tries each. If it misses often, the welcome call goes keys only and the consent phrase list is dropped (the issue's fallback). The person confirms it on staging.
- **S8 and S11** need Railway or several networks, and are the person's.
- Each answer goes into 06 §6 with its date.

### 7. Spec updates, in this change

- README G16 and 03's incident rule: a red, **or a hand-over**, opens an incident. 03 §10 example 9 accordingly.
- 02 UC-04: the stand-in paragraph is replaced by the real call and its retry rule. UC-07: key 9 opens an incident; the tier 1 path is built, tier 2 still to come.
- 04 §4.2:
  - The answer row branches on the trigger.
  - The welcome rows describe the real handler.
  - The hand-over rows: the `<Connect>` action, no data → hang up, the allowlist, the ring time, `<Number url>`.
- 04 §4.3: key 9 and tier 1 as built; tier 2 to come. 04 §4.4 step 5 names `<Number url>`.
- 05: the incident's opening rule; what `consents.evidence` holds for method `call`.
- 06 §6: the S1 and S3 answers.
- `backend/README.md` "Real calls locally" step 4: the welcome call is real.

## Tests

- **Answer.** A welcome call answered at `/voice/answer` gets the identity `<Gather>`. A campaign call gets `<Connect action>` with the campaign greeting, and a test call the S1 greeting.
- **Welcome.** Each answer combination replayed against the welcome callbacks with recorded bodies:
  - key 1 then key 1;
  - „da” then „da”;
  - „da, sunt de acord” then refused by key 2;
  - key 2;
  - key 3;
  - silent twice;
  - consent unclear twice;
  - key 0 repeats.
- **Welcome outcomes.** Given: senior `active`, code green, a consent with its evidence and `v1`. Refused: `refused`. Key 3: `wrong_number`. Retry rows: attempt 1 queues attempt 2 after the redial delay, and attempt 2 makes the senior `unreachable`. A welcome call ending `unanswered` through the status callback follows the same rule.
- **Welcome edge cases.** A later `completed` status callback leaves an ended welcome call `completed`. A senior withdrawn mid-call is left as they are.
- **Hand-over writes**, through scripted relay messages (06 §5):
  - Key 9 on a green senior gives yellow, a `request_human` report, an incident and `handed_over`.
  - Key 9 on a red senior leaves red and joins the unresolved incident.
  - Tier 1 gives red, an `alarm_tier1` report and an incident.
  - A negated tier 1 starts nothing.
  - A second 9 is a no-op.
  - A `self_harm` match speaks `SELF_HARM_HANDOVER`.
- **Hand-over callbacks.**
  - Nobody on duty: the message and a hang-up.
  - On duty and allowlisted: `<Dial>` with the ring time, `callerId` and `<Number url>`.
  - On duty but not allowlisted: the message.
  - No `HandoffData`: a hang-up.
  - Answered: the incident is `in_progress`, taken by that user, and `handover_answered` is true. Already taken by someone else: unchanged, and still `handover_answered`.
  - The result `no-answer`: `handover_answered` false and the message. `completed`: a hang-up.
- **Signatures.** Every new callback, signed badly, gets 403.
- Nothing reaches Twilio. Twilio's functions are patched where they are used, as in #47.

## Left to the builder

- Module layout and function names. Where the try counter lives in the `<Gather>` action address.
- `<Gather>` timeouts and `speechTimeout`, and speech hints.
- The shape of `handoffData` and of the evidence JSON.
- How the router passes the hand-over function into the session (an argument to `serve`, or to `Relay`).
- The truncation of a long tier 1 reason.
