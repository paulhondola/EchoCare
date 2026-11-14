# Security and GDPR: team brief for the pitch

Internal. What helps us, what hurts us, and how to answer when a judge asks. Every claim below was checked against the code on 2026-11-14, not only the spec. The judge-facing one-pager is a separate page that leads with the strengths.

## The 30-second answer

> EchoCare handles health data about vulnerable people, so we designed for that from day one. There is one door to the data: only our server touches the database, and it checks on every request who you are and whether you may see this senior. Nobody picks their own role. A medic or DAS grants it. We store as little as we can: no audio ever, watch readings for 24 hours, location only with an alarm. Everything runs in the EU. Consent is the senior's own, recorded with exactly what they agreed to. And if a senior or their family asks, one button erases everything we hold about them. What we haven't done yet is the paperwork a real pilot needs: processor agreements, a DPIA, retention periods. We know exactly what's on that list.

The last two sentences matter. Judges who ask about GDPR are checking whether we know the gaps, not whether there are none.

## What works for us

### Security

| Claim | Where it's true | Pitch line |
|---|---|---|
| One door to the data | Only FastAPI reaches Postgres, over Railway's private network (01 §5, G2). No Firestore, no direct client queries | "There's one place to get permissions right, not five." |
| Every request is verified | `auth/service.py`: Firebase ID token verified on each call; the phone number in the token is looked up against grants. No token: 401. No grant: 403 and nothing stored | "Signing in proves who you are. It gives you no access." |
| Roles are granted, never chosen | Grants are created by the setup script (DAS), DAS (medics), medics (seniors, caregivers) (01 §6) | "You can't sign up for EchoCare. Someone responsible has to add you." |
| You can't probe for data | A senior outside your reach answers `not_found`, the same as an ID that doesn't exist (01 §6). Dozens of tests cover refusals and other people's seniors | |
| Twilio can't be spoofed | Every callback and the live-call WebSocket check Twilio's HMAC signature with a constant-time compare (`voice/twilio.py`); unsigned WebSocket connects are closed before accept. The call ID in the address is single-use | "A fake 'the senior said they're fine' request is rejected." |
| Devices hold no secrets | The watch and the home node have no identity, no keys, no Wi-Fi password. They talk only to the senior's phone (watch: Data Layer, same signing key; node: bonded BLE) (01 §6) | "Steal the sensor box and you get a temperature sensor." |
| The AI can't act on its own | The status engine is pure code; the model only extracts answers. Alarm phrases are matched by the server before the model sees a sentence. The model can't place a call, set a code or choose who is alerted (01 §8, 06 §4) | "The AI talks. Fixed rules decide." |
| Medical-record AI is checked twice | The analyzer must quote the record word for word as evidence, and the server checks that the quote really appears (`medical/analyzer.py`); the record is passed as data with an explicit "not instructions" fence. The medic confirms before any question is used | Anti-hallucination and human in the loop, in one sentence |
| Secrets stay server-side | Twilio, model and Firebase credentials live in Railway variables only (06 §4). `.env`, keystores and `local.properties` are git-ignored | |
| Laptops can't touch the cloud | `check_environment()` and `alembic/env.py` refuse to run a scheduler or migration against a cloud database from a laptop; a Railway deploy missing `APP_ENV` refuses to start | Good for technical judges: safety rails, not just good intentions |
| Demo shortcuts are fenced off | The mock call endpoints answer `not_found` in production (`calls/mock.py`); the dialer rings only numbers on `DIAL_ALLOWLIST` | |
| Browser access is pinned | CORS allows only the dashboard's own origin (`core/settings.py`) | |
| Logs don't leak | Phone numbers masked (`+40700***009`), tokens never logged, medical text and summary quotes never logged; Pydantic AI instrumentation off and asserted by a test (06 §4) | |
| Right to erasure, built properly | `POST /seniors/{id}/erase`: every table's owner deletes its own rows in one transaction, children first, then the medical PDF leaves the file store. Refused while a call is live or an incident is open, so an emergency can't be erased mid-handling. One test fills every table and checks that nothing is left | "Erasure isn't a promise in a policy. It's a button, and a test proves it leaves nothing." |
| No gotchas | API docs off in production; security headers on the dashboard (framing blocked, HSTS, no sniffing); Android backup and device transfer off, so a session can't be restored elsewhere; Dependabot and dependency audits in CI | |
| Tested | Over 700 backend test functions (more cases with parametrisation), including the rule engine cell by cell, signature checks and access refusals; lint, import contracts and tests run in CI and on commit | |

