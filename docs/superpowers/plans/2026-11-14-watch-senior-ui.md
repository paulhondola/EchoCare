# Apple Watch UI for Seniors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the senior's Apple Watch obviously easy to use for the 2026-11-15 judging: a calm home with one big help button, a panic-proof „Sunteți bine?”, and an honest "help is coming" confirmation driven by the phone's ack.

**Architecture:** `Monitor` gains an observable `alert` (the last event sent, and whether the phone acked it). `PhoneLink` forwards each ack id to `Monitor`. `RootView` shows prompt › confirmation › home. The three screens are plain SwiftUI. Timing for "retrying" and auto-dismiss lives in the views (`TimelineView`, `.task`), because `Monitor.tick` stops when monitoring is paused.

**Tech Stack:** Swift 6 (strict concurrency), SwiftUI for watchOS 26, Swift Testing, AVFAudio (`AVSpeechSynthesizer`).

**Spec:** `docs/superpowers/specs/2026-11-14-watch-senior-ui-design.md`

## Global Constraints

- Touch only `ios/EchoCareWatch/` and `ios/EchoCareWatchTests/`. No change to `android/`, `backend/`, the phone app, `Shared/`, or the API.
- Romanian user-facing text lives in `ios/EchoCareWatch/Localizable.xcstrings` (source language `ro`). Add entries in the same shape as the existing ones: `"extractionState": "manual"` and a `ro` `stringUnit` with `"state": "translated"`. Code and comments are in English.
- Format arguments are Apple's (`%1$lld`). Pass `Int64`, never `Int`: Swift's `Int` is 32 bits on arm64_32 watches.
- Button colors, so white text reads at 17 pt: help/„Nu” red `#C62A2F`, „Da” green `#187A42`. The status heart is green `#3DD68C`, gray when paused. The countdown ring is amber `#F5A524`.
- Detector logic, `Timings` values, the event queue and resend behaviour don't change.
- After Swift edits, run the formatter and lint (the pre-commit hook runs them too):
  - `swift format format --in-place --parallel --recursive --configuration ios/.swift-format ios/EchoCareWatch ios/EchoCareWatchTests`
  - `swift format lint --strict --parallel --recursive --configuration ios/.swift-format ios/EchoCareWatch ios/EchoCareWatchTests`
- Run the watch tests from the repo root. The suite is enabled only with demo timings (Debug):
  - `xcodebuild test -project ios/EchoCare.xcodeproj -scheme EchoCareWatch -destination 'platform=watchOS Simulator,name=Apple Watch Series 12 (42mm)' -quiet`
  - If the name matches more than one simulator, use `id=7B9B0341-BE8F-4776-B784-CB77B02E4FE8`.

## Review Focus

1. **An ack for an older, resent event arrives while a newer confirmation shows.** It must not turn the newer one to ✓. Pinned by `anAckForAnotherEventIsIgnored` (Task 1).
2. **The same ack arrives twice** (the phone answers a resend). The ✓ and the success buzz happen once. Pinned by `aRepeatedAckBuzzesOnce` (Task 1).
3. **The senior presses help while monitoring is paused.** The event is still sent and the confirmation still shows. Pinned by `callMeWhilePausedStillAlerts` (Task 1).
4. **A new anomaly fires while the confirmation shows.** The prompt takes over, and „Da” on it doesn't bring back a stale confirmation. Pinned by `aNewPromptClearsTheConfirmation` (Task 1).
5. **The largest text size on a 42 mm watch.** The prompt's buttons must stay reachable (scroll), not clip off-screen. Checked by hand in Task 3, step 6.

---

### Task 1: Alert state in `Monitor`, fed by the phone's ack

**Files:**
- Modify: `ios/EchoCareWatch/Monitoring/Monitor.swift`
  - Add `Timings` constants.
  - Add `Alert` and `HelpPhase` next to `Prompt`, plus `Prompt.remainingFraction`.
  - Add `alert` and the two methods to `Monitor`.
  - Edit `callMe()`, `resolve(send:)` and `raiseAnomaly`.
