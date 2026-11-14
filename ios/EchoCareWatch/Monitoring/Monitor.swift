import Foundation
import Observation
import Shared
import WatchKit
import os

/// 06 §3's timings. Debug builds are demo builds (`DEMO`, Wear OS `BuildConfig.DEMO`); Release uses
/// the production values.
enum Timings {
    #if DEMO
        static let demo = true
        static let pulseHoldMs: Int64 = 15_000
        static let inactivityMs: Int64 = 60_000
        // UC-09 §2 step 3
        static let promptTimeoutMs: Int64 = 15_000
    #else
        static let demo = false
        static let pulseHoldMs: Int64 = 60_000
        static let inactivityMs: Int64 = 4 * 60 * 60_000
        static let promptTimeoutMs: Int64 = 120_000
    #endif
    // Under the 90 s and 45 min silence limits (UC-13); the phone reads the same value
    static let checkInMinutes = CheckInInterval.minutes(demo: demo)
    // „Sunteți bine?” buzzes again this often while it shows; a fall's sound follows the first buzz
    static let promptBuzzMs: Int64 = 3_000
    static let fallSoundDelayMs: Int64 = 1_000
    // 50 readings a second, the rate fall detection needs (P19)
    static let accelerometerHz: Double = 50
    // How long after the last step the wearer is still considered to be moving (UC-09 "not moving")
    static let movingWindowMs: Int64 = 30_000
    static let minuteMs: Int64 = 60_000
}

/// The sensors behind `Monitor`: `WorkoutRunner` on the watch, a fake in tests. Every reading
/// carries its wall-clock time in milliseconds. `onSteps` gets the day's step count so far, which
/// only grows. `onEnded` fires when the session ends without `stop()`, for example when the system
/// ends the workout. Main-actor isolated, so the callbacks run on the main actor.
@MainActor
protocol SensorSource: AnyObject {
    func start(
        onHeartRate: @escaping (Int64, Int) -> Void,
        onAcceleration: @escaping (Int64, Float) -> Void,
        onSteps: @escaping (Int64, Int) -> Void,
        onEnded: @escaping () -> Void
    ) async throws
    func stop()
}

/// The watch → phone messages (04 §3). `PhoneLink` on the watch, a fake in tests.
@MainActor
protocol PhoneSending: AnyObject {
    func send(event: EventMessage)
    func send(checkIn: CheckInMessage)
}

/// The watch's haptics: `WKInterfaceDevice.play` on the watch, a recorder in tests.
typealias Haptics = @MainActor (WKHapticType) -> Void

/// „Sunteți bine?", raised by a detector or the Debug trigger. `deadlineMs` is when silence sends it.
struct Prompt: Equatable {
    var id: String
    var type: String
    var measuredAt: String
    var snapshot: EventSnapshot
    var deadlineMs: Int64
}

/// The watch's monitoring (G14, UC-09, UC-13), ported from `MonitoringService.kt` and the prompt's
/// timeout from `AreYouOkScreen.kt`. Runs the four detectors from `Shared` while the workout session
/// runs, raises „Sunteți bine?", sends a check-in every interval, and on „Nu" or silence queues the
/// event and sends it to the phone.
@Observable @MainActor
final class Monitor {
    private(set) var running = false
    private(set) var prompt: Prompt?
    /// The last valid heart rate, for the home screen.
    private(set) var lastHeartRate: Int?
    /// The last start failed, typically because Health access was refused (`permission_needed`).
    private(set) var startFailed = false
    private(set) var starting = false

    @ObservationIgnored private let sensors: any SensorSource
    @ObservationIgnored private let link: any PhoneSending
    @ObservationIgnored private let queue: EventQueue
    @ObservationIgnored private let clock: () -> Int64
    @ObservationIgnored private let ticking: Bool
    @ObservationIgnored private let haptics: Haptics
    @ObservationIgnored private let log = Logger(
        subsystem: "ro.echocare.watch", category: "monitor")

    // Fresh each session, as Wear OS gets a fresh MonitoringService
    @ObservationIgnored private var fallDetector = FallDetector()
    @ObservationIgnored private var restingBaseline = RestingBaseline()
    @ObservationIgnored private var pulseAnomaly = PulseAnomaly(holdMs: Timings.pulseHoldMs)
    @ObservationIgnored private var inactivity = InactivityDetector(limitMs: Timings.inactivityMs)

    @ObservationIgnored private var startedAtMs: Int64 = 0
    @ObservationIgnored private var lastMinuteMs: Int64 = 0
    @ObservationIgnored private var minute = 0
    @ObservationIgnored private var lastStepAtMs: Int64 = -1
    @ObservationIgnored private var stepCount = -1
    @ObservationIgnored private var tickTask: Task<Void, Never>?
    // While a prompt shows: when it last buzzed, and when a fall's sound is due
    @ObservationIgnored private var lastBuzzMs: Int64 = 0
    @ObservationIgnored private var fallSoundAtMs: Int64?

