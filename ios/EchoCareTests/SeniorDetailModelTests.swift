import Foundation
import os
import Testing

@testable import EchoCare

// One senior's page for the caregiver and the medic (UC-12), ported from the id half of Android's
// SeniorViewModel.kt: the medical record keeps the last one on a failed read and clears on a 204
// (design §5.7), and the medic's commands reread the page.
private let pageJSON = """
    {"id": "s1", "full_name": "Maria Pop", "form_of_address": "doamna Maria", "phone_e164": "+40700000101",
     "phone_is_landline": false, "enrollment_state": "unreachable", "medic": {"display_name": "Dr. Pop"}}
    """
private let recordJSON = #"{"state": "review", "uploaded_at": "2026-11-13T10:00:00Z", "items": []}"#

@MainActor
struct SeniorDetailModelTests {
    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    /// A stub API answering by path; `medical` gives the record read's answer for each read in turn.
    private func model(
        medical: [StubURLProtocol.Reply], command: StubURLProtocol.Reply = .init(200, pageJSON)
    ) -> (SeniorDetailModel, StubURLProtocol.Stub) {
        let reads = OSAllocatedUnfairLock(initialState: 0)
        let stub = StubURLProtocol.Stub { sent in
            let path = sent.url.path
            if path.hasSuffix("/medical-record") {
                let n = reads.withLock { n -> Int in
                    defer { n += 1 }
                    return min(n, medical.count - 1)
                }
                return medical[n]
            }
            if path.hasSuffix("/calls") { return .init(200, "[]") }
            if path.hasSuffix("/welcome-call") || path.hasSuffix("/consent-withdrawn") {
                return command
            }
            if path.hasSuffix("/seniors") { return .init(200, "[]") }
            return .init(200, pageJSON)
        }
        let api = ApiClient(
            baseURL: URL(string: "https://api.test")!, tokens: NoToken(), session: stub.session())
        return (SeniorDetailModel(api: api), stub)
    }

    @Test func aRecordIsReadWithTheMedicsPage() async {
        let (model, _) = model(medical: [.init(200, recordJSON)])
        await model.load(id: "s1", medical: true)
        #expect(model.medical?.state == "review")
        #expect(
            model.page
                == Load.ready(
                    try! ApiClient.makeDecoder().decode(SeniorPage.self, from: Data(pageJSON.utf8)))
        )
    }

    @Test func aNotFoundOrAFailedReadKeepsTheLastRecord() async {
        let (model, _) = model(medical: [.init(200, recordJSON), .init(404, "{}"), .init(500, "")])
        await model.load(id: "s1", medical: true)
        await model.load(id: "s1", medical: true)
        #expect(model.medical?.state == "review")
        await model.load(id: "s1", medical: true)
        #expect(model.medical?.state == "review")
    }

    @Test func aNoContentClearsTheRecord() async {
        let (model, _) = model(medical: [.init(200, recordJSON), .init(204)])
        await model.load(id: "s1", medical: true)
        await model.load(id: "s1", medical: true)
        #expect(model.medical == nil)
    }

    @Test func theCaregiverReadsNoRecord() async {
        let (model, stub) = model(medical: [.init(200, recordJSON)])
        await model.load(id: "s1", medical: false)
        #expect(model.medical == nil)
        #expect(!stub.requests.contains { $0.url.path.hasSuffix("/medical-record") })
    }

    @Test func aRefusedCommandShowsItsNoticeAndRereads() async {
        let (model, stub) = model(
            medical: [.init(204)], command: .init(409, #"{"detail": {"reason": "wrong_state"}}"#))
        await model.load(id: "s1", medical: true)
        let before = stub.requests.count
        await model.callAgain(id: "s1")
        #expect(model.notice == CommandOutcome.refused("wrong_state"))
        #expect(!model.busy)
        // The command, then the page, the calls and the record again
        #expect(stub.requests.count > before + 1)
    }

    @Test func aCommandThatWentThroughLeavesNoNotice() async {
        let (model, _) = model(medical: [.init(204)])
        await model.load(id: "s1", medical: true)
        await model.withdraw(id: "s1")
        #expect(model.notice == nil)
    }

    @Test func aPdfOverTheLimitIsNotSent() async {
        let (model, stub) = model(medical: [.init(204)])
        await model.uploadPdf(id: "s1", pdf: Data(count: MAX_PDF_BYTES + 1))
        #expect(model.uploadNotice == "medical_too_large")
        #expect(!stub.requests.contains { $0.method == "PUT" })
    }
}
