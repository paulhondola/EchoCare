import Foundation
import os
import Testing

@testable import EchoCare

// seniors §9.2: the form's four steps against a stubbed API, ported from android's
// EnrollViewModel.kt behaviour (no Kotlin test exists for it).
private func pageJSON(
    state: String = "draft", street: String? = nil, number: String? = nil,
    caregivers: String = "[]",
    signedAt: String? = nil
) -> String {
    func q(_ s: String?) -> String { s.map { "\"\($0)\"" } ?? "null" }
    return """
        {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
         "phone_e164": "+40256123456", "phone_is_landline": true, "enrollment_state": "\(state)",
         "street": \(q(street)), "street_number": \(q(number)), "signed_at": \(q(signedAt)),
         "medic": {"display_name": "Dr. Pop"}, "caregivers": \(caregivers)}
        """
}
private let rowJSON = """
    {"id": "s1", "full_name": "Maria Popescu", "form_of_address": "doamna Maria",
     "phone_e164": "+40256123456", "phone_is_landline": true, "enrollment_state": "submitted"}
    """
private let caregiverJSON = """
    {"user_id": "u1", "display_name": "Ioana Pop", "relation": "fiică", "phone_e164": "+40700000004"}
    """

@MainActor
struct EnrollModelTests {
    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    private func model(
        id: String? = nil,
        _ handler: @escaping @Sendable (StubURLProtocol.Sent) -> StubURLProtocol.Reply
    ) -> (EnrollModel, StubURLProtocol.Stub) {
        let stub = StubURLProtocol.Stub(handler)
        let api = ApiClient(
            baseURL: URL(string: "https://api.test")!, tokens: NoToken(), session: stub.session())
        return (EnrollModel(seniorId: id, api: api), stub)
    }

    private func fill(_ model: EnrollModel) {
        model.type(.fullName, "Maria Popescu")
        model.type(.formOfAddress, "doamna Maria")
        model.type(.phone, "0256 123 456")
    }

    @Test func `a new form is ready at step 1 and a saved one opens read`() async {
        let (new, _) = model { _ in .init(200, pageJSON()) }
        #expect(new.form == .ready(Opened()))
        #expect(new.step == .senior)
        #expect(!new.existing)

        let (saved, _) = model(id: "s1") { _ in
            .init(200, pageJSON(street: "Str. Daliei", number: "12"))
        }
        #expect(saved.form == .loading)
        await saved.open()
        #expect(saved.form == .ready(Opened()))
        #expect(saved.values[.street] == "Str. Daliei")
        #expect(saved.values[.phone] == "0256 123 456")
    }

    @Test func `step 1 posts the first time and puts after that, never a second draft`() async {
        let (model, stub) = model { _ in .init(200, pageJSON()) }
        fill(model)
        await model.next()
        #expect(model.step == .address)
        #expect(model.id == "s1")
        #expect(stub.requests.map(\.method) == ["POST"])
        let sent = try? JSONSerialization.jsonObject(with: stub.requests[0].body) as? [String: Any]
        #expect(sent?["phone"] as? String == "+40256123456")

        await model.next()
        #expect(model.step == .caregivers)
        #expect(stub.requests.map(\.method) == ["POST", "PUT"])
        #expect(stub.requests[1].url.path.hasSuffix("/seniors/s1"))
    }