- Modify: `ios/EchoCareWatch/Monitoring/PhoneLink.swift`: an `onAcked` callback, called from `acked(_:)`.
- Modify: `ios/EchoCareWatch/EchoCareWatchApp.swift`: in `WatchDelegate.init`, wire `link.onAcked` to `monitor.eventReceived(id:)`.
- Test: `ios/EchoCareWatchTests/MonitorTests.swift` (new tests in the existing suite).
- Test: create `ios/EchoCareWatchTests/AlertTests.swift` for the pure functions, with no demo gate.

**Interfaces:**
- Produces, in `Monitor.swift`:
  ```swift
  extension Timings {
      static let helpRetryingMs: Int64 = 20_000   // „Încercăm din nou…” after this long without an ack
      static let helpShownMs: Int64 = 60_000      // the ✓ screen goes home after this long
  }
  enum HelpPhase: Equatable { case sending, retrying, received }
  struct Alert: Equatable {
      var id: String          // the event id sent to the phone
      var sentAtMs: Int64
      var receivedAtMs: Int64?
      func phase(nowMs: Int64) -> HelpPhase
  }
  extension Prompt {
      /// 1 when the prompt opens, 0 at the deadline, clamped to 0...1. Total is Timings.promptTimeoutMs.
      func remainingFraction(nowMs: Int64) -> Double
  }
  // on Monitor
  private(set) var alert: Alert?
  func eventReceived(id: String)
  func dismissAlert(id: String)
  ```
- Produces, in `PhoneLink.swift`: `var onAcked: (@MainActor (String) -> Void)?`

- [ ] **Step 1: Write the failing pure-function tests in `AlertTests.swift`**

```swift
@Test func phaseIsSendingBeforeTheRetryLimit() {
    #expect(Alert(id: "e", sentAtMs: 0).phase(nowMs: 19_999) == .sending)
}
@Test func phaseIsRetryingFromTheRetryLimit() {
    #expect(Alert(id: "e", sentAtMs: 0).phase(nowMs: 20_000) == .retrying)
}
@Test func phaseIsReceivedOnceAcked() {
    #expect(Alert(id: "e", sentAtMs: 0, receivedAtMs: 25_000).phase(nowMs: 25_000) == .received)
}
@Test func remainingFractionRunsFromOneToZero() {
    let p = Prompt(id: "p", type: "fall", measuredAt: "", snapshot: .empty,
                   deadlineMs: 1_000 + Timings.promptTimeoutMs)
    #expect(p.remainingFraction(nowMs: 1_000) == 1)
    #expect(p.remainingFraction(nowMs: 1_000 + Timings.promptTimeoutMs / 2) == 0.5)
    #expect(p.remainingFraction(nowMs: p.deadlineMs + 5_000) == 0)
    #expect(p.remainingFraction(nowMs: 0) == 1)   // clock before the prompt opened
}
```

Give `Alert.receivedAtMs` a default of `nil` so the two-argument init compiles.

- [ ] **Step 2: Write the failing `Monitor` tests in `MonitorTests.swift`**

Use the suite's existing helpers (`raiseHighPulse`, `tick(at:)`, `clock`, `haptics.played`, `link.events`). Assertions:

```swift
@Test func callMeSetsAnAlertForItsEvent()        // alert?.id == link.events.last?.id, receivedAtMs == nil
@Test func answeringNoSetsAnAlertForThePrompt()  // after answer(ok: false): alert?.id == the prompt's id
@Test func aTimeoutSetsAnAlert()                 // tick past deadlineMs → alert?.id == the prompt's id
@Test func answeringYesSetsNoAlert()             // answer(ok: true) → alert == nil
@Test func theMatchingAckMarksItReceived()       // eventReceived(id: alert.id) → receivedAtMs == clock.now, haptics.played.last?.type == .success
@Test func anAckForAnotherEventIsIgnored()       // eventReceived(id: "other") → receivedAtMs == nil, no .success played
@Test func aRepeatedAckBuzzesOnce()              // eventReceived twice → exactly one .success in haptics.played, receivedAtMs unchanged by the second
@Test func callMeWhilePausedStillAlerts()        // monitor.stop(); callMe() → link.events.count == 1, alert != nil
@Test func aNewPromptClearsTheConfirmation()     // callMe(); raise a prompt → alert == nil; answer(ok: true) → alert == nil
@Test func dismissAlertClearsOnlyTheSameId()     // dismissAlert(id: "other") keeps it; dismissAlert(id: alert.id) → nil
```

- [ ] **Step 3: Run the tests to verify they fail**

