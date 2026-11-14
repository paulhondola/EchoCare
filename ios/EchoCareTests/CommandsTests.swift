import Foundation
import Testing

@testable import EchoCare

// UC-12, 04 §2: what the medic's „Sună din nou” and withdrawal answered. Ported from android's
// CommandsTest.kt.
struct CommandsTests {
    private func page(state: String, phone: String) -> SeniorPage {
        SeniorPage(
            id: "s", fullName: "S", formOfAddress: "Dna", phone: phone, landline: false,
            state: state, medic: Medic(displayName: "M"))
    }

    @Test func `200 is done`() {
        #expect(commandOutcome(status: 200, body: nil) == .done)
    }

    @Test func `409 wrong_state is refused with its reason`() {
        #expect(
            commandOutcome(status: 409, body: #"{"detail":{"reason":"wrong_state"}}"#)
                == .refused("wrong_state"))
    }

    @Test func `409 already_done is refused with its reason`() {
        #expect(
            commandOutcome(status: 409, body: #"{"detail":{"reason":"already_done"}}"#)
                == .refused("already_done"))
    }

    @Test func `403 is refused without a reason, 404 and 422 with their own`() {
        #expect(commandOutcome(status: 403, body: nil) == .refused(nil))
        #expect(
            commandOutcome(status: 404, body: #"{"detail":{"reason":"not_found"}}"#)
                == .refused("not_found"))
        #expect(
            commandOutcome(status: 422, body: #"{"detail":[{"loc":["body","text_version"]}]}"#)
                == .refused("invalid"))
    }

    @Test func `no answer is offline`() {
        #expect(commandOutcome(status: nil, body: nil) == .offline)
    }

    @Test func `a 5xx is offline, as for a read`() {
        #expect(commandOutcome(status: 503, body: "<html>Bad gateway</html>") == .offline)
    }

    @Test func `a read that went through clears an offline notice, not a refusal`() {
        #expect(noticeAfterRead(.offline) == nil)
        #expect(noticeAfterRead(.refused("wrong_state")) == .refused("wrong_state"))
        #expect(noticeAfterRead(nil) == nil)
    }

    @Test func `a new number on a senior to resolve is a changed number`() {
        #expect(isNewNumberToCall(before: "+40700000001", now: page(state: "wrong_number", phone: "+40700000002")))
        #expect(isNewNumberToCall(before: "+40700000001", now: page(state: "unreachable", phone: "+40700000002")))
    }

    @Test func `the same number, or a senior not to resolve, is not`() {
        #expect(!isNewNumberToCall(before: "+40700000001", now: page(state: "unreachable", phone: "+40700000001")))
        #expect(!isNewNumberToCall(before: "+40700000001", now: page(state: "active", phone: "+40700000002")))
    }

    // Android's `command(call)`: what the API client threw becomes the status and body read above

    @Test func `a call that returns is done`() async {
        #expect(await command {} == .done)
    }

    @Test func `a refusal the client threw is read from its status and body`() async {
        let wrong = await command { throw ApiError.http(status: 409, body: #"{"detail": {"reason": "wrong_state"}}"#) }
        #expect(wrong == .refused("wrong_state"))
        #expect(await command { throw ApiError.http(status: 404, body: "{}") } == .refused("not_found"))
        #expect(await command { throw ApiError.http(status: 503, body: "") } == .offline)
    }

    @Test func `no answer or an unreadable one is offline`() async {
        #expect(await command { throw URLError(.notConnectedToInternet) } == .offline)
        let unreadable = DecodingError.dataCorrupted(.init(codingPath: [], debugDescription: "x"))
        #expect(await command { throw ApiError.decoding(unreadable) } == .offline)
    }

    @Test func `no token is the 401 the API would answer`() async {
        #expect(await command { throw TokenError.signedOut } == .refused(nil))
    }
}
