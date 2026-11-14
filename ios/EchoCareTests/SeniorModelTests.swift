import Foundation
import Testing

@testable import EchoCare

// „Pornește monitorizarea” says what happened, not what was hoped (design, Monitoring), and
// clears once the phone stops hearing from the watch.
@MainActor
struct SeniorModelTests {
    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    private func model(
        start: @escaping @MainActor () async throws -> Void,
        startHealth: @escaping @MainActor () -> Void = {}
    ) -> SeniorModel {
        SeniorModel(api: ApiClient(tokens: NoToken()), startWatch: start, startHealth: startHealth)
    }

    @Test func aStartThatThrowsIsFailedNotStarted() async {
        let model = model { throw WatchLinkError.notAvailable }
        await model.startMonitoring()
        #expect(model.monitoring == .failed)
    }

    @Test func aStartThatWorksIsStarted() async {
        let model = model {}
        await model.startMonitoring()
        #expect(model.monitoring == .started)
    }

    @Test func anotherTapIsAllowedOnceStarted() async {
        var starts = 0
        let model = model { starts += 1 }
        await model.startMonitoring()
        await model.startMonitoring()
        #expect(starts == 2)
    }

    // MARK: Apple Health sync

    @Test func loadStartsHealthSync() async {
        var starts = 0
        let model = model(start: {}, startHealth: { starts += 1 })
        await model.load()
        #expect(starts >= 1)
    }

    @Test func startedMonitoringStartsHealthSync() async {
        var starts = 0
        let model = model(start: {}, startHealth: { starts += 1 })
        await model.startMonitoring()
        #expect(starts == 1)
    }

    @Test func failedMonitoringDoesNotStartHealthSync() async {
        var starts = 0
        let model = model(
            start: { throw WatchLinkError.notAvailable }, startHealth: { starts += 1 })
        await model.startMonitoring()
        #expect(starts == 0)
    }

    // MARK: What the phone hears from the watch

    private let now = Date(timeIntervalSince1970: 1_000_000)
    private let interval: TimeInterval = 60

    private func after(
        _ state: Monitoring, heard: TimeInterval? = nil, started: TimeInterval? = nil,
        installed: Bool? = true
    ) -> Monitoring {
        monitoringAfter(
            state,
            seen: WatchSeen(
                lastHeard: heard.map { now.addingTimeInterval(-$0) }, appInstalled: installed),
            startedAt: started.map { now.addingTimeInterval(-$0) }, now: now, interval: interval)
    }

    @Test func aRecentCheckInOrEventMeansTheWatchIsRunning() {
        #expect(after(.idle, heard: 30) == .started)
        #expect(after(.failed, heard: 30) == .started)
        #expect(after(.started, heard: 119) == .started)
    }

    @Test func silenceForTwoIntervalsClearsStarted() {
        #expect(after(.started, heard: 121) == .idle)
        #expect(after(.started, heard: 300, started: 200) == .idle)
        // Nothing heard yet, but started just now: the first check-in is still to come
        #expect(after(.started, started: 90) == .started)
        #expect(after(.started, started: 121) == .idle)
    }

    @Test func aWatchAppNotInstalledClearsStarted() {
        #expect(after(.started, heard: 10, installed: false) == .idle)
        // Not yet known: WCSession hasn't activated
        #expect(after(.started, heard: 10, installed: nil) == .started)
    }

    @Test func silenceLeavesOtherStatesAlone() {
        #expect(after(.idle) == .idle)
        #expect(after(.failed, heard: 500) == .failed)
        #expect(after(.starting, heard: 10) == .starting)
        #expect(after(.starting, installed: false) == .starting)
    }

    @Test func theHomeReadsTheWatchOnEachReread() async {
        var seen = WatchSeen(lastHeard: nil, appInstalled: true)
        var clock = now
        let model = SeniorModel(
            api: ApiClient(tokens: NoToken()), startWatch: {}, watchSeen: { seen }, now: { clock },
            checkInInterval: interval)
        await model.startMonitoring()
        #expect(model.monitoring == .started)
        clock = now.addingTimeInterval(200)
        model.refreshMonitoring()
        #expect(model.monitoring == .idle)
        seen.lastHeard = clock
        model.refreshMonitoring()
        #expect(model.monitoring == .started)
    }
}