Run the watch test command from Global Constraints.
Expected: build fails (`Alert`, `eventReceived`, `remainingFraction` not defined).

- [ ] **Step 4: Implement in `Monitor.swift`**

- `callMe()` builds the `EventMessage`, sends it through `enqueueAndSend`, then sets `alert = Alert(id: msg.id, sentAtMs: clock())`.
- `resolve(send: true)` sets `alert` the same way with `prompt.id`.
- `raiseAnomaly`, where it sets `prompt`, also sets `alert = nil`.
- `eventReceived(id:)` returns unless `alert?.id == id && alert?.receivedAtMs == nil`. Then it sets `receivedAtMs = clock()` and calls `haptics(.success)`.
- `dismissAlert(id:)` sets `alert = nil` only when the id matches.

- [ ] **Step 5: Wire the ack**

- `PhoneLink.acked(_:)`: keep `queue.ack` and the log, then call `onAcked?(id)`.
- `WatchDelegate.init`, after `monitor` exists: `link.onAcked = { [monitor] id in monitor.eventReceived(id: id) }`.
- The event queue still acks every id. Only `Monitor` filters by the current alert.

- [ ] **Step 6: Run the tests to verify they pass**

Run the watch test command.
Expected: all tests pass. The existing `callMeSendsAManualRequest`, `answerNoSendsEventOnce` and `timeoutSendsEvent` stay green.

- [ ] **Step 7: Format, lint, commit**

```bash
git add ios/EchoCareWatch/Monitoring ios/EchoCareWatch/EchoCareWatchApp.swift ios/EchoCareWatchTests
git commit -m "Watch: track the last alert and the phone's ack for it"
```

---

### Task 2: Home screen B with the pause button

**Files:**
- Create: `ios/EchoCareWatch/Screens/Palette.swift`
- Modify: `ios/EchoCareWatch/Screens/HomeView.swift`
- Modify: `ios/EchoCareWatch/Localizable.xcstrings`

**Interfaces:**
- Consumes: `Monitor.running`, `.starting`, `.startFailed`, `.lastHeartRate`, `start()`, `stop()`, `callMe()` (unchanged).
- Produces: `enum Palette { static let help, yes, calm, ring: Color }`, using the hex values in Global Constraints. Tasks 3 and 4 use it.

- [ ] **Step 1: Add strings**

| Key | Value |
|---|---|
| `all_good` | `Totul e în regulă` |
| `heart_rate_plain` | `Puls %1$lld` |

- Reuse `monitor_off`, `heart_rate_waiting`, `call_me`, `start_monitoring`, `stop_monitoring`, `permission_needed` and `grant_permission`.
- Delete `monitor_active`, `heart_rate` and `call_me_sending`, which this change leaves unused.

- [ ] **Step 2: Rewrite `HomeView`'s body**

1. Wrap the screen in a `NavigationStack` with a `.toolbar` `ToolbarItem(placement: .topBarLeading)`. It holds a small button (SF Symbols `pause.fill` / `play.fill`) that calls `stop()` / `start()`.
   - Its accessibility label is `stop_monitoring` / `start_monitoring`.
   - It's disabled while `starting`.
   - This is the team's toggle: leave it small and gray, not prominent.
2. Inside a `ScrollView` / `VStack`:
   - The permission line and button as today, when `startFailed`.
   - `heart.fill` at about 44 pt, in `Palette.calm` while running, `.gray` when not.
   - `all_good` / `monitor_off` as `.title3.bold()`, centered, allowed to wrap to two lines.
   - While running, the pulse line (`heart_rate_plain` / `heart_rate_waiting`) as `.body`, `.secondary`.
   - `call_me` as a full-width `.borderedProminent` button tinted `Palette.help`, `.headline` text.
   - The `#if DEBUG` buttons last, so they sit below the fold.
3. Delete `sending` and the 2-second debounce: after `callMe()`, `RootView` switches to the confirmation at once (Task 4), so there is no second tap to block.
4. Keep the Int64 cast for the pulse format.

- [ ] **Step 3: Build**

Run: `xcodebuild build -project ios/EchoCare.xcodeproj -scheme EchoCareWatch -destination 'generic/platform=watchOS Simulator' -quiet`
Expected: `** BUILD SUCCEEDED **` (or no output with `-quiet`, exit 0).

