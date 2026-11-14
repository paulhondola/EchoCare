import Foundation
import Testing

@testable import EchoCare

// The app reads a newer server leniently (ADR-001 §2.3); ported from android's ApiTest.kt.
struct ApiTests {}

extension ApiTests {
@Suite struct Decoding {
    // The same coders as ApiClient.
    private let decoder = ApiClient.makeDecoder()

    private func decode<T: Decodable>(_ type: T.Type, _ json: String) throws -> T {
        try decoder.decode(type, from: Data(json.utf8))
    }

    @Test func aRowOfSeniorsIsDecoded() throws {
        let rows = try decode(
            [SeniorRow].self,
            """
            [{"id": "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21", "full_name": "Maria Popescu",
              "form_of_address": "doamna Maria", "phone_e164": "+40256123456",
              "phone_is_landline": true, "enrollment_state": "draft"}]
            """)
        #expect(
            rows == [
                SeniorRow(
                    id: "0199b6f0-7c1e-7a55-b8d2-5d0c8c3a7f21", fullName: "Maria Popescu",
                    formOfAddress: "doamna Maria", phone: "+40256123456", landline: true,
                    state: "draft")
            ])
    }

    @Test func aRowWithACodeIsDecoded() throws {
        let rows = try decode(
            [SeniorRow].self,
            """
            [{"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
              "phone_e164": "+40256123456", "phone_is_landline": true,
              "enrollment_state": "active", "code": "yellow",
              "reason": "Nu are căldură în casă", "since": "2026-10-17T10:00:00Z"}]
            """)
        #expect(rows.first?.code == "yellow")
        #expect(rows.first?.reason == "Nu are căldură în casă")
        #expect(rows.first?.since == "2026-10-17T10:00:00Z")
    }

    private let page = """
        {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
         "phone_e164": "+40256123456", "phone_is_landline": true, "enrollment_state": "submitted",
         "street": "Str. Daliei", "street_number": "12", "block": null, "staircase": null,
         "floor": "2", "apartment": "9", "intercom_code": "09", "key_holder": null,
         "landmark": null, "call_window": "9-12",
         "medic": {"display_name": "Dr. Ion Pop", "practice": null},
         "caregivers": [{"user_id": "u1", "display_name": "Ioana Pop", "relation": "fiică",
                         "phone_e164": "+40700000004"}]}
        """

