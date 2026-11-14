import Foundation
import Testing

@testable import EchoCare

// UC-12, design §"The list": what the DAS home shows, in which order. Ported case for case from
// Android's das/IncidentsTest.kt. `mapsUri` differs on purpose: Android's `geo:` URI means nothing
// to iOS, so it is an Apple Maps link with the same inputs.
struct IncidentsTests {
    private func row(_ id: String, _ status: String, _ openedAt: String, takenAt: String? = nil) -> IncidentRow {
        IncidentRow(
            id: id, seniorName: "Dumitru Pop", formOfAddress: "domnul Dumitru", status: status,
            reason: "Durere în piept", openedAt: "2026-10-22T\(openedAt):00Z",
            takenByName: takenAt.map { _ in "DAS Test" }, takenAt: takenAt.map { "2026-10-22T\($0):00Z" })
    }

    @Test func openComeFirstOldestFirst() {
        let rows = ["19:15", "19:06", "18:29"].map { row($0, "open", $0) }
        #expect(sections(rows).open.map(\.id) == ["18:29", "19:06", "19:15"])
    }

    @Test func inProgressSortsByTakeTimeThenOpenTime() {
        let rows = [
            row("A", "in_progress", "18:00", takenAt: "19:00"),
            // No take time: the open time stands in
            row("B", "in_progress", "18:30"),
        ]
        #expect(sections(rows).inProgress.map(\.id) == ["B", "A"])
    }

    @Test func unknownStatusIsLeftOut() {
        let s = sections([row("R", "resolved", "18:00"), row("X", "archived", "18:00")])
        #expect(s.open.isEmpty)
        #expect(s.inProgress.isEmpty)
    }

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


