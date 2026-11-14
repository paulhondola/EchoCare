import Foundation
import Testing

@testable import EchoCare

// UC-11: Preiau and Trimite against a stubbed API, as Android's IncidentViewModel and
// ResolveViewModel behave. A refusal shows its line, and the page is read again.
private let openJSON = """
    {"id": "i1", "status": "open", "reason": "Durere în piept", "opened_at": "2026-10-22T19:00:00Z",
     "senior": {"id": "s1", "full_name": "Dumitru Pop", "form_of_address": "domnul Dumitru",
     "phone_e164": "+40700000113", "phone_is_landline": false}}
    """
private let rowJSON = """
    {"id": "i1", "senior_full_name": "Dumitru Pop", "senior_form_of_address": "domnul Dumitru",
     "status": "in_progress", "reason": "Durere în piept", "opened_at": "2026-10-22T19:00:00Z"}
    """
private let takenJSON = openJSON.replacingOccurrences(of: #""open""#, with: #""in_progress""#)

@MainActor
struct IncidentModelTests {
    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    private func api(_ stub: StubURLProtocol.Stub) -> ApiClient {
        ApiClient(baseURL: URL(string: "https://api.test")!, tokens: NoToken(), session: stub.session())
    }

    /// The incident page answers `page`; a POST answers `command`.
    private func stub(page: String = openJSON, command: StubURLProtocol.Reply) -> StubURLProtocol.Stub {
        StubURLProtocol.Stub { sent in sent.method == "POST" ? command : .init(200, page) }
    }

    @Test func takingReadsThePageAgain() async {
        let s = stub(page: takenJSON, command: .init(200, rowJSON))
        // The row the take returns is not read: the page is
        let model = IncidentModel(id: "i1", api: api(s))
        await model.take()
        #expect(model.notice == nil)
        #expect(!model.taking)
        guard case .ready(let page, _) = model.page else { Issue.record("not read"); return }
        #expect(page.status == "in_progress")
        #expect(s.requests.map(\.method) == ["POST", "GET"])
    }

    @Test func aTakeSomeoneElseWonNamesThemAndReadsAgain() async {
        let s = stub(
            command: .init(409, #"{"detail": {"reason": "already_done", "taken_by_name": "Cristian Pavel"}}"#))
        let model = IncidentModel(id: "i1", api: api(s))
        await model.take()
        #expect(model.notice == .takenBy("Cristian Pavel"))
        #expect(s.requests.last?.method == "GET")
    }

    @Test func aTakeWithNoConnectionSaysSoAndKeepsTheLastPage() async {
        let s = stub(command: .init(503, ""))
        let model = IncidentModel(id: "i1", api: api(s))
        await model.load()
        await model.take()
        #expect(model.notice == .says("send_failed"))
    }

    @Test func aSignedOutTakeEndsAndReadsNothingMore() async {
        let s = stub(command: .init(401, ""))
        let model = IncidentModel(id: "i1", api: api(s))
        await model.take()
        #expect(model.notice == .ends(.signedOut))
        // A 401 is retried once with a fresh token, then the page is not read
        #expect(!s.requests.contains { $0.method == "GET" })
    }

    @Test func aGoodReadClearsTheNotice() async {
        let s = stub(command: .init(403, ""))
        let model = IncidentModel(id: "i1", api: api(s))
        await model.take()
        #expect(model.notice == .says("not_allowed_action"))
        await model.load()
        #expect(model.notice == nil)
    }

    @Test func resolvingSendsTheTrimmedNoteAndLeaves() async throws {
        let s = stub(command: .init(200, rowJSON))
        let model = ResolveModel(id: "i1", api: api(s))
        model.outcome = "team_sent"
        model.note = "  Echipa a ajuns.  "
        await model.submit()
        #expect(model.done)
        let body = try JSONSerialization.jsonObject(with: #require(s.requests.first).body) as? [String: String]
        #expect(body == ["outcome": "team_sent", "note": "Echipa a ajuns."])
    }

    @Test func aRefusedResolveKeepsWhatWasTyped() async {
        let s = stub(command: .init(409, #"{"detail": {"reason": "already_done"}}"#))
        let model = ResolveModel(id: "i1", api: api(s))
        model.outcome = "false_alarm"
        model.note = "Alarmă falsă"
        await model.submit()
        #expect(!model.done)
        #expect(model.notice == .says("already_resolved"))
        #expect(model.note == "Alarmă falsă")
        #expect(!model.sending)
    }

    @Test func nothingIsSentWithoutAnOutcome() async {
        let s = stub(command: .init(200, rowJSON))
        let model = ResolveModel(id: "i1", api: api(s))
        model.note = "x"
        await model.submit()
        #expect(s.requests.isEmpty)
    }
}