- [ ] **Step 4: Look at it on the 42 mm simulator**

Check the screen with no scrolling:
- The heart, the status text and the help button are all visible.
- The pause button sits in the top-left corner.
- With monitoring stopped, the heart is gray and the text reads „Monitorizare oprită”.

- [ ] **Step 5: Format, lint, run the watch tests, commit**

```bash
git add ios/EchoCareWatch/Screens ios/EchoCareWatch/Localizable.xcstrings
git commit -m "Watch: calm home with one big help button and a small pause toggle"
```

---

### Task 3: Prompt A, with the draining ring, double tap and spoken question

**Files:**
- Modify: `ios/EchoCareWatch/Screens/AreYouOkView.swift`
- Modify: `ios/EchoCareWatch/Localizable.xcstrings`

**Interfaces:**
- Consumes: `Prompt.remainingFraction(nowMs:)` (Task 1), `Palette` (Task 2), `answer: (Bool) -> Void` (unchanged).

- [ ] **Step 1: Strings**

- Reuse `are_you_ok_title`, `are_you_ok_yes` („Da, sunt bine”) and `are_you_ok_no` („Nu, ajutor!”).
- Delete `are_you_ok_countdown`, which becomes unused.

- [ ] **Step 2: Rewrite the body**

1. **Ring.** A `TimelineView(.periodic(from: .now, by: 0.5))` draws a `RoundedRectangle` stroke in `Palette.ring`, about 6 pt wide.
   - It uses `.trim(from: 0, to: prompt.remainingFraction(nowMs:))` and `.ignoresSafeArea()`, behind the content.
   - The corner radius should roughly follow the screen corners; exact match not required.
2. **Content.**
   - The title in `.title3.weight(.heavy)`.
   - „✓ Da, sunt bine”, a full-width button filled `Palette.yes`.
   - „✕ Nu, ajutor!”, a full-width button filled `Palette.help`.
   - The two buttons share the remaining height equally, with `.headline` text.
   - Use `Label` with `checkmark` / `xmark` symbols, or the text alone. Keep the text first for VoiceOver.
3. **Fit.** Use `ViewThatFits(in: .vertical)`: the stretched layout first, then the same content in a `ScrollView` with natural button heights, so large text sizes scroll instead of clipping.
4. **Double tap.** Add `.handGestureShortcut(.primaryAction)` on the „Da” button.

- [ ] **Step 3: Spoken prompt**

Add a private `@MainActor enum PromptVoice` in the same file, with a static `AVSpeechSynthesizer` kept alive.
- `speak()` returns unless `AVSpeechSynthesisVoice(language: "ro-RO")` is non-nil.
- Otherwise it says `String(localized: "are_you_ok_title")` once, with that voice.
- Call it from `.onAppear`.
- Don't touch `AVAudioSession` categories: the workout session owns the audio.
- If it misbehaves on the device (Task 5), delete `PromptVoice` and its call. That's the agreed fallback.

- [ ] **Step 4: Build**

Same build command as Task 2, step 3. Expected: success.

- [ ] **Step 5: Look at it on the 42 mm simulator**

Trigger it with the Debug button (`force_fall`). Check:
- Both buttons are visible with no scrolling.
- The ring drains over 15 s.
- When the ring empties, the prompt closes (it goes to the confirmation once Task 4 lands; home before that).

- [ ] **Step 6: Largest text size**

In the simulator, set Settings › Display & Brightness › Text Size to the largest, and turn on Bold Text. Trigger the prompt again.
Expected: the content scrolls, and both buttons can be reached and tapped.

- [ ] **Step 7: Format, lint, run the watch tests, commit**

```bash
git add ios/EchoCareWatch/Screens/AreYouOkView.swift ios/EchoCareWatch/Localizable.xcstrings
git commit -m "Watch: full-screen Sunteți bine? with a draining ring, double tap and voice"
```

---

### Task 4: "Help is coming" confirmation

**Files:**
- Create: `ios/EchoCareWatch/Screens/HelpComingView.swift`
- Modify: `ios/EchoCareWatch/EchoCareWatchApp.swift` (`RootView`)
- Modify: `ios/EchoCareWatch/Localizable.xcstrings`

