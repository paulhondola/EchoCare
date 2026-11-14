import Foundation
import Shared
import Testing

@testable import EchoCareWatch

// UC-09, UC-13, 06 §3: the watch's rules, prompt and check-ins, as MonitoringService.kt and
// AreYouOkScreen.kt run them. The values are the demo timings (Debug builds), so the suite runs only there.

@MainActor
private final class FakeSensors: SensorSource {
    var heartRate: ((Int64, Int) -> Void)?
    var acceleration: ((Int64, Float) -> Void)?
    var steps: ((Int64, Int) -> Void)?
    var ended: (() -> Void)?
    var failure: (any Error)?
    var stops = 0

    func start(
        onHeartRate: @escaping (Int64, Int) -> Void,
        onAcceleration: @escaping (Int64, Float) -> Void,
        onSteps: @escaping (Int64, Int) -> Void,
        onEnded: @escaping () -> Void
    ) async throws {
        if let failure { throw failure }
        heartRate = onHeartRate
        acceleration = onAcceleration
        steps = onSteps
        ended = onEnded
    }

    func stop() { stops += 1 }
}

@MainActor
private final class FakeLink: PhoneSending {
    var events: [EventMessage] = []
    var checkIns: [CheckInMessage] = []

    func send(event: EventMessage) { events.append(event) }
    func send(checkIn: CheckInMessage) { checkIns.append(checkIn) }
}

private final class FakeClock {
    var now: Int64 = 1_793_304_000_000
}

private struct Denied: Error {}

// The FallDetector traces of Task 2's FallDetectorTests: 50 readings a second, shaped after S13.
private struct Trace {
    static let periodMs: Int64 = 20
    var readings: [Float] = []

    mutating func hold(_ g: Float, ms: Int64) {
        readings.append(contentsOf: Array(repeating: g, count: Int(ms / Self.periodMs)))
    }

    mutating func impact(_ g: Float) { readings.append(g) }

    // Arm movement, alternating around 1 g by more than the stillness tolerance
    mutating func move(ms: Int64) {
        for i in 0..<Int(ms / Self.periodMs) { readings.append(i % 2 == 0 ? 0.6 : 1.6) }
    }
}

@MainActor
@Suite(.enabled(if: Timings.demo, "demo timings: run the Debug configuration"))
struct MonitorTests {
    private let sensors = FakeSensors()
    private let link = FakeLink()
    private let clock = FakeClock()
    private let queue = EventQueue(
        directory: FileManager.default.temporaryDirectory
            .appending(path: "echocare-monitor-\(UUID().uuidString)", directoryHint: .isDirectory))
    private let monitor: Monitor
    private let startedAt: Int64

    init() async {
        let clock = clock
        monitor = Monitor(sensors: sensors, link: link, queue: queue, clock: { clock.now }, ticking: false)
        startedAt = clock.now
        await monitor.start()
    }

    private func heartRate(_ bpm: Int, at ms: Int64) {
        clock.now = ms
        sensors.heartRate?(ms, bpm)
    }

    private func feed(_ trace: Trace, from start: Int64) {
        for (i, g) in trace.readings.enumerated() {
            let ms = start + Int64(i) * Trace.periodMs
            clock.now = ms
            sensors.acceleration?(ms, g)
        }
    }

    private func tick(at ms: Int64) {
        clock.now = ms
        monitor.tick(nowMs: ms)
    }

    /// Baseline 60 from ten still readings, then 90 bpm still for the 15 s demo hold. Readings
    /// 7.5 s apart: the still 90s join the baseline too, and at 5 s apart they lift it past 65
    /// before the hold ends (RestingBaseline, as on Wear OS).
    private func raiseHighPulse(from start: Int64? = nil, bpm: Int = 90) -> Int64 {
        var t = start ?? startedAt
        for _ in 0..<10 {
            t += 5_000
            heartRate(60, at: t)
        }
        for _ in 0..<3 {
            t += 7_500
            heartRate(bpm, at: t)
        }
        return t
    }

    private func fall() -> Trace {
        var trace = Trace()
        trace.hold(1, ms: 1_000)
        trace.impact(8.3)
        trace.move(ms: 1_500)
        trace.hold(1, ms: 15_000)
        return trace
    }

    @Test func startRunsTheSession() {
        #expect(monitor.running)
        #expect(monitor.prompt == nil)
    }

    @Test func highPulseAtRestRaisesPrompt() {
        let at = raiseHighPulse()
        let prompt = monitor.prompt
        #expect(prompt?.type == "high_pulse_at_rest")
        #expect(prompt?.snapshot.pulse == 90)
        #expect(prompt?.snapshot.moving == false)
        #expect(prompt?.deadlineMs == at + 15_000)
        #expect(link.events.isEmpty)
    }

    @Test func aPulseHighForLessThanTheHoldRaisesNothing() {
        var t = startedAt
        for _ in 0..<10 {
            t += 5_000
            heartRate(60, at: t)
        }
        heartRate(90, at: t + 5_000)
        heartRate(90, at: t + 14_000)
        #expect(monitor.prompt == nil)
    }

    @Test func answerOkSendsNothing() {
        _ = raiseHighPulse()
        monitor.answer(ok: true)
        #expect(monitor.prompt == nil)
        #expect(link.events.isEmpty)
        #expect(queue.pending().isEmpty)
    }