    @Test func aPageIsDecodedWithItsNulls() throws {
        let senior = try decode(SeniorPage.self, page)
        #expect(senior.street == "Str. Daliei")
        #expect(senior.streetNumber == "12")
        #expect(senior.block == nil)
        #expect(senior.medic == Medic(displayName: "Dr. Ion Pop", practice: nil))
        #expect(
            senior.caregivers == [
                Caregiver(
                    userId: "u1", displayName: "Ioana Pop", relation: "fiică",
                    phone: "+40700000004")
            ])
    }

    @Test func fieldsAndStatesALaterServerAddsAreNoProblem() throws {
        let later =
            page
            .replacingOccurrences(of: "\"submitted\"", with: "\"paused\"")
            .replacingOccurrences(of: "\"call_window\"", with: "\"code\": \"green\", \"call_window\"")
        let senior = try decode(SeniorPage.self, later)
        #expect(senior.state == "paused")
        #expect(senior.callWindow == "9-12")
    }

    @Test func aGrantKeepsOnlyItsRole() throws {
        let me = try decode(
            Me.self,
            """
            {"display_name": "Ana Pop", "phone_e164": "+40700000003", "grants": [
                {"role": "caregiver", "senior_id": "s1", "senior_form_of_address": "doamna Maria",
                 "relation": "fiică"}]}
            """)
        #expect(me == Me(displayName: "Ana Pop", grants: [Grant(role: "caregiver")]))
    }

    @Test func anOldProfileHasNoWarning() throws {
        let me = try decode(Me.self, #"{"display_name": "X", "grants": []}"#)
        #expect(!me.warningActive)
    }

    // GET /incidents/{id} as the local API serves it (04 §1), with a field a later server adds.
    @Test func anIncidentPageIsDecoded() throws {
        let incident = try decode(
            IncidentPage.self,
            """
            {"id":"92a0","status":"open","reason":"Durere în piept, greutate la respirație",
             "opened_at":"2026-10-22T19:06:55.123456+00:00","taken_by_name":null,"taken_at":null,
             "resolved_by_name":null,"resolved_at":null,"outcome":null,"note":null,
             "handover_answered":false,"future_field":1,
             "senior":{"id":"s1","full_name":"Dumitru Pop","form_of_address":"domnul Dumitru",
               "phone_e164":"+40700000113","phone_is_landline":false,"street":"Strada Bucovinei",
               "street_number":"27","block":"H4","staircase":"A","floor":"5","apartment":"31",
               "intercom_code":"31","key_holder":"Fiica, Simona, are cheie de rezervă",
               "landmark":"Lângă parcul din cartier"},
             "caregivers":[{"display_name":"Simona Pop","phone_e164":"+40700000211","relation":"fiică"}],
             "event":{"type":"sos_button","measured_at":"2026-10-22T19:05:00+00:00",
               "latitude":45.7489,"longitude":21.2087,"location_accuracy_m":14,"located_at":null},
             "calls":[{"id":"c1","trigger":"watch","attempt":1,"state":"handed_over",
               "started_at":"2026-10-22T19:06:30+00:00","ended_at":null,"final_severity":"red",
               "final_certainty":null,"reason":null,"summary":null,"handover_answered":null,
               "reports":[{"source":"agent","severity":"red","certainty":null,
                 "reason":"Durere în piept, greutate la respirație",
                 "quote":"Mă strânge în piept și nu pot respira bine.",
                 "at":"2026-10-22T19:06:42+00:00"}],
               "turns":[{"speaker":"senior","kind":"speech",
                 "content":"Mă strânge în piept și nu pot respira bine.",
                 "at":"2026-10-22T19:06:41+00:00"}]}]}
            """)
        #expect(incident.senior.street == "Strada Bucovinei")
        #expect(incident.event?.accuracy == 14.0)
        #expect(incident.calls.first?.handoverAnswered == nil)
        #expect(
            incident.calls.first?.reports.first?.quote == "Mă strânge în piept și nu pot respira bine.")
        #expect(incident.caregivers.first?.relation == "fiică")
    }

    @Test func aRowAndAPageFromAnOlderApiDecode() throws {
        // 04 §1: none of the medic panel's fields; they all read as nil.
        let row = try decode(
            SeniorRow.self,
            """
            {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
             "phone_e164": "+40256123456", "phone_is_landline": true,
             "enrollment_state": "draft"}
            """)
        #expect(row.createdAt == nil)
        #expect(row.submittedAt == nil)
        #expect(row.acceptedAt == nil)
        #expect(row.watchState == nil)
        let page = try decode(
            SeniorPage.self,
            """
            {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
             "phone_e164": "+40256123456", "phone_is_landline": true,
             "enrollment_state": "draft", "medic": {"display_name": "Dr. Ionescu"}}
            """)
        #expect(page.createdAt == nil)
        #expect(page.submittedAt == nil)
        #expect(page.acceptedAt == nil)
        #expect(page.consent == nil)
        #expect(page.consentGivenAt == nil)
        #expect(page.signedAt == nil)
        #expect(page.caregivers.isEmpty)
    }

    @Test func aPageWithConsentDecodes() throws {
        // 04 §2: decision and method stay strings, so a value added later still decodes.
        func consent(_ decision: String, _ method: String) -> String {
            #"{"decision": "\#(decision)", "method": "\#(method)", "at": "2026-10-06T08:00:00Z"}"#
        }
        func page(_ consent: String) throws -> SeniorPage {
            try decode(
                SeniorPage.self,
                """
                {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
                 "phone_e164": "+40256123456", "phone_is_landline": true,
                 "enrollment_state": "withdrawn", "medic": {"display_name": "Dr. Ionescu"},
                 "created_at": "2026-10-01T08:00:00Z", "submitted_at": "2026-10-02T08:00:00Z",
                 "accepted_at": "2026-10-03T08:00:00Z", "consent_given_at": "2026-10-04T08:00:00Z",
                 "signed_at": "2026-10-05T08:00:00Z", "consent": \(consent)}
                """)
        }
        let withdrawn = try page(consent("withdrawn", "medic"))
        #expect(
            withdrawn.consent
                == ConsentState(decision: "withdrawn", method: "medic", at: "2026-10-06T08:00:00Z"))
        #expect(withdrawn.createdAt == "2026-10-01T08:00:00Z")
        #expect(withdrawn.submittedAt == "2026-10-02T08:00:00Z")
        #expect(withdrawn.acceptedAt == "2026-10-03T08:00:00Z")
        #expect(withdrawn.consentGivenAt == "2026-10-04T08:00:00Z")
        #expect(withdrawn.signedAt == "2026-10-05T08:00:00Z")
        #expect(try page(consent("given", "robot")).consent?.method == "robot")
    }

    @Test func aTranscriptCarriesItsAnswers() throws {
        // GET /calls/{id}/transcript (04 §1): the turns and reports, plus the answers
        let call = try decode(
            IncidentCall.self,
            """
            {"id": "c1", "trigger": "campaign", "attempt": 1, "state": "completed",
             "reports": [], "turns": [],
             "answers": [{"field": "feeling", "value": "unwell", "clear": false,
                          "quote": "Nu prea bine", "at": "2026-11-04T09:00:00Z",
                          "later": true}]}
            """)
        #expect(
            call.answers == [
                CallAnswer(
                    field: "feeling", value: "unwell", clear: false, quote: "Nu prea bine",
                    at: "2026-11-04T09:00:00Z")
            ])
        // An incident's call, or an older server, sends none
        let bare = try decode(
            IncidentCall.self,
            #"{"id": "c2", "trigger": "welcome", "attempt": 1, "state": "completed"}"#)
        #expect(bare.answers.isEmpty)
    }

    @Test func decodesUnknownRoleAndExtraFields() throws {
        let me = try decode(
            Me.self,
            """
            {"display_name": "Ana", "future_key": {"a": 1}, "warning_active": true,
             "grants": [{"role": "inspector", "senior_id": null}, {"role": "das"}]}
            """)
        #expect(me.grants.map(\.role) == ["inspector", "das"])
        #expect(me.warningActive)
    }

    @Test func aSeniorFormSendsEveryFieldAndANilAsNull() throws {
        let form = SeniorForm(
            fullName: "Maria Popescu", formOfAddress: "doamna Maria", phone: "+40256123456",
            callWindow: nil, street: "Str. Daliei", streetNumber: nil, block: nil, staircase: nil,
            floor: nil, apartment: nil, intercomCode: nil, keyHolder: nil, landmark: nil)
        let json = try JSONSerialization.jsonObject(
            with: ApiClient.makeEncoder().encode(form)) as? [String: Any]
        #expect(json?.count == 13)
        #expect(json?["full_name"] as? String == "Maria Popescu")
        #expect(json?["street"] as? String == "Str. Daliei")
        #expect(json?["call_window"] is NSNull)
        #expect(json?["intercom_code"] is NSNull)
    }

    @Test func aMockAnswerSendsNoDefaults() throws {
        let encoder = ApiClient.makeEncoder()
        let welcome = try JSONSerialization.jsonObject(
            with: encoder.encode(MockAnswer(consent: true))) as? [String: Any]
        #expect(welcome?.keys.sorted() == ["consent"])
        let declined = try JSONSerialization.jsonObject(
            with: encoder.encode(MockAnswer(declined: true))) as? [String: Any]
        #expect(declined?.keys.sorted() == ["declined"])
    }

    @Test func formsEncodeSnakeCaseKeys() throws {
        let encoder = ApiClient.makeEncoder()
        let event = EventForm(
            id: "e1", type: "fall", measuredAt: "2026-11-14T10:00:00+02:00", source: "watch",
            snapshot: EventSnapshotForm(restingBaseline: 60, minutesWithoutSteps: 3),
            latitude: 45.7, longitude: 21.2, locationAccuracyM: 12)
        let json = try JSONSerialization.jsonObject(with: encoder.encode(event)) as? [String: Any]
        #expect(json?["measured_at"] as? String == "2026-11-14T10:00:00+02:00")
        #expect(json?["location_accuracy_m"] as? Double == 12)
        let snapshot = json?["snapshot"] as? [String: Any]
        #expect(snapshot?["resting_baseline"] as? Int == 60)
        #expect(snapshot?["minutes_without_steps"] as? Int == 3)
    }
}

}

