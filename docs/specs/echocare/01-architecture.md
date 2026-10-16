# 01 · Architecture

Part of the [EchoCare specification](README.md). IDs such as G2 and P10 refer to the decision log there.

## 1. Shape

One FastAPI service holds all data and everything that has consequences: phone calls, timers, events from the senior's phone, the rules and the matrix (G2). Every app, the DAS web dashboard included, talks only to FastAPI. Firebase does two narrow jobs: it proves that a person owns a phone number, and it delivers pushes. Apps never talk to each other, to Twilio or to the model. The watch and the home node talk only to the senior's phone.

## 2. System overview

Numbers on the arrows match the channel table in section 4.

```mermaid
flowchart TB
    subgraph EDGE["People and devices"]
        SP["Senior's phone<br/>any phone, landline included"]
        W["Wear OS app<br/>senior, optional"]
        HN["Home node, ESP32<br/>senior's home, optional"]
        SA["Android app<br/>senior role, optional"]
        CA["Android app<br/>caregiver role"]
        MA["Android app<br/>medic role, tablet"]
        DA["Android app<br/>DAS role, red incidents"]
        WD["Web dashboard<br/>DAS desk, Svelte"]
        DP["On-duty DAS phone<br/>also runs the DAS role"]
    end

    subgraph FB["Firebase"]
        AUTH["Phone sign-in<br/>SMS code"]
        FCM["Firebase push"]
    end

    subgraph RW["Railway, EU West"]
        API["FastAPI: reads, data entry,<br/>commands, event intake"]
        CORE["Dialer, call session,<br/>rules and status engine, notifier"]
        PG[("PostgreSQL")]
    end

    TW["Twilio<br/>Voice, ConversationRelay, SMS"]
    LLM["Model provider"]

    W <-->|"1 events, check-ins"| SA
    HN <-->|"12 readings, button, light"| SA
    SA & CA & MA & DA & WD -->|"2 sign in"| AUTH
    SA & CA & MA & DA & WD <-->|"3 HTTPS, JSON"| API
    API --> CORE
    CORE -->|"4 alert, refresh"| FCM
    FCM --> SA & CA & MA & DA
    CORE -->|"5 place call, SMS"| TW
    TW -->|"6 callbacks"| API
    TW <-->|"7 WebSocket, text both ways"| CORE
    CORE -->|"8 conversation turns"| LLM
    API & CORE <-->|"9 SQL"| PG
    TW <-->|"10 phone network"| SP
    TW <-->|"10 phone network"| DP
    API -->|"11 verify identity tokens"| AUTH
```

## 3. Parts

| Part | Role | Notes |
|---|---|---|
| Firebase phone sign-in | Proves a person owns a phone number | Holds no roles and no application data. A Firebase account is created automatically at first sign-in |
| Firebase push | Delivers alerts and refresh signals to Android apps | No health details in any message (P18) |
| FastAPI service | All reads and writes, calls, scheduling, event intake, the rules and the matrix | The only part that changes a code, makes a phone ring or touches the database |
| PostgreSQL | The single store | Reached only by FastAPI, over Railway's private network |
| Android app | One app, four roles | The roles granted to the signed-in number decide which screens appear. The medic layout targets a tablet and also works on a phone. The DAS role shows only red incidents (G15) |
| Web dashboard | DAS at the desk | Svelte 5 and SvelteKit 3 (ADR-003), built into a static site. Everything a dispatcher does: all seniors, incidents, enrollment requests, campaigns, staff and on duty. Re-reads every few seconds instead of receiving pushes |
| Wear OS app | Senior's watch | One screen and one background job. Talks only to the senior's phone app |
| Home node **(P20, proposed)** | Sensor box in the senior's home, optional | An ESP32 with a room temperature and humidity sensor, a motion sensor, an SOS button, a buzzer and a status light. Plugged into the mains, no battery. Talks only to the senior's phone app, over Bluetooth Low Energy. Measures and reports; FastAPI decides. Hardware in section 11 |
| Twilio | Phone network edge | Places calls, turns speech into text and text into speech (ConversationRelay), runs the welcome call's key-and-voice questions, bridges the hand-over, sends the caregiver notice SMS |
| Model provider | The language model behind the agent | Not yet chosen; see [04-interfaces.md](04-interfaces.md) section 5 |