### GDPR

| Principle (article) | What we do |
|---|---|
| Data minimisation (5(1)(c)) | No audio stored anywhere in our systems: Twilio turns speech into text. Watch readings deleted after 24 h (ADR-006). Home node: latest reading only, no camera, no microphone. Location only attached to an alarm event, no tracking |
| Need-to-know access (5(1)(f), 25) | Caregivers see the code, reason and address, never the transcript or medical record. The medical record goes to DAS only after the medic confirms it (01 §6 table) |
| Privacy by design (25) | Push notifications carry generic text and an ID, no health details (P18). Pre-signed PDF links expire after 10 minutes |
| Demonstrable consent (7(1)) | Consent is a history, never overwritten: each row stores the text version agreed to and the evidence (the key press, or the words and Twilio's confidence) (05 §2). Refusal and withdrawal are recorded the same way |
| No automated decisions about the person (22) | The summary briefs the medic and DAS; it never sets a code, a call or a recipient. A red alert goes to a human dispatcher |
| EU hosting (Chapter V) | API, database and file storage on Railway EU West; Twilio processes the calls in Ireland (IE1) |
| Right to erasure (17) | DAS or the registering medic erases a senior and everything about them in one action, the medical PDF included. Only a log line with the senior's ID and who erased it remains |
| Accuracy (5(1)(d)) | Every quote in a summary is checked to be the senior's own words; medical items need verbatim evidence |
| Audit trail | Status reports record every severity reached, with its source and the senior's words, so every code can be explained (05 §2) |

## What works against us

Ordered by how likely a judge is to raise it.

| # | Gap | Severity for the pitch | Honest answer |
|---|---|---|---|
| 1 | **Processors outside the EU.** DeepInfra (the language model, US company) reads transcripts and medical records; Firebase (Google) sees phone numbers. No processor agreements (Art. 28) signed | High: the most predictable question | "For the demo, fictitious data only. For a pilot: DPAs with all four processors, and either an EU-hosted model or a provider under the EU-US Data Privacy Framework or SCCs. The model sits behind one OpenAI-compatible endpoint, so swapping in an EU-hosted model is a config change." |
| 2 | **Retention is "kept" with no end date** for transcripts, events, summaries and incidents (05 §5) | Medium | "Retention periods are the data controller's call (DAS). The mechanism already exists: watch readings expire after 24 h. Adding a period to transcripts is the same job." |
| 3 | **Consent questions the spec itself leaves open.** Is a spoken "da" explicit consent for health data (open question 7)? Today's consent text doesn't cover the summary, which is profiling (open question 14). Medical analysis starts at `accepted`, before the welcome-call consent | Medium–high | See "Legal basis" below. The strongest answer is that consent may not be the right basis at all for a public social service |
| 4 | **Capacity to consent.** Some seniors have cognitive decline; a phone "da" from them is weak consent | Medium, from the medically minded | "The medic who knows the patient registers them and sees the consent result; a refusal or unclear answer goes back to the medic in person." |
| 5 | **No access log.** We log refusals, but not who read which senior's transcript. DAS sees all submitted seniors | Medium for security judges (Art. 32 for health data) | Fixable in a few hours; see below |
| 6 | **SMS-only sign-in for staff.** A DAS account sees every senior; SIM swap is the known weakness of SMS login | Medium | "Pilot: a second factor for DAS and medics. Seniors and caregivers keep SMS because it's what they can use." |
| 7 | **No rate limiting, no Firebase App Check.** The API has no per-caller limits; anyone can call it with a valid token as hard as they like | Low–medium | Railway sits in front; an unregistered number gets a 403 at the first query. Still worth adding |
| 8 | **No DPIA, no records of processing (Art. 30, 35).** Large-scale health data of vulnerable people with new technology almost certainly requires a DPIA | Medium if asked, but a cheap document | Write a one-page DPIA outline; showing it on a slide is strong |

## Legal basis: the answer that turns a weakness into a strength

Consent (Art. 6(1)(a) + 9(2)(a)) is fragile for seniors: it has to be explicit, freely given and withdrawable, and capacity is questionable. A public social-assistance directorate (DAS) providing social care may instead rely on **public task (Art. 6(1)(e))** together with **health or social care (Art. 9(2)(h))**, under professional secrecy, with the medic involved. Consent then stays as an ethical and transparency step, which is what the welcome call already does.

How to say it: "Legally, DAS as controller would most likely rely on its public-care mandate, not consent alone. We still ask every senior on the first call, record the exact text they agreed to and let them withdraw, because respecting the person matters beyond the legal minimum." **Say this only as our understanding; we are not lawyers. A pilot needs DAS's DPO to confirm it.**

## Judge Q&A

### Non-technical judges

**"Is my grandmother's data safe?"**
Only the people who need it see it: her doctor, the dispatchers, and family who only see whether she's OK and where she lives. We never record her voice. Nobody can join EchoCare on their own; her doctor adds her.

**"Who owns the data?"**
DAS, the social-assistance service, is the data controller. We are the technology. The data sits in Europe.

**"What if she says no, or changes her mind?"**
She's asked on the very first call. If she says no, nothing starts. If she withdraws later, calls stop at once. (Gap: today the medic or DAS records the withdrawal; saying "stop" on a call is on the roadmap.)

**"Does the AI decide if she's in danger?"**
No. The AI holds the conversation. Fixed, tested rules decide the colour, and a red always goes to a human dispatcher who talks to her.

**"Isn't it creepy, a watch and sensors watching her?"**
The watch keeps one day of pulse readings, then deletes them. The home box measures temperature and motion: no camera, no microphone. Location is only sent with an alarm.

### Technical judges

**"How do you authenticate and authorize?"**
Firebase phone auth proves the number; FastAPI verifies the ID token on every request and maps the number to grants in our own database. Authorization is per endpoint and per senior, server-side only; the app's role screens are cosmetic. Out-of-scope resources return 404, not 403.

**"How do you trust Twilio's webhooks?"**
HMAC-SHA1 signature on every callback and on the WebSocket upgrade, compared in constant time, URL rebuilt from `PUBLIC_BASE_URL` because of the proxy. The relay call ID is single-use.

**"Prompt injection? A senior or a PDF telling the model to do something?"**
The model has no tools that act on the world. Alarm phrases are matched before the model; the status matrix is pure code with no model in it. The medical record is fenced as data, and every extracted item must quote the record verbatim, checked by the server, then confirmed by a medic.

**"Where does health data go?"**
Postgres and S3 on Railway EU West. Speech goes to Twilio IE1. Transcript text and medical text go to DeepInfra for the model. That last one is the known non-EU hop (gap 1).

**"Encryption?"**
TLS everywhere in transit (Railway HTTPS, Twilio WSS). At rest it's whatever Railway's managed Postgres and storage give us; we don't add field-level encryption. Medical PDFs are in a private bucket, reached only through 10-minute pre-signed URLs. (Don't claim more than that.)