    @Test func answerNoSendsEventOnce() throws {
        _ = raiseHighPulse()
        let prompt = try #require(monitor.prompt)
        monitor.answer(ok: false)
        monitor.answer(ok: false)
        let sent = EventMessage(
            id: prompt.id, type: "high_pulse_at_rest", measuredAt: prompt.measuredAt,
            snapshot: prompt.snapshot)
        #expect(link.events == [sent])
        #expect(queue.pending() == [sent])
        #expect(monitor.prompt == nil)
    }

    @Test func timeoutSendsEvent() throws {
        let at = raiseHighPulse()
        let prompt = try #require(monitor.prompt)
        tick(at: at + 14_999)
        #expect(link.events.isEmpty)
        #expect(monitor.prompt == prompt)
        tick(at: at + 15_000)
        #expect(link.events.map(\.id) == [prompt.id])
        #expect(monitor.prompt == nil)
    }

    @Test func promptResolvesOnce() throws {
        // A late „Nu" after the timeout sends nothing more. The tick that timed it out is also
        // past the first minute, so it resends the queue: count events, not sends.
        let at = raiseHighPulse()
        tick(at: at + 15_000)
        monitor.answer(ok: false)
        monitor.answer(ok: true)
        #expect(Set(link.events.map(\.id)).count == 1)
        #expect(queue.pending().count == 1)

        // A second anomaly while a prompt shows raises no second prompt. The first one's readings
        // lifted the baseline, so this one needs a higher pulse.
        let again = raiseHighPulse(from: at + 20_000, bpm: 120)
        let prompt = try #require(monitor.prompt)
        feed(fall(), from: again)
        #expect(monitor.prompt == prompt)
        monitor.answer(ok: false)
        #expect(link.events.map(\.id).last == prompt.id)
        #expect(Set(link.events.map(\.id)).count == 2)
        #expect(queue.pending().count == 2)
    }

    @Test func fallRaisesPrompt() {
        feed(fall(), from: startedAt)
        #expect(monitor.prompt?.type == "fall")
        #expect(link.events.isEmpty)
    }

    @Test func inactivityRaisesPromptAfterTheDemoMinute() {
        // The first reading is the day's count so far, not a step
        sensors.steps?(startedAt + 1_000, 120)
        sensors.steps?(startedAt + 2_000, 125)
        tick(at: startedAt + 61_999)
        #expect(monitor.prompt == nil)
        tick(at: startedAt + 62_000)
        #expect(monitor.prompt?.type == "inactivity")
        #expect(monitor.prompt?.snapshot.minutesWithoutSteps == 1)
    }

    @Test func checkInEveryMinuteInDemo() throws {
        heartRate(72, at: startedAt + 5_000)
        sensors.steps?(startedAt + 6_000, 300)
        tick(at: startedAt + 30_000)
        #expect(link.checkIns.isEmpty)
        tick(at: startedAt + 60_000)
        #expect(link.checkIns.count == 1)
        tick(at: startedAt + 90_000)
        #expect(link.checkIns.count == 1)
        tick(at: startedAt + 120_000)
        #expect(link.checkIns.count == 2)

        let checkIn = try #require(link.checkIns.first)
        #expect(checkIn.worn)
        #expect(checkIn.lastPulse == 72)
        #expect(checkIn.stepsToday == 300)
        #expect(checkIn.restingPulse == nil)
        #expect(checkIn.measuredAt == "2026-10-29T20:01:00.000Z")
    }

    @Test func pendingEventsAreResentEachMinuteUntilAcked() throws {
        _ = raiseHighPulse()
        monitor.answer(ok: false)
        let id = try #require(link.events.first?.id)
        tick(at: startedAt + 120_000)
        #expect(link.events.map(\.id) == [id, id])
        queue.ack(id: id)
        tick(at: startedAt + 180_000)
        #expect(link.events.count == 2)
    }

    @Test func callMeSendsAManualRequest() {
        monitor.callMe()
        #expect(link.events.map(\.type) == ["manual_request"])
        #expect(link.events.first?.snapshot == nil)
        #expect(queue.pending().count == 1)
    }

    @Test func monitorStateFollowsSessionEnd() {
        sensors.ended?()
        #expect(!monitor.running)
        tick(at: startedAt + 60_000)
        tick(at: startedAt + 120_000)
        #expect(link.checkIns.isEmpty)
        // Readings after the end, if any arrive, are not acted on
        feed(fall(), from: startedAt + 130_000)
        #expect(monitor.prompt == nil)
    }

    @Test func aPromptShowingWhenTheSessionEndsStillTimesOut() {
        let at = raiseHighPulse()
        sensors.ended?()
        tick(at: at + 15_000)
        #expect(link.events.count == 1)
    }

    @Test func stopStopsTheSensorsAndTheCheckIns() {
        monitor.stop()
        #expect(!monitor.running)
        #expect(sensors.stops == 1)
        tick(at: startedAt + 60_000)
        #expect(link.checkIns.isEmpty)
    }

    @Test func aFailedStartLeavesItStopped() async {
        let sensors = FakeSensors()
        sensors.failure = Denied()
        let clock = clock
        let other = Monitor(sensors: sensors, link: link, queue: queue, clock: { clock.now }, ticking: false)
        await other.start()
        #expect(!other.running)
        #expect(other.startFailed)
    }

    #if DEBUG
    @Test func aForcedAnomalyRaisesThePromptWithAFakeSnapshot() {
        monitor.forceAnomaly(type: "inactivity")
        #expect(monitor.prompt?.type == "inactivity")
        #expect(monitor.prompt?.snapshot.minutesWithoutSteps == 240)
        monitor.answer(ok: false)
        #expect(link.events.map(\.type) == ["inactivity"])
    }
    #endif
}