    @Test func timelinePutsReportsWhereTheyHappened() {
        let flagged = report("red", "q", "19:41")
        let c = call(reports: [flagged], turns: [turn("19:34"), turn("19:41"), turn("19:48")])
        #expect(
            timeline(c) == [.said(turn("19:34")), .said(turn("19:41")), .flagged(flagged), .said(turn("19:48"))])
    }

    @Test func timelineOfACallWithNoTurns() {
        #expect(timeline(call()).isEmpty)
    }

    // design §"The incident page"

    private let street = IncidentSenior(
        id: "s", fullName: "Dumitru Pop", formOfAddress: "domnul Dumitru", phone: "+40700000113",
        landline: false, street: "Strada Bucovinei", streetNumber: "27")

    private func call(
        _ id: String = "c", state: String = "completed", startedAt: String? = nil,
        reports: [CallReport] = [], turns: [CallTurn] = []
    ) -> IncidentCall {
        IncidentCall(
            id: id, trigger: "campaign", attempt: 1, state: state, startedAt: startedAt.map(at),
            reports: reports, turns: turns)
    }

    @Test func seniorsWordsIsTheLatestRedQuote() {
        let calls = [
            call("a", reports: [report("yellow", "q1", "19:00"), report("red", "q2", "19:06")]),
            call("b", reports: [report("red", "q3", "19:20")]),
        ]
        #expect(seniorsWords(calls) == "q3")
    }

    @Test func noRedQuoteMeansNoWords() {
        let calls = [
            call(reports: [report("red", nil, "19:00"), report("red", "  ", "19:05"), report("yellow", "q", "19:10")])
        ]
        #expect(seniorsWords(calls) == nil)
        #expect(seniorsWords([]) == nil)
    }

    @Test func newestCallFirstIsTheApisOrderReversed() {
        // GET /incidents/{id} sends calls oldest first. An unanswered call never started, so its
        // start time cannot order it.
        let calls = [call("1", startedAt: "18:00"), call("2", state: "unanswered"), call("3", startedAt: "19:00")]
        #expect(newestFirst(calls).map(\.id) == ["3", "2", "1"])
    }

    @Test func liveWhenRingingOrInProgress() {
        #expect(callLive([call(state: "completed"), call(state: "ringing")]))
        #expect(callLive([call(state: "in_progress")]))
        #expect(!callLive([call(state: "handed_over"), call(state: "unanswered")]))
    }

    @Test func mapsUsesCoordinatesWhenThereAreAny() {
        let event = TriggerEvent(type: "sos_button", measuredAt: at("19:05"), latitude: 45.7489, longitude: 21.2087)
        #expect(mapsUrl(street, event) == "https://maps.apple.com/?ll=45.7489,21.2087&q=45.7489,21.2087")
    }

    @Test func mapsFallsBackToTheAddress() {
        #expect(mapsUrl(street, nil) == "https://maps.apple.com/?q=Strada%20Bucovinei%2027%2C%20Timi%C8%99oara")
    }

    @Test func noPlaceMeansNoMapsLink() {
        var nowhere = street
        nowhere.street = nil
        nowhere.streetNumber = nil
        #expect(mapsUrl(nowhere, TriggerEvent(type: "fall", measuredAt: at("19:05"))) == nil)
    }

    // design §"Preiau", §"Rezolvare caz"

    @Test func onlyOpenAndInProgressHaveAnAction() {
        #expect(actFor("open") == .take)
        #expect(actFor("in_progress") == .resolve)
        #expect(actFor("resolved") == nil)
        #expect(actFor("archived") == nil)
    }

    @Test func takeRefusals() {
        #expect(noticeAfter(.alreadyDone(takenByName: "Cristian Pavel"), act: .take) == .takenBy("Cristian Pavel"))
        #expect(noticeAfter(.alreadyDone(takenByName: nil), act: .take) == .says("incident_changed"))
        #expect(noticeAfter(.wrongState, act: .take) == .says("incident_changed"))
        #expect(noticeAfter(.failed(.noConnection), act: .take) == .says("send_failed"))
        #expect(noticeAfter(.failed(.notAllowed), act: .take) == .says("not_allowed_action"))
        #expect(noticeAfter(.failed(.notFound), act: .take) == .says("incident_gone"))
        #expect(noticeAfter(.failed(.signedOut), act: .take) == .ends(.signedOut))
        #expect(noticeAfter(.invalid([]), act: .resolve) == .says("send_failed"))
    }

    @Test func resolveRefusals() {
        #expect(noticeAfter(.alreadyDone(takenByName: "X"), act: .resolve) == .says("already_resolved"))
        #expect(noticeAfter(.wrongState, act: .resolve) == .says("incident_changed"))
    }

    @Test func sendNeedsAnOutcomeAndANote() {
        #expect(!canSend(nil, "x"))
        #expect(!canSend("team_sent", "   "))
        #expect(!canSend("team_sent", String(repeating: "a", count: 1001)))
        #expect(canSend("team_sent", String(repeating: "a", count: 1000)))
    }

    @Test func outcomesInTheDashboardsOrder() {
        #expect(
            OUTCOMES.map(\.value) == ["senior_ok", "team_sent", "called_112", "not_reached", "false_alarm"])
    }

    // Final review fixes

    @Test func unknownAccuracyIsLeftOutNotZero() {
        var e = TriggerEvent(type: "sos_button", measuredAt: at("19:05"), latitude: 45.7489, longitude: 21.2087)
        #expect(location(e) == Location(latitude: "45.74890", longitude: "21.20870", accuracy: nil))
        e.latitude = 45.748912345678
        e.longitude = 21.20871234567
        #expect(location(e) == Location(latitude: "45.74891", longitude: "21.20871", accuracy: nil))
        e.accuracy = 14.4
        #expect(location(e)?.accuracy == 14)
        e.latitude = nil
        #expect(location(e) == nil)
    }

    @Test func aNewerCallOpensWhenItArrives() {
        // The dispatcher opened the old call; a redial then joined the incident.
        let toggled = ["old": true]
        #expect(expanded("redial", newestId: "redial", toggled: toggled))
        #expect(expanded("old", newestId: "redial", toggled: toggled))
        #expect(!expanded("other", newestId: "redial", toggled: toggled))
        // A newest call the dispatcher closed stays closed
        #expect(!expanded("redial", newestId: "redial", toggled: ["redial": false]))
    }

    // The dashboard's colour per status: red, yellow, green (IncidentCard.svelte BAR)
    @Test func statusTonesMatchTheDashboard() {
        #expect(statusTone("open") == .rosu)
        #expect(statusTone("in_progress") == .galben)
        #expect(statusTone("resolved") == .verde)
        #expect(statusTone("archived") == .muted)
    }
}