**"What happens during a deploy, could data get mixed?"**
Migrations only add; old and new copies share the schema. A database advisory lock keeps one scheduler running.

**"GDPR erasure?"**
Yes: DAS or the medic presses one button, and everything about the senior goes, the PDF included. Each table's owner deletes its own rows in one transaction, children first, and a test fills every table and checks nothing is left. The Firebase sign-in record is the one thing we can't delete yet: the API deliberately holds no Firebase credential.

## Candidate fixes

Done on 2026-11-14 (branch `security-erasure`): API docs off in production, Android backup off, the PDF deleted with a draft, Dependabot and audits, dashboard security headers, and erasure. What's left, grouped by cost:

**Minutes each**
- Update the dependencies the audits flag: `certifi`, `opentelemetry-api`, `pyasn1` in the backend; 5 high-severity npm advisories in the dashboard

**Hours (strong pitch value)**
- **Export for any senior** (Art. 15, 20): the same walk over the owners as erasure, reading instead of deleting
- **Access log**: who read which senior's transcript or medical record, and when. Visible in the dashboard, it's a demo moment in itself
- **Retention job**: the scheduler already deletes 24-hour watch readings; extend it with a configurable period for transcripts and events
- Rate limiting per caller

**Documents (no code, high value)**
- One-page DPIA outline and Art. 30 record of processing: purposes, data categories, recipients, processors, retention, transfers
- Consent text `v3` that covers the summary and the medical record; gate the medical analysis on consent, or rely on the Art. 9(2)(h) basis and say so

**Bigger (pilot, not hackathon)**
- EU-hosted model, signed DPAs, a second factor for staff, Firebase App Check, withdrawal by voice on any call
