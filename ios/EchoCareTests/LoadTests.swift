import Foundation
import Testing

@testable import EchoCare

// seniors §8.2: what a list or a page shows for each answer. Ported from Android's home/LoadTest.kt.
struct LoadTests {
    private let list = ["doamna Maria"]
    private let lost = Answer<[String]>.no(.noConnection)

    @Test func statusesBecomeFailures() {
        #expect(failureOf(status: 401, reason: "not_signed_in") == .signedOut)
        #expect(failureOf(status: 403, reason: "not_registered") == .notRegistered)
        #expect(failureOf(status: 403, reason: "not_allowed") == .notAllowed)
        // A 403 with no readable reason is not a reason to sign the person out.
        #expect(failureOf(status: 403, reason: nil) == .notAllowed)
        #expect(failureOf(status: 404, reason: "not_found") == .notFound)
        #expect(failureOf(status: 503, reason: "auth_unavailable") == .noConnection)
        #expect(failureOf(status: 500, reason: nil) == .noConnection)
        #expect(failureOf(status: nil, reason: nil) == .noConnection)
    }

    @Test func onlySignedOutAndNotRegisteredEndTheSession() {
        #expect(Failure.allCases.filter(\.endsSession) == [.signedOut, .notRegistered])
    }

    @Test func reasonIsReadFromARefusalBody() {
        #expect(reasonOf(#"{"detail": {"reason": "not_registered"}}"#) == "not_registered")
        #expect(
            reasonOf(#"{"detail": {"reason": "already_done", "taken_by_name": "Ana"}}"#)
                == "already_done")
    }

    @Test func anyOtherBodyHasNoReason() {
        // FastAPI's own 422: a list under "detail".
        #expect(reasonOf(#"{"detail": [{"loc": ["body", "phone"], "msg": "bad"}]}"#) == nil)
        #expect(reasonOf(#"{"detail": "Not Found"}"#) == nil)
        #expect(reasonOf("<html>502 Bad Gateway</html>") == nil)
        #expect(reasonOf("") == nil)
        #expect(reasonOf("{}") == nil)
        #expect(reasonOf(nil) == nil)
    }

    @Test func anAnswerReplacesWhateverWasShown() {
        #expect(Load<[String]>.loading.after(.ok(list)) == .ready(list))
        #expect(Load.ready(["old"], offline: true).after(.ok(list)) == .ready(list))
        #expect(Load<[String]>.failed(.noConnection).after(.ok(list)) == .ready(list))
    }

    @Test func withNothingOnScreenALostConnectionIsShown() {
        #expect(Load<[String]>.loading.after(lost) == .failed(.noConnection))
        #expect(Load<[String]>.failed(.noConnection).after(lost) == .failed(.noConnection))
    }

    @Test func withDataOnScreenALostConnectionKeepsItUnderTheBanner() {
        let shown = Load.ready(list)
        #expect(shown.after(lost) == .ready(list, offline: true))
        // And it stays there on the next failed re-read.
        #expect(shown.after(lost).after(lost) == .ready(list, offline: true))
    }

    @Test func aRefusalReplacesTheDataEvenWhenSomeIsShown() {
        let shown = Load.ready(list)
        for failure in Failure.allCases where failure != .noConnection {
            #expect(shown.after(.no(failure)) == .failed(failure))
            #expect(Load<[String]>.loading.after(.no(failure)) == .failed(failure))
        }
    }

    @Test func aCallBecomesAnAnswer() async {
        let list = list
        #expect(await answer { list } == .ok(list))
        #expect(
            await answer { () throws -> [String] in
                throw ApiError.http(status: 403, body: #"{"detail": {"reason": "not_registered"}}"#)
            } == .no(.notRegistered))
        #expect(
            await answer { () throws -> [String] in throw ApiError.http(status: 404, body: "{}") }
                == .no(.notFound))
        #expect(
            await answer { () throws -> [String] in throw URLError(.timedOut) }
                == .no(.noConnection))
        // A body this build cannot read is treated as no answer, never as a crash.
        let unreadable = DecodingError.dataCorrupted(
            .init(codingPath: [], debugDescription: "unexpected JSON"))
        #expect(
            await answer { () throws -> [String] in throw ApiError.decoding(unreadable) }
                == .no(.noConnection))
    }

    @Test func offlineIsOffByDefault() {
        #expect(Load.ready(list) == .ready(list, offline: false))
        #expect(Load.ready(list).after(lost) == .ready(list, offline: true))
    }
}