private struct FakeTokens: TokenSource {
    final class Calls: Sendable {
        private let list = OSLockedArray()
        func append(_ value: Bool) { list.append(value) }
        var values: [Bool] { list.values }
    }
    let calls = Calls()

    func token(forceRefresh: Bool) async throws -> String {
        calls.append(forceRefresh)
        return forceRefresh ? "fresh" : "stale"
    }
}

private final class OSLockedArray: Sendable {
    private let lock = NSLock()
    nonisolated(unsafe) private var storage: [Bool] = []
    func append(_ value: Bool) { lock.lock(); storage.append(value); lock.unlock() }
    var values: [Bool] { lock.lock(); defer { lock.unlock() }; return storage }
}

extension ApiTests {
@Suite struct Client {
    private let base = URL(string: "https://example.test")!

    private func client(_ stub: StubURLProtocol.Stub, _ tokens: FakeTokens = FakeTokens())
        -> ApiClient
    {
        ApiClient(baseURL: base, tokens: tokens, session: stub.session())
    }

    private let meJSON = #"{"display_name": "Ana", "grants": [{"role": "medic"}]}"#
    private let rowJSON = """
        {"id": "s1", "full_name": "M", "form_of_address": "d", "phone_e164": "+40",
         "phone_is_landline": false, "enrollment_state": "draft"}
        """

