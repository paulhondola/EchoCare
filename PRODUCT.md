# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

Design work targets the DAS web dashboard (`dashboard/`). The Android phone and tablet app (senior, caregiver, medic and DAS roles) and the Wear OS app are context only; they get their own product record if design work moves there.

## Users

DAS dispatchers (Direcția de Asistență Socială) at a desk, through shifts that can run 8 to 12 hours. Their jobs on the dashboard: notice a red incident the moment it opens, take it, reach the senior, caregiver or 112, and resolve it with an outcome and a note; watch every enrolled senior's code; accept enrollment requests, which starts the welcome call; start and end heat or cold weather campaigns; grant medic and DAS staff and set who is on duty.

The on-duty dispatcher also carries the DAS phone, which receives the live hand-over call and shows red incidents in the Android app. The dashboard is the desk surface; the phone is the away-from-desk one (G15).

## Product Purpose

EchoCare is an early-warning system for heat and cold illness in seniors who live alone. During a weather warning it phones each enrolled senior, an AI agent talks with them in Romanian, and the server turns the answers into one code, green, yellow or red, that the caregiver, the medic and DAS all see. A red opens an incident and hands the live call to the on-duty DAS phone. A Wear OS watch, the optional home node and the senior's own "Sunați-mă" button can start the same call.

Success right now is the live demo at UniHack 8 (Timișoara, 13–15 November 2026), Medical Renaissance track, in front of the judges. Reuse in two university courses comes second. A real pilot is later and may be a rewrite (G1). The demo leads with cold (G14).

## Positioning

The current system is reactive: a senior has to call DAS to get help, and the most exposed seniors are the ones who don't, because heat stroke brings confusion. EchoCare calls them, on any phone, landlines included, and needs nothing else from the senior. The model only extracts answers; fixed server rules decide the code, and the model may raise a level but never lower it (G10). Alarm phrases force red without waiting for the model (G11, G12). It is framed as prevention of a medical emergency (heat stroke, hypothermia), not as a social service.

## Operating Context

- Dispatchers sign in with a phone number and an SMS code (G6). Roles come from grants, never self-chosen.
- The dashboard re-reads the API every few seconds (04 §6). A new open red shows a banner over every page and plays a siren once the dispatcher has switched sound alerts on in the browser (UC-11).
- Incident lifecycle: `open` → `in_progress` when someone takes it (answering the hand-over takes it) → `resolved` with an outcome (`senior_ok`, `team_sent`, `called_112`, `not_reached`, `false_alarm`) and a note (G16). Resolving does not change the senior's code.
- A dispatcher acts on what the dashboard shows: the senior's address with access details (staircase, flat, intercom), a landline badge, the last known phone location, caregivers and family doctor to call, and call transcripts (G13).
- If nobody is on duty, red hand-overs cannot be transferred; the dashboard has to make that state impossible to miss.

## Capabilities and Constraints

- Screens: incidents (board and table), seniors (with CSV export), enrollments, staff and on duty, weather campaigns, system health.
- All data comes from the FastAPI JSON API. The dashboard holds no business rules: codes, permissions and incident transitions are decided by the server; the dashboard only shows and requests them.
- User-facing text is Romanian. Code, comments and docs are English.
- Terminology to keep: Cod Roșu, Cod Galben, Cod Verde; incident, preiau, rezolvă; campanie caniculă, campanie ger; înrolare; de serviciu.
- The API only grows: new fields are optional, nothing is renamed or dropped in one change (ADR-001 §2.3). Contract changes move together with `04-interfaces.md`.
- The data is health data about real people in a pilot: addresses, intercom codes, transcripts. The demo uses fictitious data only (06 §security).
- CI fails on Svelte accessibility warnings (`svelte-check --fail-on-warnings`).
- Undecided: risk factors and a risk score (open question 5); shelters and a map are out of scope for the MVP.

## Brand Commitments

- Name: EchoCare. The earlier working name "Ești bine?" appears in the v3 spec and hackathon brief and is history.
- The three codes are product vocabulary shared by every role and surface. Each code means the same thing everywhere.

## Evidence on Hand

- Mock data only: fictitious seniors and incidents from `backend/scripts/seed.py`.
- No DAS partner, endorsement, pilot, testimonial or usage figure exists. Do not invent any.
- The public statistics cited in `docs/specs/unihack.md` were not approved for design work; do not put them on a surface without asking.

## Product Principles

1. **A red is never missed.** The open-red state outranks everything else on every page until someone takes it.
2. **The server decides, the screen shows.** No surface computes, softens or overrides a code.
3. **Act from one place.** Everything a dispatcher needs to reach the senior (address, access details, numbers, last words on the call) is where the incident is, without leaving the board.
4. **Built for the whole shift.** Calm when nothing is happening, so that what is happening stands out.
5. **Show only what is true.** Demo data stays fictitious; no claims, partners or numbers the project does not have.

## Accessibility & Inclusion

- Dispatchers work long shifts; screens must stay readable and low-strain over hours.
- Code state must not depend on colour alone: each code carries its name (Cod Roșu, Cod Galben, Cod Verde) wherever it appears.
- The siren needs an explicit opt-in, and every audio alert has a visible counterpart.
