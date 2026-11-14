# Apple Watch UI for seniors

**Date:** 2026-11-14 · **Scope:** `ios/EchoCareWatch` only · **Size:** small change

## Why

For the UniHack judging on 2026-11-15. The judges should believe a real senior, with poor sight and little experience with technology, could use the watch easily. Today the watch home is a list of same-looking gray buttons. „Oprește monitorizarea” sits directly above „Nu mă simt bine”, and nothing tells the senior that help is on the way.

## Goals

- At a glance the senior can tell they are being looked after, and the help button is the most obvious thing on screen.
- „Sunteți bine?” can be answered in a panic: two big targets, the time left shown without numbers.
- After „Nu”, silence or the help button, the watch says help is coming, and only once the team really has the alert.
- The team can still pause monitoring and trigger anomalies during the demo.

## Non-goals and anti-goals

- **Not on Wear OS.** This is a deliberate exception to the `ios/AGENTS.md` rule that each Swift screen ports its Kotlin file. `android/`, `backend/` and the API contract stay as they are.
- No complications, widgets or new targets. No change to the detectors, the timings, the event queue or the phone app.
- **Anti-goal:** a ✓ that appears when the alert has not reached the team. Telling a senior help is coming when it isn't is worse than saying nothing.

## Approaches considered (for the confirmation)

| | How ✓ is decided | Trade-off |
|---|---|---|
| **Real confirmation (picked by Paul)** | The phone's `received` ack, which it sends only after `POST /me/events` succeeds (`Relay.handle`, 04 §3) | Honest. On bad Wi-Fi it stays on „Anunțăm echipa…”, softened to „Încercăm din nou…” after 20 s |
| Timer | ✓ 2 s after sending, whatever happens | Always looks good on stage, but it lies when the phone or the network is down |
| Phone got it | ✓ when WatchConnectivity delivers | Says nothing about the team. Dropped |

## The design

Mockups were reviewed in the brainstorm companion (home B, prompt A).

**Home (`HomeView`)**, top to bottom:
- A small gray pause/play button in the top-left corner, about 24 pt (the team's toggle). It calls `monitor.stop()` / `monitor.start()`.
- A big heart: green while monitoring runs, gray when it doesn't.
- A large two-line status: „Totul e în regulă” while running, „Monitorizare oprită” when not.
- „Puls 72”, a plain number with no „bpm”, while running. „Puls: se măsoară…” until the first reading.
- „Nu mă simt bine” as a full-width red button at the bottom, the only red thing on screen. It works whether monitoring runs or not, as `callMe()` does today.
- The permission line and its button stay as today when `startFailed`.
- The Debug buttons (`#if DEBUG`) sit below the fold.

**Prompt (`AreYouOkView`):**
- „Sunteți bine?” as a heavy title.
- A full-width green „✓ Da, sunt bine” above a full-width red „✕ Nu, ajutor!”. Together they fill the screen with no scrolling on 41 mm.
- An amber ring around the screen edge drains from full to empty between the moment the prompt opened and `deadlineMs`. It replaces the „12 s” text.
- „Da” also answers to the system double tap (`.handGestureShortcut(.primaryAction)`). On watches without double tap it does nothing.
- **Spoken prompt:** the watch says „Sunteți bine?” once when the prompt opens, only if `AVSpeechSynthesisVoice(language: "ro-RO")` exists, and stays silent otherwise. It must not disturb the workout session or the haptics. If that proves fiddly, drop it rather than delay the rest.

**Confirmation (new `HelpComingView`)**, shown after `callMe()`, „Nu” or a timeout:
1. A spinner, „Anunțăm echipa…”, and „Țineți telefonul aproape”.
   - After 20 s without an ack, the line changes to „Încercăm din nou…”. The queue keeps resending as today.
2. On the ack for that event id: a green ✓, „Echipa a fost anunțată”, „Vă sunăm imediat. Răspundeți la telefon.”, and a `.success` haptic.
   - It goes back to home after 60 s, or on tap.

**Screen priority in `RootView`:** prompt, then confirmation, then home. A new prompt replaces a confirmation.

**State:**
- `Monitor` gains an observable `alert` (the event id, when it was sent, and whether it was received). `resolve(send: true)` and `callMe()` set it.
- `PhoneLink.acked(_:)` already runs when the phone answers. It gains a callback so `Monitor` hears the id.
- Only the current alert's id marks it received. An ack for an older resent event is ignored.

**Copy:** the Romanian strings above, added to `EchoCareWatch/Localizable.xcstrings` under new keys.

**Contrast:** white text on the buttons uses dark enough red and green (about `#C62A2F` and `#187A42`) to read clearly at 17 pt.

## Left to the builder

- Exact SwiftUI sizes, so prompt A fits 41 mm and 45 mm without scrolling at the default text size and still works, with scrolling, at large text sizes.
- How the ring is drawn (a trimmed rounded-rectangle stroke inside the existing `TimelineView`).
- Key names for the new strings, and how the callback is wired from `PhoneLink` to `Monitor` (`PhoneSending` or `WatchDelegate`).
- Tests in `EchoCareWatchTests/MonitorTests.swift`:
  - `callMe()`, „Nu” and a timeout each set `alert`; „Da” does not.
  - The matching ack marks it received; an unrelated id does not.
- Check on Alex's watch: the simulator can't show WatchConnectivity or double tap. Confirm the ro-RO voice exists before the demo.