    /// `ticking: false` leaves `tick(nowMs:)` to the caller (tests); otherwise a loop calls it every
    /// second while the session runs or a prompt shows.
    init(
        sensors: any SensorSource,
        link: any PhoneSending,
        queue: EventQueue,
        clock: @escaping () -> Int64 = { Int64(Date().timeIntervalSince1970 * 1_000) },
        ticking: Bool = true,
        haptics: @escaping Haptics = { WKInterfaceDevice.current().play($0) }
    ) {
        self.sensors = sensors
        self.link = link
        self.queue = queue
        self.clock = clock
        self.ticking = ticking
        self.haptics = haptics
        // batteryLevel reads -1 until this is on
        WKInterfaceDevice.current().isBatteryMonitoringEnabled = true
    }

    func start() async {
        guard !running, !starting else { return }
        starting = true
        defer { starting = false }
        fallDetector = FallDetector()
        restingBaseline = RestingBaseline()
        pulseAnomaly = PulseAnomaly(holdMs: Timings.pulseHoldMs)
        inactivity = InactivityDetector(limitMs: Timings.inactivityMs)
        lastStepAtMs = -1
        stepCount = -1
        lastHeartRate = nil
        do {
            try await sensors.start(
                onHeartRate: { [weak self] at, bpm in self?.onHeartRate(atMs: at, bpm: bpm) },
                onAcceleration: { [weak self] at, g in self?.onAcceleration(atMs: at, g: g) },
                onSteps: { [weak self] at, count in self?.onSteps(atMs: at, count: count) },
                onEnded: { [weak self] in self?.sessionEnded() }
            )
        } catch {
            log.error("start failed: \(error.localizedDescription, privacy: .public)")
            startFailed = true
            return
        }
        startFailed = false
        running = true
        startedAtMs = clock()
        lastMinuteMs = startedAtMs
        minute = 0
        log.info("started battery=\(self.battery() ?? -1) pending=\(self.queue.pending().count)")
        // Resend anything the phone never acked
        resendPending()
        startTicking()
    }

    /// Stopped on the watch: no `onEnded`, the session simply goes.
    func stop() {
        guard running else { return }
        running = false
        sensors.stop()
        log.info("stopped after minute=\(self.minute)")
    }

    /// „Da" (`ok`) drops the prompt; „Nu" sends the event. Exactly one outcome per prompt: a late
    /// answer after the timeout does nothing (Review Focus 5).
    func answer(ok: Bool) {
        resolve(send: !ok)
    }

    func tick(nowMs: Int64) {
        if let prompt, nowMs >= prompt.deadlineMs {
            log.info("prompt \(prompt.id, privacy: .public) timed out")
            resolve(send: true)
        }
        if prompt != nil { buzz(nowMs: nowMs) }
        guard running else { return }
        if inactivity.isInactive(nowMs: nowMs) {
            raiseAnomaly("inactivity", snapshot(nowMs: nowMs))
        }
        // Wall-clock minutes, as on Wear OS
        if nowMs - lastMinuteMs >= Timings.minuteMs {
            lastMinuteMs = nowMs
            minute += 1
            // 06 §3: every 15 minutes, every minute in the demo; the first after a minute
            if minute == 1 || minute % Timings.checkInMinutes == 0 { sendCheckIn(nowMs: nowMs) }
            // The phone may have come back since the last tick
            resendPending()
        }
    }

    /// „Nu mă simt bine" (UC-10): a `manual_request`, queued and sent like any event.
    func callMe() {
        enqueueAndSend(
            EventMessage(id: UUID().uuidString, type: "manual_request", measuredAt: iso(clock())))
    }

    #if DEBUG
        /// Hand-raises a prompt with a fake snapshot, so the demo can show the whole UC-09 loop without
        /// a real anomaly (Debug only, `MonitoringService.forceAnomaly`).
        func forceAnomaly(type: String) {
            let nowMs = clock()
            raiseAnomaly(
                type,
                EventSnapshot(
                    pulse: type == "high_pulse_at_rest" ? 125 : lastHeartRate,
                    restingBaseline: restingBaseline.value(nowMs: nowMs),
                    moving: false,
                    minutesWithoutSteps: type == "inactivity" ? 240 : 0,
                    battery: battery()))
            log.info("forced anomaly=\(type, privacy: .public)")
        }
    #endif

    // MARK: Readings

    private func onHeartRate(atMs nowMs: Int64, bpm: Int) {
        guard running, bpm > 0 else { return }
        lastHeartRate = bpm
        let moving = isMoving(nowMs: nowMs)
        // Nil until enough still readings land, so the default can't raise a false alarm
        let baseline = restingBaseline.measured(nowMs: nowMs)
        restingBaseline.onReading(atMs: nowMs, bpm: bpm, moving: moving)
        if pulseAnomaly.onReading(atMs: nowMs, bpm: bpm, baselineBpm: baseline, moving: moving) {
            pulseAnomaly.reset()
            log.info("pulse anomaly bpm=\(bpm) baseline=\(baseline ?? -1)")
            raiseAnomaly("high_pulse_at_rest", snapshot(nowMs: nowMs))
        }
    }