## 4. Channels

| # | From → to | Means | Carries | Caller proves identity with |
|---|---|---|---|---|
| 1 | Watch ↔ senior's phone app | Wear OS Data Layer messages | Anomaly events, check-ins, acknowledgements | Same app, same signing key, paired devices |
| 2 | Apps and dashboard → Firebase sign-in | Firebase sign-in library, phone provider (with reCAPTCHA in the browser) | Phone number, SMS code, token renewal | The SMS code |
| 3 | Apps and dashboard → FastAPI | Web requests, JSON over HTTPS. The API accepts browser requests only from the dashboard's own address | Reads, data entry, commands, the senior's events and check-ins | Firebase identity token |
| 4 | FastAPI → Firebase push → Android app | Firebase server library for Python | Alert or refresh, with a senior id | Service credentials |
| 5 | FastAPI → Twilio | Twilio Voice and Messaging APIs | "Call this number", the caregiver notice SMS | Twilio account credentials |
| 6 | Twilio → FastAPI | Web callbacks | Call answered, call status, voicemail detection, welcome-call answers, hand-over, hand-over result | Twilio request signature |
| 7 | Twilio ↔ FastAPI | WebSocket (ConversationRelay) | Senior's words as text in; agent's words as text out | Twilio request signature on connect, plus a one-time call id in the address |
| 8 | FastAPI → model provider | Streaming API with tool calls | Conversation turns and tool results | Provider API key |
| 9 | FastAPI ↔ PostgreSQL | Private network | Everything | Database credentials |
| 10 | Twilio ↔ phones | Ordinary phone network | Voice | n/a |
| 11 | FastAPI → Firebase sign-in | Firebase server library for Python | Checking identity tokens | Service credentials |
| 12 | Home node ↔ senior's phone app **(P20, proposed)** | Bluetooth Low Energy, the node as a GATT server and the phone app as the client | Room readings, motion, the SOS button; the status light and the buzzer back to the node | Bonded once from the phone app; the phone accepts only its bonded node |

## 5. One door (G2)

> **Every read and every write goes through FastAPI. Firebase never holds application data.**

There is no second path to the database, so there is one place that checks permissions, one schema and one writer. A change of code, a new call or a new grant is written by FastAPI, which therefore knows the moment to send a refresh (section 7).

## 6. Identity and permissions

**People** sign in with their phone number and an SMS code (G6), in the Android app or the dashboard. The Firebase library on Android reads the code automatically when it can. The client then sends its Firebase identity token with every request to FastAPI. FastAPI verifies the token, reads the phone number from it, and looks it up.

Nobody chooses a role. A role is a **grant** made by someone allowed to make it, by entering the person's phone number:

| Who grants | Grants | How |
|---|---|---|
| The setup script, run by the team | DAS employees | Name and phone number |
| A DAS employee | Medics, and other DAS employees | Name, phone number, practice (for a medic) |
| A medic | A senior, and the senior's caregivers | The registration form: the senior's own number, and each caregiver's name, relation and number |
| A DAS employee | Caregivers of a senior that is submitted or further along, and that senior's own grant when it changes the senior's number | The caregiver's name, relation and number, or the senior's new number ([seniors-and-enrollment.md](../seniors-and-enrollment.md) SE9, SE11) |

A grant creates the person's user row immediately, before they ever sign in. At first sign-in FastAPI attaches the Firebase account to that row. The phone number stays the key on every request: if a different Firebase account signs in with the number, FastAPI replaces the stored one and logs a warning ([auth-layer.md](../auth-layer.md) AL4).