    @Test func `step 3 sends nothing and step 4 reads the senior`() async {
        let (model, stub) = model { _ in .init(200, pageJSON(street: "S", number: "1")) }
        fill(model)
        await model.next()
        await model.next()
        let before = stub.requests.count
        await model.next()
        #expect(model.step == .review)
        // Only the read of step 4
        #expect(stub.requests.dropFirst(before).map(\.method) == ["GET"])
        #expect(
            model.review
                == .ready(
                    try! ApiClient.makeDecoder().decode(
                        SeniorPage.self, from: Data(pageJSON(street: "S", number: "1").utf8))))
    }

    @Test func `back drops what was typed since the last save and step 1 closes the form`() async {
        let (model, _) = model { _ in .init(200, pageJSON()) }
        fill(model)
        #expect(!model.back())
        await model.next()
        model.type(.street, "Str. Nouă")
        #expect(model.back())
        #expect(model.step == .senior)
        #expect(model.values[.street] == "")
    }

    @Test func `a refused save marks the field and stays on the step`() async {
        let (model, _) = model { _ in .init(409, #"{"detail": {"reason": "phone_taken"}}"#) }
        fill(model)
        await model.next()
        #expect(model.step == .senior)
        #expect(model.errors == [.phone: "phone_taken"])
        // Typing in the field takes its text away
        model.type(.phone, "0256 123 457")
        #expect(model.errors.isEmpty)
        #expect(!model.busy)
    }

    @Test func `no connection keeps what was typed and says so`() async {
        let (model, _) = model { _ in .init(502, "<html>") }
        fill(model)
        await model.next()
        #expect(model.notice == .says("no_connection"))
        #expect(model.values[.fullName] == "Maria Popescu")
        #expect(model.step == .senior)
    }

    @Test func `a caregiver is added and removed at once`() async {
        let (model, stub) = model { sent in
            if sent.method == "POST" && sent.url.path.hasSuffix("/seniors") {
                return .init(200, pageJSON())
            }
            if sent.method == "POST" { return .init(200, caregiverJSON) }
            return .init(204)
        }
        fill(model)
        await model.next()
        await model.next()
        model.type(.caregiverName, "Ioana Pop")
        model.type(.relation, "fiică")
        model.type(.caregiverPhone, "0700 000 004")
        await model.add()
        #expect(model.caregivers.map(\.userId) == ["u1"])
        #expect(model.adding.isEmpty)
        let body =
            try? JSONSerialization.jsonObject(with: stub.requests.last!.body) as? [String: Any]
        #expect(body?["phone"] as? String == "+40700000004")

        await model.remove(model.caregivers[0])
        #expect(model.caregivers.isEmpty)
        #expect(stub.requests.last?.method == "DELETE")
    }

    @Test func `the last caregiver of a submitted senior stays`() async {
        let (model, _) = model(id: "s1") { sent in
            if sent.method == "DELETE" {
                return .init(
                    422, #"{"detail": {"reason": "incomplete", "missing": ["caregiver"]}}"#)
            }
            return .init(200, pageJSON(state: "submitted", caregivers: "[\(caregiverJSON)]"))
        }
        await model.open()
        await model.remove(model.caregivers[0])
        #expect(model.caregivers.count == 1)
        #expect(model.notice == .says("last_caregiver"))
    }

    @Test func `submit sends the senior and the form closes`() async {
        let (model, stub) = model(id: "s1") { sent in
            sent.url.path.hasSuffix("/submit") ? .init(200, rowJSON) : .init(200, pageJSON())
        }
        await model.open()
        #expect(!model.submitted)
        await model.submit()
        #expect(model.submitted)
        #expect(stub.requests.last?.url.path.hasSuffix("/seniors/s1/submit") == true)
    }

    @Test func `a refused submit names what is missing`() async {
        let (model, _) = model(id: "s1") { sent in
            sent.url.path.hasSuffix("/submit")
                ? .init(422, #"{"detail": {"reason": "incomplete", "missing": ["caregiver"]}}"#)
                : .init(200, pageJSON())
        }
        await model.open()
        await model.submit()
        #expect(!model.submitted)
        #expect(model.notice == .missing(["caregiver"]))
    }

    @Test func `an already submitted senior is read again instead`() async {
        let (model, _) = model(id: "s1") { sent in
            sent.url.path.hasSuffix("/submit")
                ? .init(409, #"{"detail": {"reason": "wrong_state"}}"#)
                : .init(200, pageJSON(state: "submitted"))
        }
        await model.open()
        await model.submit()
        #expect(model.step == .review)
        #expect(!model.submitted)
        #expect(model.state == "submitted")
    }

    @Test func `a 404 stops the form`() async {
        let (model, _) = model(id: "s1") { _ in .init(404, #"{"detail": {"reason": "not_found"}}"#)
        }
        await model.open()
        #expect(model.form == .failed(.notFound))
    }

    @Test func `signing posts the strokes and reads the summary again`() async {
        let signed = OSAllocatedUnfairLock(initialState: false)
        let (model, stub) = model(id: "s1") { sent in
            if sent.url.path.hasSuffix("/signature") {
                signed.withLock { $0 = true }
                return .init(204)
            }
            return .init(
                200, pageJSON(signedAt: signed.withLock { $0 } ? "2026-11-14T10:00:00Z" : nil))
        }
        await model.open()
        await model.sign(signatureForm([[Point(x: 0.5, y: 0.5)]], width: 1, height: 1))
        #expect(stub.requests.contains { $0.url.path.hasSuffix("/signature") })
        guard case .ready(let senior, _) = model.review else {
            Issue.record("the summary was not read again")
            return
        }
        #expect(senior.signedAt == "2026-11-14T10:00:00Z")
    }

    @Test func `a refused signature keeps the pad and shows a line`() async {
        let (model, _) = model(id: "s1") { sent in
            sent.url.path.hasSuffix("/signature") ? .init(502, "") : .init(200, pageJSON())
        }
        await model.open()
        await model.sign(signatureForm([[Point(x: 0.5, y: 0.5)]], width: 1, height: 1))
        #expect(model.notice == .says("no_connection"))
    }

    @Test func `a pdf over the limit is not sent`() async {
        let (model, stub) = model(id: "s1") { _ in .init(200, pageJSON()) }
        await model.open()
        await model.uploadPdf(Data(count: MAX_PDF_BYTES + 1))
        #expect(model.medicalNotice == "medical_too_large")
        await model.uploadPdf(nil)
        #expect(model.medicalNotice == "medical_upload_failed")
        #expect(stub.requests.allSatisfy { $0.method == "GET" })
    }

    @Test func `a pdf is sent and a failure never blocks`() async {
        let record = #"{"state": "uploaded", "uploaded_at": "2026-11-14T10:00:00Z"}"#
        let (model, _) = model(id: "s1") { sent in
            sent.method == "PUT" ? .init(200, record) : .init(200, pageJSON())
        }
        await model.open()
        await model.uploadPdf(Data(count: 10))
        #expect(model.medicalSent)
        #expect(model.medicalNotice == nil)

        let (failing, _) = self.model(id: "s1") { sent in
            sent.method == "PUT" ? .init(500, "") : .init(200, pageJSON())
        }
        await failing.open()
        await failing.uploadPdf(Data(count: 10))
        #expect(!failing.medicalSent)
        #expect(failing.medicalNotice == "medical_upload_failed")
    }
}