    @Test func pathsAreUnderApi() async throws {
        let stub = StubURLProtocol.replying(.init(200, "[]"))
        let tokens = FakeTokens()
        _ = try await client(stub, tokens).seniors(role: "medic")
        let sent = try #require(stub.requests.first)
        #expect(sent.method == "GET")
        #expect(sent.url.absoluteString == "https://example.test/api/seniors?role=medic")
        #expect(sent.headers["Authorization"] == "Bearer stale")
        #expect(tokens.calls.values == [false])
    }

    @Test func meReadsTheProfile() async throws {
        let stub = StubURLProtocol.replying(.init(200, meJSON))
        let me = try await client(stub).me()
        #expect(me.displayName == "Ana")
        #expect(stub.requests.first?.url.path == "/api/profile")
    }

    @Test func retriesOnceOn401WithFreshToken() async throws {
        let stub = StubURLProtocol.replying(.init(401, #"{"detail":"expired"}"#), .init(200, meJSON))
        let tokens = FakeTokens()
        let me = try await client(stub, tokens).me()
        #expect(me.displayName == "Ana")
        #expect(tokens.calls.values == [false, true])
        #expect(stub.requests.map { $0.headers["Authorization"] } == ["Bearer stale", "Bearer fresh"])
    }

    @Test func secondUnauthorizedReachesCaller() async throws {
        let stub = StubURLProtocol.replying(.init(401, "nope"), .init(401, "still nope"))
        let tokens = FakeTokens()
        do {
            _ = try await client(stub, tokens).me()
            Issue.record("expected a throw")
        } catch let ApiError.http(status, body) {
            #expect(status == 401)
            #expect(body == "still nope")
        }
        #expect(stub.requests.count == 2)
        #expect(tokens.calls.values == [false, true])
    }

    @Test func aServerErrorCarriesStatusAndBody() async throws {
        let stub = StubURLProtocol.replying(.init(409, #"{"detail":"wrong_state"}"#))
        do {
            _ = try await client(stub).submit(id: "s1")
            Issue.record("expected a throw")
        } catch let ApiError.http(status, body) {
            #expect(status == 409)
            #expect(body.contains("wrong_state"))
        }
        #expect(stub.requests.count == 1)
    }

    @Test func aBadBodyIsADecodingError() async throws {
        let stub = StubURLProtocol.replying(.init(200, #"{"nope": 1}"#))
        do {
            _ = try await client(stub).me()
            Issue.record("expected a throw")
        } catch ApiError.decoding {
        }
    }

    @Test func noContentAnswersNilAnd404OnRecordsToo() async throws {
        let none = StubURLProtocol.replying(.init(204))
        #expect(try await client(none).medicalRecord(id: "s1") == nil)
        #expect(try await client(none).mockCall() == nil)
        let missing = StubURLProtocol.replying(.init(404, #"{"detail":"not_found"}"#))
        #expect(try await client(missing).mockCall() == nil)
        let record = StubURLProtocol.replying(
            .init(200, #"{"state": "pending", "uploaded_at": "2026-11-14T10:00:00Z"}"#))
        #expect(try await client(record).medicalRecord(id: "s1")?.state == "pending")
    }

    @Test func voidCallsAcceptNoContent() async throws {
        let stub = StubURLProtocol.replying(.init(204))
        let api = client(stub)
        try await api.removeCaregiver(id: "s1", userId: "u1")
        try await api.checkIn(CheckInForm(measuredAt: "2026-11-14T10:00:00+02:00", worn: true))
        try await api.mockAnswer(id: "c1", body: MockAnswer(consent: true))
        try await api.sign(
            id: "s1", body: SignatureForm(textVersion: "v1", strokes: [[[0.5, 1], [2, 3]]]))
        let sent = stub.requests
        #expect(sent.map(\.method) == ["DELETE", "POST", "POST", "POST"])
        #expect(
            sent.map(\.url.path) == [
                "/api/seniors/s1/caregivers/u1", "/api/me/check-ins", "/api/calls/c1/mock-answer",
                "/api/seniors/s1/signature",
            ])
        #expect(sent[1].headers["Content-Type"] == "application/json")
        let body = try JSONSerialization.jsonObject(with: sent[1].body) as? [String: Any]
        #expect(body?["measured_at"] as? String == "2026-11-14T10:00:00+02:00")
        #expect(body?["worn"] as? Bool == true)
        #expect(body?["battery"] == nil)
    }

    @Test func aMockAnswerConflictThrows() async throws {
        let stub = StubURLProtocol.replying(.init(409, "not due"))
        do {
            try await client(stub).mockAnswer(id: "c1", body: MockAnswer(declined: true))
            Issue.record("expected a throw")
        } catch let ApiError.http(status, _) {
            #expect(status == 409)
        }
    }

    @Test func uploadSendsThePdfAsApplicationPdf() async throws {
        let stub = StubURLProtocol.replying(
            .init(200, #"{"state": "pending", "uploaded_at": "2026-11-14T10:00:00Z"}"#))
        let pdf = Data("%PDF-1.4 test".utf8)
        let record = try await client(stub).uploadMedicalRecord(id: "s1", pdf: pdf)
        #expect(record.state == "pending")
        let sent = try #require(stub.requests.first)
        #expect(sent.method == "PUT")
        #expect(sent.url.path == "/api/seniors/s1/medical-record")
        #expect(sent.headers["Content-Type"] == "application/pdf")
        #expect(sent.body == pdf)
    }

    @Test func everyEndpointUsesItsMethodAndPath() async throws {
        let stub = StubURLProtocol.replying(.init(200, "{}"))
        let api = client(stub)
        // The bodies are not read here, so failures to decode are expected and ignored.
        _ = try? await api.senior(id: "s1")
        _ = try? await api.calls(id: "s1")
        _ = try? await api.createSenior(Self.form)
        _ = try? await api.updateSenior(id: "s1", body: Self.form)
        _ = try? await api.addCaregiver(
            id: "s1", body: CaregiverForm(displayName: "I", relation: "fiică", phone: "+40"))
        _ = try? await api.submit(id: "s1")
        _ = try? await api.callAgain(id: "s1")
        _ = try? await api.withdraw(id: "s1")
        _ = try? await api.confirmMedicalRecord(
            id: "s1", body: MedicalConfirmForm(items: [], analyzedAt: nil))
        _ = try? await api.reanalyzeMedicalRecord(id: "s1")
        _ = try? await api.sendEvent(EventForm(id: "e", type: "fall", measuredAt: "t"))
        _ = try? await api.incidents(status: "open,in_progress")
        _ = try? await api.incident(id: "i1")
        _ = try? await api.transcript(id: "c1")
        _ = try? await api.take(id: "i1")
        _ = try? await api.resolve(id: "i1", body: Resolution(outcome: "ok", note: "n"))
        let seen = stub.requests.map { "\($0.method) \($0.url.path)" }
        #expect(
            seen == [
                "GET /api/seniors/s1", "GET /api/seniors/s1/calls", "POST /api/seniors",
                "PUT /api/seniors/s1", "POST /api/seniors/s1/caregivers",
                "POST /api/seniors/s1/submit", "POST /api/seniors/s1/welcome-call",
                "POST /api/seniors/s1/consent-withdrawn",
                "POST /api/seniors/s1/medical-record/confirm",
                "POST /api/seniors/s1/medical-record/reanalyze", "POST /api/me/events",
                "GET /api/incidents", "GET /api/incidents/i1", "GET /api/calls/c1/transcript",
                "POST /api/incidents/i1/take", "POST /api/incidents/i1/resolve",
            ])
        #expect(stub.requests[11].url.query == "status=open,in_progress")
    }

    private static let form = SeniorForm(
        fullName: "M", formOfAddress: "d", phone: "+40", callWindow: nil, street: nil,
        streetNumber: nil, block: nil, staircase: nil, floor: nil, apartment: nil,
        intercomCode: nil, keyHolder: nil, landmark: nil)
}
}