| When a number signs in | Result |
|---|---|
| Its grants are all one role | The app opens the screens for that role. The dashboard accepts DAS grants only |
| Its grants span several roles (for example a caregiver who is also a medic, or a senior who uses a relative's phone) | The app asks which role to use, listing only the granted roles. Several grants of one role, such as a caregiver of both parents, are one role: its screens list every senior it covers |
| It has none | „Numărul nu este înregistrat. Contactați medicul de familie." Nothing is stored |

Phone numbers are normalized to the international format (+40…) on every write and every lookup, so "0722 123 456" typed by a medic matches the number Firebase reports.

**The watch** has no identity of its own. Its messages reach FastAPI only through the senior's phone app, which is signed in as that senior (G5).

**The home node** has no identity of its own either (P20). It is bonded once to the senior's phone over Bluetooth, and its readings reach FastAPI only through that phone's app. It holds no Wi-Fi password, no address of the API and no key, so a lost or opened box gives nothing away.

**Twilio** signs every callback; FastAPI rejects unsigned or wrongly signed requests.

**One place enforces permissions: FastAPI.** Every endpoint checks the caller's grants and, where a senior is involved, that the grant covers that senior. The app's role screens are a convenience, not a protection. A caller may do what any of their grants allows; the role chosen in the app only picks screens. For one senior, the caller sees what the grants covering that senior allow in the table below. A medic covers a senior when they hold a medic grant and registered that senior. A senior outside the caller's reach answers "not found", as an id that does not exist does. A user holds at most one senior grant, so one mobile number signs in as one senior: registering a second senior with that mobile is refused, while a landline, which signs nobody in, can be shared ([auth-layer.md](../auth-layer.md) AL2, AL7, AL8; [seniors-and-enrollment.md](../seniors-and-enrollment.md) SE10). The medic who registered a senior, and DAS for a senior it reaches, may edit the registration and its caregivers (SE9).

**Who sees which seniors**

| Role | Sees |
|---|---|
| Medic | Seniors they registered |
| Caregiver | Seniors whose registration lists their number |
| Senior | Themselves |
| DAS | All seniors that are submitted or further along |

**Who sees how much** (kept from v3 §11.4, extended)

| Information | Caregiver | Medic | DAS |
|---|---|---|---|
| Code and reason | Yes | Yes | Yes |
| Call history, short form | Yes | Yes | Yes |
| Full transcript | No | Yes | Yes |
| Address and access details | Yes | Yes | Yes |
| Location attached to an event **(proposed)** | Yes | No | Yes |
| Watch state (worn, battery, last check-in) | Yes | Yes | No |
| Home node state and latest room reading (temperature, humidity, last motion) **(proposed)** | Yes | Yes | Yes |
| Consent record | No | Yes | Yes |

## 7. Live updates and push (G4)

One mechanism serves open and closed Android apps. When FastAPI writes something a person can see in the app, it sends a Firebase push to every device of every account that can see it.

The web dashboard receives no pushes. A dispatcher's dashboard is always open, so it re-reads every few seconds (interval in [06-operations.md](06-operations.md) section 3). A new red plays an audible cue; browsers allow sound only after a click on the page, so the dashboard asks for one click after sign-in („Pornește alertele sonore”).

| Kind | Sent when | What the app does |
|---|---|---|
| Alert | A code changes into yellow or red (recipients in [03-status-model.md](03-status-model.md) section 7) | Shows a system notification with generic text; tapping it opens the senior's page. If the app is open, it also re-reads |
| Refresh | Any other visible change: a code into green, a call starting or ending, an enrollment state, a watch or home node state, a new grant | Silent. If the app is open, it re-reads the screen; if closed, nothing |

A slow timed re-read while a screen is open is the backstop for a lost push. Its interval is in [06-operations.md](06-operations.md) section 3.

```mermaid
sequenceDiagram
    participant F as FastAPI
    participant DB as PostgreSQL
    participant P as Firebase push
    participant O as Open app
    participant C as Closed app

    F->>DB: write the new code
    F->>P: alert or refresh, with the senior id, to every device that can see it
    P-->>O: message arrives
    O->>F: re-read the open screen
    P-->>C: alert shown as a system notification
    C->>F: when opened, read the senior's page
    loop every backstop interval while a screen is open
        O->>F: re-read
    end
```

## 8. Inside the FastAPI service

One process, several modules with narrow jobs. They are separate so that the dialer, the notifier and the call sessions can later become separate workers without a rewrite.

```mermaid
flowchart LR
    subgraph INB["Inbound"]
        AUTHM["Identity<br/>verify token, resolve grants"]
        API["Reads, data entry, commands"]
        INT["Senior event intake<br/>from the phone app"]
        HOOK["Twilio callbacks<br/>signed"]
        WS["Relay WebSocket"]
    end

    subgraph LOGIC["Logic"]
        SCHED["Scheduler<br/>due calls, redials, silent devices,<br/>no motion at home"]
        DIAL["Dialer"]
        WEL["Welcome call<br/>fixed script"]
        SESS["Call session<br/>agent loop, alarm phrases"]
        ENG["Rules and status engine<br/>answers, matrix"]
    end

    subgraph OUTB["Outbound"]
        NOTIF["Notifier"]
        STORE["Store"]
    end

    TWILIO["Twilio"]
    MODEL["Model provider"]
    PUSH["Firebase push"]

    AUTHM --> API
    AUTHM --> INT
    API --> SCHED
    INT --> SCHED
    SCHED --> DIAL
    DIAL -->|"Voice API"| TWILIO
    HOOK --> DIAL
    HOOK --> WEL
    HOOK --> SESS
    WS <--> SESS
    SESS -->|"streaming, tool calls"| MODEL
    SESS -->|"answers, alarm matches"| ENG
    WEL -->|"identity, consent"| STORE
    DIAL -->|"unanswered"| ENG
    ENG --> STORE
    ENG --> NOTIF
    NOTIF --> PUSH
    ENG -->|"red: hand over"| SESS
    ENG -->|"redial"| SCHED
```

| Module | Job | Depends on |
|---|---|---|
| Identity | Verifies the Firebase identity token, normalizes the phone number, loads the caller's grants, attaches the Firebase account at first sign-in | Firebase sign-in, Store |
| Reads, data entry, commands | The endpoints in [04-interfaces.md](04-interfaces.md) sections 1 and 2; checks grants on each | Store |
| Senior event intake | Receives events, check-ins and room readings forwarded by the senior's phone app; drops duplicates; applies the cooldown and the active-warning rule; turns a room reading that stays out of range into an event (P21) | Store |
| Scheduler | On a short tick: finds calls that are due, marks silent watches and home nodes, and records an inactivity event for a home node with no motion past the limit during a warning. All timers are rows with a due time, so a restart loses nothing. Each tick first takes a database lock, so a second running copy of the service skips the tick | Store |
| Dialer | Places a call through Twilio and tracks its lifecycle from the status callbacks | Twilio, Store |
| Welcome call | Answers the welcome call's callbacks with fixed questions and records identity and consent | Store |
| Call session | One per live wellbeing call. Holds the WebSocket, matches alarm phrases, asks the confirmation question, runs the conversation with the model, executes hand-over | Twilio, model provider |
| Rules and status engine | Turns answers into severity and certainty, checks the shelter answer against the latest room reading (P22), applies the matrix, decides the code and the actions. Pure logic with no outside calls | Nothing |
| Notifier | Sends alerts and refreshes through Firebase push; the caregiver notice SMS through Twilio | Firebase push, Twilio |
| Store | All reads and writes to PostgreSQL, asynchronous | PostgreSQL |

The rules and status engine has no dependencies on purpose: every rule and every cell of the matrix can be tested without a phone, a model or a database.

**The agent loop is written directly against the model provider's library (proposed)**, not inside an agent framework. The server refuses tool calls, matches alarm phrases before the model sees a sentence, and cuts the model's reply short on an interruption; a framework's own loop would be in the way.

**Everything in the request path is asynchronous.** One blocking database call or web request in this process would pause every live conversation.

## 9. Hosting (G9)

| Part | Where | Requirement |
|---|---|---|
| FastAPI service | Railway, EU West, built from a Dockerfile | Exactly one replica; sleeping when idle turned off; a health check at `/api/health`. Railway's public HTTPS address also serves the secure WebSocket Twilio needs |
| PostgreSQL | Railway, same project and region | Reached over the private network |
| Web dashboard | Railway, a separate static-site service in the same project | Its own service, so that changing the dashboard never redeploys FastAPI and drops live calls. The API allows browser requests from this address only |
| Android and Wear OS apps | Installed directly on the demo devices | n/a |

A new deploy starts before the old one stops, so for a few seconds two copies run. The scheduler's database lock keeps one of them idle. Calls live on the old copy drop, so nothing is deployed after the Sunday-morning freeze.

During development Twilio must still reach channels 6 and 7: a tunnel to a laptop, or a Railway environment per branch.

## 10. Deliberately absent

- **No message broker or worker pool.** Nothing in the MVP needs one. The module boundaries in section 8 keep that door open.
- **One web client only**, for DAS at the desk. Seniors, caregivers and medics use the Android app.
- **No second path to the database.** No SQL Connect, no Firestore, no live queries.
- **No file storage.** The only image-like item, the optional signature, is stored as strokes on a consent record.
- **No app-to-app channel** between people's devices. The watch and the home node talk to the senior's phone, which are one person's devices.
- **No device on the internet except phones.** The home node has no Wi-Fi connection and never reaches FastAPI on its own.
- **No audio anywhere in our systems.** Twilio handles speech in both directions; FastAPI sees and stores text only.

## 11. Home node hardware (P20, proposed)

One box per senior, on a shelf in the room where they spend the day, within about ten metres of the phone. It is plugged in, so it has no battery to charge and no deep sleep.

| Part | Job | Approximate cost |
|---|---|---|
| ESP32 DevKit (WROOM-32 or S3) | The controller; Bluetooth Low Energy built in | 30–45 lei |
| SHT31 module, I2C | Room temperature and humidity. Chosen over the DHT22 for accuracy, since the readings decide a code | 20–40 lei |
| HC-SR501 PIR | Motion in the room | 8–15 lei |
| Large push button | SOS, on a long press | 5–10 lei |
| Active buzzer module | Confirms a press, and the phone's acknowledgement | 3–5 lei |
| RGB LED and three 220 Ω resistors, or one WS2812 | Shows the senior's code | 2–5 lei |
| 5 V USB phone charger and cable | Power | n/a |
| **Total** | Plus a spare ESP32 and a spare SHT31 for the demo | **about 90–140 lei** |

**Wiring**

| Part | Pin | ESP32 |
|---|---|---|
| SHT31 | VCC, GND | 3V3, GND |
| | SDA, SCL | GPIO21, GPIO22 (I2C address `0x44`) |
| PIR | VCC, GND | VIN (5 V), GND |
| | OUT | GPIO27 (the output is 3.3 V, safe to connect directly) |
| SOS button | one leg, the other | GPIO32 with the internal pull-up, GND |
| Buzzer module | signal, VCC, GND | GPIO25, 3V3, GND |
| RGB LED | R, G, B | GPIO16, GPIO17, GPIO18, each through 220 Ω |

The PIR needs 30 to 60 seconds to settle after power-on; its jumper is set to repeat trigger.

**What the node does**

- Advertises one EchoCare GATT service and accepts a connection only from its bonded phone. The characteristics are in [04-interfaces.md](04-interfaces.md) section 3.
- Reads the SHT31 every reading interval, smooths it with a short moving average, and notifies the phone. A value outside a plausible range (−10 to 50°C) is not sent.
- Notifies motion when it starts, and keeps the time of the last motion for the next reading.
- On a long press of the button (two seconds), beeps once and notifies the phone with an id it generates; beeps twice when the phone says FastAPI recorded it. Until then it keeps the press and sends it again after a reconnection.
- Lights the LED in the colour the phone writes: the senior's code, blue while a call is in progress. A slow white blink means "not connected to the phone".

The node decides nothing. The thresholds, the hold time and the inactivity limit live in FastAPI (P21), so changing them needs no firmware update.