    private func onAcceleration(atMs nowMs: Int64, g: Float) {
        guard running else { return }
        if fallDetector.onReading(timestampMs: nowMs, g: g) {
            log.info("fall detected")
            raiseAnomaly("fall", snapshot(nowMs: nowMs))
        }
    }

    private func onSteps(atMs nowMs: Int64, count: Int) {
        guard running else { return }
        // The first reading is the day's count so far; only a later increase is a step
        if stepCount >= 0, count > stepCount {
            lastStepAtMs = nowMs
            inactivity.onStep(atMs: nowMs)
        }
        stepCount = count
    }

    private func sessionEnded() {
        guard running else { return }
        // UC-13: stop visibly, and stop the check-ins, so the phone marks the watch offline
        running = false
        sensors.stop()
        log.info("session ended after minute=\(self.minute)")
    }

    // MARK: Prompt and events

    private func raiseAnomaly(_ type: String, _ snapshot: EventSnapshot) {
        // One prompt at a time: a second anomaly while one shows is dropped
        guard prompt == nil else {
            log.info("anomaly \(type, privacy: .public) dropped: a prompt is showing")
            return
        }
        let nowMs = clock()
        prompt = Prompt(
            id: UUID().uuidString, type: type, measuredAt: iso(nowMs), snapshot: snapshot,
            deadlineMs: nowMs + Timings.promptTimeoutMs)
        haptics(.notification)
        lastBuzzMs = nowMs
        // A fall also sounds (design, Watch app), a moment after the first buzz so the two don't merge
        fallSoundAtMs = type == "fall" ? nowMs + Timings.fallSoundDelayMs : nil
        startTicking()
    }

    /// Wear OS buzzes once; a watch on a lowered wrist is easy to miss, so the prompt buzzes again
    /// every few seconds until it is answered or times out (design, Watch app).
    private func buzz(nowMs: Int64) {
        if let at = fallSoundAtMs, nowMs >= at {
            fallSoundAtMs = nil
            haptics(.failure)
        }
        if nowMs - lastBuzzMs >= Timings.promptBuzzMs {
            lastBuzzMs = nowMs
            haptics(.notification)
        }
    }

    private func resolve(send: Bool) {
        guard let prompt else { return }
        self.prompt = nil
        fallSoundAtMs = nil
        guard send else { return }
        enqueueAndSend(
            EventMessage(
                id: prompt.id, type: prompt.type, measuredAt: prompt.measuredAt,
                snapshot: prompt.snapshot))
    }

    /// Queue first, then send: the phone's `received` clears it.
    private func enqueueAndSend(_ msg: EventMessage) {
        queue.enqueue(msg)
        link.send(event: msg)
    }

    private func resendPending() {
        let pending = queue.pending()
        if pending.isEmpty { return }
        log.info("resending \(pending.count) queued event(s)")
        pending.forEach { link.send(event: $0) }
    }

    private func sendCheckIn(nowMs: Int64) {
        link.send(
            checkIn: CheckInMessage(
                measuredAt: iso(nowMs),
                battery: battery(),
                // The design treats a running session as worn
                worn: true,
                lastPulse: lastHeartRate,
                restingPulse: restingBaseline.measured(nowMs: nowMs),
                stepsToday: stepCount >= 0 ? stepCount : nil,
                minutesWithoutSteps: minutesWithoutSteps(nowMs: nowMs)))
    }

    // MARK: Snapshot

    private func isMoving(nowMs: Int64) -> Bool {
        // shortcut, as on Wear OS: steps are the only movement signal
        lastStepAtMs > 0 && nowMs - lastStepAtMs < Timings.movingWindowMs
    }

    private func minutesWithoutSteps(nowMs: Int64) -> Int {
        Int((nowMs - (lastStepAtMs < 0 ? startedAtMs : lastStepAtMs)) / Timings.minuteMs)
    }

    private func snapshot(nowMs: Int64) -> EventSnapshot {
        EventSnapshot(
            pulse: lastHeartRate,
            restingBaseline: restingBaseline.value(nowMs: nowMs),
            moving: isMoving(nowMs: nowMs),
            minutesWithoutSteps: minutesWithoutSteps(nowMs: nowMs),
            battery: battery())
    }

    private func battery() -> Int? {
        let level = WKInterfaceDevice.current().batteryLevel
        // -1 while battery monitoring is off or the level is unknown (the simulator)
        return level < 0 ? nil : Int((level * 100).rounded())
    }

    private func iso(_ ms: Int64) -> String {
        Date.ISO8601FormatStyle(includingFractionalSeconds: true)
            .format(Date(timeIntervalSince1970: Double(ms) / 1_000))
    }

    // MARK: Ticks

    private func startTicking() {
        guard ticking, tickTask == nil else { return }
        tickTask = Task { [weak self] in
            while !Task.isCancelled {
                try? await Task.sleep(for: .seconds(1))
                guard let self else { return }
                self.tick(nowMs: self.clock())
                if !self.running && self.prompt == nil {
                    self.tickTask = nil
                    return
                }
            }
        }
    }
}
