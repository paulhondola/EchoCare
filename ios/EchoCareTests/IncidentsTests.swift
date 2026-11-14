import Foundation
import Testing

@testable import EchoCare

// UC-12: the relative times and the call timeline the medic's patient page shares with the DAS
// screens. Ported from the matching cases of Android's das/IncidentsTest.kt; Task 11 adds the rest
// of that file.
struct IncidentsTests {
    private let now = instant("2026-10-22T20:00:00Z")!

    @Test func agoBoundaries() {
        func before(_ seconds: TimeInterval) -> String {
            ISO8601DateFormatter().string(from: now.addingTimeInterval(-seconds))
        }
        #expect(ago(before(30), now: now) == .moments)
        #expect(ago(before(59 * 60), now: now) == .minutes(59))
        #expect(ago(before(60 * 60), now: now) == .hours(1, 0))
        #expect(ago(before((23 * 60 + 59) * 60), now: now) == .hours(23, 59))
        #expect(ago(before(24 * 3600), now: now) == .on(now.addingTimeInterval(-24 * 3600)))
        // A phone clock behind the server's
        #expect(ago(ISO8601DateFormatter().string(from: now.addingTimeInterval(90)), now: now) == .moments)
    }

    @Test func agoReadsFastApiTimestamps() {
        #expect(ago("2026-10-22T19:06:55.123456+00:00", now: now) == .minutes(53))
    }

    private func at(_ hm: String) -> String { "2026-10-22T\(hm):00Z" }

    private func report(_ severity: String, _ quote: String?, _ hm: String) -> CallReport {
        CallReport(severity: severity, reason: "R \(hm)", quote: quote, at: at(hm))
    }

    private func turn(_ hm: String) -> CallTurn { CallTurn(speaker: "senior", content: "T \(hm)", at: at(hm)) }

    private func call(reports: [CallReport] = [], turns: [CallTurn] = []) -> IncidentCall {
        IncidentCall(id: "c", trigger: "campaign", attempt: 1, state: "completed", reports: reports, turns: turns)
    }

    @Test func timelinePutsReportsWhereTheyHappened() {
        let flagged = report("red", "q", "19:41")
        let c = call(reports: [flagged], turns: [turn("19:34"), turn("19:41"), turn("19:48")])
        #expect(
            timeline(c) == [.said(turn("19:34")), .said(turn("19:41")), .flagged(flagged), .said(turn("19:48"))])
    }

    @Test func timelineOfACallWithNoTurns() {
        #expect(timeline(call()).isEmpty)
    }
}
