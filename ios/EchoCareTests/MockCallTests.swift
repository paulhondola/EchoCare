import Foundation
import Testing

@testable import EchoCare

// design §6.2: the mock call card's answer is what the server's MockAnswerForm reads (§4.2). Ported
// from android's MockCallTest.kt, with the adapters that turn ApiClient's results into the
// statuses Android's pure functions read.
struct MockCallTests {
    private let encoder = ApiClient.makeEncoder()
    private let decoder = ApiClient.makeDecoder()

    private func sent(_ answer: MockAnswer) throws -> [String: Any] {
        try JSONSerialization.jsonObject(with: encoder.encode(answer)) as? [String: Any] ?? [:]
    }

    @Test func anAnswerNeedsAllThree() {
        #expect(campaignAnswer(feeling: "ok", day: nil, shelter: "yes") == nil)
        #expect(
            campaignAnswer(feeling: "ok", day: "marți", shelter: "yes")
                == MockAnswer(feeling: "ok", day: "marți", shelter: "yes"))
    }

    @Test func answersAreSentAsTheServerReadsThem() throws {
        #expect(try sent(MockAnswer(declined: true)) as NSDictionary == ["declined": true])
        #expect(try sent(MockAnswer(consent: false)) as NSDictionary == ["consent": false])
        let campaign = try #require(campaignAnswer(feeling: "unwell", day: "sâmbătă", shelter: "no"))
        #expect(
            try sent(campaign) as NSDictionary
                == ["feeling": "unwell", "day": "sâmbătă", "shelter": "no"])
    }

    @Test func aWelcomeCallIsDecoded() throws {
        let call = try decoder.decode(
            MockCall.self,
            from: Data(
                """
                {"call_id": "c1", "trigger": "welcome", "consent_text": "Sunteți de acord?",
                 "text_version": "v1-app"}
                """.utf8))
        #expect(call == MockCall(callId: "c1", trigger: "welcome", consentText: "Sunteți de acord?"))
    }

    @Test func aDefiniteReadSetsTheCardAndALostOneKeepsIt() {
        let shown = MockCall(callId: "c1", trigger: "campaign")
        let next = MockCall(callId: "c2", trigger: "welcome")
        #expect(cardAfterRead(status: 200, body: next, previous: shown) == next)
        // 204 (nothing due), 403 and 404 (production) are the server's answer: no card
        for status in [204, 403, 404] {
            #expect(cardAfterRead(status: status, body: nil, previous: shown) == nil)
        }
        // A redeploy's 502 or 503, or no connection at all (nil), keeps what the senior is on
        for status in [500, 502, 503, nil] as [Int?] {
            #expect(cardAfterRead(status: status, body: nil, previous: shown) == shown)
        }
    }

    @Test func aPostSettlesTheCardOnlyWhenTheServerAnswered() {
        // 204, and 409 or 422: the call is done or the body was refused, so the page rereads
        for status in [204, 409, 422] { #expect(answerSettled(status: status)) }
        // The answer may not have arrived: the card stays so the senior can press again
        for status in [500, 502, 503, nil] as [Int?] { #expect(!answerSettled(status: status)) }
    }

    @Test func theDaysAreTheServers() {
        #expect(DAYS.count == 7)
        #expect(DAYS[5] == "sâmbătă")
    }

    // MARK: The adapter between ApiClient and the status functions

    @Test func aCardReadIsAStatus() async {
        let card = MockCall(callId: "c1", trigger: "welcome")
        let got = await readMock { card }
        #expect(got.status == 200)
        #expect(got.body == card)
        // ApiClient returns nil for 204 (and 404)
        let none = await readMock { nil }
        #expect(none.status == 204)
        #expect(none.body == nil)
    }

    @Test func aRefusedOrLostReadIsItsStatusOrNone() async {
        for status in [403, 500, 502] {
            let read = await readMock { throw ApiError.http(status: status, body: "") }
            #expect(read.status == status)
            #expect(read.body == nil)
        }
        for error: any Error in [URLError(.notConnectedToInternet), URLError(.timedOut), CancellationError()] {
            let read = await readMock { throw error }
            #expect(read.status == nil)
        }
    }

    @Test func aPostIsAStatusToo() async {
        #expect(await postStatus {} == 204)
        #expect(await postStatus { throw ApiError.http(status: 409, body: "{}") } == 409)
        #expect(await postStatus { throw URLError(.networkConnectionLost) } == nil)
    }

    @Test func theAdaptedStatusesDriveTheCard() async {
        let shown = MockCall(callId: "c1", trigger: "campaign")
        let forbidden = await readMock { throw ApiError.http(status: 403, body: "") }
        #expect(cardAfterRead(status: forbidden.status, body: forbidden.body, previous: shown) == nil)
        let lost = await readMock { throw URLError(.notConnectedToInternet) }
        #expect(cardAfterRead(status: lost.status, body: lost.body, previous: shown) == shown)
        let refused = await postStatus { throw ApiError.http(status: 422, body: "") }
        #expect(answerSettled(status: refused))
        let offline = await postStatus { throw URLError(.notConnectedToInternet) }
        #expect(!answerSettled(status: offline))
    }

    @Test func aLoadFailureIsWhatItMeans() async {
        let signedOut: Answer<Int> = await answer { throw ApiError.http(status: 401, body: "") }
        #expect(signedOut == .no(.signedOut))
        let notRegistered: Answer<Int> = await answer {
            throw ApiError.http(status: 403, body: #"{"detail":{"reason":"not_registered"}}"#)
        }
        #expect(notRegistered == .no(.notRegistered))
        let lost: Answer<Int> = await answer { throw URLError(.notConnectedToInternet) }
        #expect(lost == .no(.noConnection))
        let token: Answer<Int> = await answer { throw TokenError.signedOut }
        #expect(token == .no(.signedOut))
        let fine: Answer<Int> = await answer { 7 }
        #expect(fine == .ok(7))
    }
}