**Interfaces:**
- Consumes: `Monitor.alert`, `Alert.phase(nowMs:)`, `Monitor.dismissAlert(id:)`, `Timings.helpShownMs` (Task 1), `Palette` (Task 2).
- Produces: `struct HelpComingView: View { let alert: Alert; let dismiss: () -> Void }`

- [ ] **Step 1: Strings**

| Key | Value |
|---|---|
| `help_sending` | `Anunțăm echipa…` |
| `help_keep_phone` | `Țineți telefonul aproape` |
| `help_retrying` | `Încercăm din nou…` |
| `help_received` | `Echipa a fost anunțată` |
| `help_answer_phone` | `Vă sunăm imediat. Răspundeți la telefon.` |

- [ ] **Step 2: Write `HelpComingView`**

A `TimelineView(.periodic(from: .now, by: 1))` switches on `alert.phase(nowMs:)`:
- **`.sending`:** a large `ProgressView`, `help_sending` as `.headline`, and `help_keep_phone` as `.body` `.secondary`.
- **`.retrying`:** the same, with `help_retrying` in place of `help_keep_phone`.
- **`.received`:** a green circle (`Palette.yes`) about 64 pt with a white `checkmark`, `help_received` as `.headline`, and `help_answer_phone` as `.body`.

Behaviour:
- In `.received`, a tap anywhere calls `dismiss()`.
- `.task(id: alert.receivedAtMs)`: when `receivedAtMs` is set, sleep `Timings.helpShownMs` ms, then call `dismiss()`.
- Text centered, allowed to wrap, in a `ScrollView` so large text sizes scroll.

- [ ] **Step 3: `RootView` priority**

1. If `monitor.prompt` is set, show `AreYouOkView` (as today).
2. Else if `monitor.alert` is set, show `HelpComingView(alert:)` with `dismiss: { monitor.dismissAlert(id: alert.id) }`.
3. Else show `HomeView`.

Update the doc comment.

- [ ] **Step 4: Build, then look at it on the simulator**

Same build command as Task 2, step 3. Press „Nu mă simt bine”. Expected:
- „Anunțăm echipa…” at once.
- „Încercăm din nou…” after 20 s. The simulator has no phone link, so it never gets an ack.

Then press `force_fall` while the confirmation shows. Expected: the prompt replaces it.

- [ ] **Step 5: Format, lint, run the watch tests, commit**

```bash
git add ios/EchoCareWatch/Screens/HelpComingView.swift ios/EchoCareWatch/EchoCareWatchApp.swift ios/EchoCareWatch/Localizable.xcstrings
git commit -m "Watch: show help is coming, and confirm once the team has the alert"
```

---

### Task 5: Check on the real watch

The simulator can't show WatchConnectivity, the ack, double tap or the ro-RO voice. No code is expected in this task, apart from dropping `PromptVoice` if step 4 fails.

- [ ] **Step 1: Build and install on the phone and the watch**

Use Alex's Mac, and the iPhone and watch commands in `ios/AGENTS.md` (Commands table). Sign in on the phone as the demo senior, against staging or local.

- [ ] **Step 2: Help button**

Press „Nu mă simt bine”. Expected:
- „Anunțăm echipa…”, then within a few seconds the ✓ screen with a success buzz.
- The dashboard shows the `manual_request`.
- The screen goes home after 60 s, or on a tap.

- [ ] **Step 3: Prompt and timeout**

1. Press `force_fall` and answer „Nu”. Expected: the confirmation, then ✓.
2. Press `force_fall` again and let it time out. Expected: the same.
3. Press `force_fall` again and answer „Da” with a thumb-and-finger double tap (Series 9 or later, or Ultra 2). Expected: back to home, no confirmation.

- [ ] **Step 4: Voice**

Expected: on `force_fall` the watch says „Sunteți bine?” once, and the buzzing continues. If no ro-RO voice is installed it stays silent; note that for the demo, and install the voice from the watch's Siri/VoiceOver settings if you want it. If speech breaks the haptics or the workout, delete `PromptVoice`, commit, and rebuild.

- [ ] **Step 5: Wrist down**

Press help, lower the wrist, and wait for the ack. Expected: the success buzz is felt, and on wrist raise the ✓ screen still shows.

- [ ] **Step 6: Phone out of reach**

Turn on airplane mode on the phone, then press help. Expected:
- „Încercăm din nou…” after 20 s.
- With the phone back online, the queued event is resent within a minute and the screen turns to ✓.
