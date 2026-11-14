import Foundation
import Testing

@testable import EchoCare

// seniors §9.3: one reader for both refusal bodies, and what the form does with each. Ported from
// android's RefusalTest.kt.
struct RefusalTests {
    // FastAPI's own 422, as the backend sends it for a number that does not parse.
    private let badPhone = """
        {"detail": [{"type": "value_error", "loc": ["body", "phone"],
                     "msg": "Value error, not a valid phone number", "input": "0700",
                     "ctx": {"error": {}}}]}
        """

    @Test func `FastAPI's list names the fields`() {
        #expect(refusalOf(status: 422, body: badPhone) == .invalid(["phone"]))
        #expect(
            refusalOf(
                status: 422,
                body: """
                    {"detail": [{"loc": ["body", "display_name"]}, {"loc": ["body", "relation"]},
                                {"loc": ["body", "relation"]}]}
                    """) == .invalid(["display_name", "relation"]))
        // The body as a whole, or a path parameter: no field of the form to mark
        #expect(
            refusalOf(
                status: 422, body: #"{"detail": [{"loc": ["body"]}, {"loc": ["path", "senior_id"]}]}"#)
                == .invalid([]))
        #expect(refusalOf(status: 422, body: "not json") == .invalid([]))
    }

    @Test func `our body gives the reason`() {
        #expect(
            refusalOf(
                status: 422,
                body: """
                    {"detail": {"reason": "incomplete",
                                "missing": ["street", "street_number", "caregiver"]}}
                    """) == .incomplete(["street", "street_number", "caregiver"]))
        #expect(
            refusalOf(status: 422, body: #"{"detail": {"reason": "incomplete"}}"#) == .incomplete([]))
        #expect(
            refusalOf(status: 409, body: #"{"detail": {"reason": "already_done"}}"#) == .alreadyDone())
        #expect(
            refusalOf(status: 409, body: #"{"detail": {"reason": "wrong_state"}}"#) == .wrongState)
        // A reason a later server adds: the senior is read again, never a crash (ADR-001 §2.3)
        #expect(refusalOf(status: 409, body: #"{"detail": {"reason": "paused"}}"#) == .wrongState)
    }

    @Test func `everything else is as for a read in slice 3`() {
        #expect(
            refusalOf(status: 404, body: #"{"detail": {"reason": "not_found"}}"#) == .failed(.notFound))
        #expect(
            refusalOf(status: 403, body: #"{"detail": {"reason": "not_allowed"}}"#)
                == .failed(.notAllowed))
        #expect(
            refusalOf(status: 403, body: #"{"detail": {"reason": "not_registered"}}"#)
                == .failed(.notRegistered))
        #expect(
            refusalOf(status: 401, body: #"{"detail": {"reason": "not_signed_in"}}"#)
                == .failed(.signedOut))
        #expect(refusalOf(status: 502, body: "<html>502</html>") == .failed(.noConnection))
        #expect(refusalOf(status: nil, body: nil) == .failed(.noConnection))
    }

    @Test func `a refused save marks the fields or says why`() {
        #expect(
            thenAfter(.save, .invalid(["phone"])) == .mark([.phone: "invalid_phone"]))
        #expect(
            thenAfter(.save, .invalid(["full_name", "unknown"])) == .mark([.fullName: "field_invalid"]))
        #expect(thenAfter(.save, .invalid([])) == .show(.says("field_invalid")))
        // A submitted senior keeps the street and number (04 §2)
        #expect(
            thenAfter(.save, .incomplete(["street"])) == .show(.missing(["street"])))
        #expect(thenAfter(.save, .wrongState) == .reread)
    }

    @Test func `phone taken marks the phone`() {
        let body = #"{"detail": {"reason": "phone_taken"}}"#
        #expect(refusalOf(status: 409, body: body) == .phoneTaken)
        #expect(thenAfter(.save, .phoneTaken) == .mark([.phone: "phone_taken"]))
    }

    @Test func `a refused caregiver says why`() {
        #expect(
            thenAfter(.add, .invalid(["phone"])) == .mark([.caregiverPhone: "caregiver_phone_invalid"]))
        #expect(
            thenAfter(.add, .invalid(["display_name", "relation"]))
                == .mark([.caregiverName: "field_invalid", .relation: "field_invalid"]))
        #expect(thenAfter(.add, .alreadyDone()) == .show(.says("already_caregiver")))
        // Past draft the last caregiver stays (04 §2)
        #expect(
            thenAfter(.remove, .incomplete(["caregiver"])) == .show(.says("last_caregiver")))
    }

    @Test func `a refused submit names what is missing or rereads`() {
        #expect(
            thenAfter(.submit, .incomplete(["street_number", "caregiver"]))
                == .show(.missing(["street_number", "caregiver"])))
        // Already submitted, or past it: step 4 shows the state the senior is in
        #expect(thenAfter(.submit, .wrongState) == .reread)
        #expect(thenAfter(.submit, .alreadyDone()) == .reread)
    }

    @Test func `no connection keeps the form and the rest stop it`() {
        for action in Action.allCases {
            #expect(thenAfter(action, .failed(.noConnection)) == .show(.says("no_connection")))
            for failure in Failure.allCases where failure != .noConnection {
                #expect(thenAfter(action, .failed(failure)) == .stop(failure))
            }
        }
    }

    @Test @MainActor func `a command becomes what its answer means`() async {
        #expect(await send { "s1" } == .ok("s1"))
        #expect(
            await send { throw ApiError.http(status: 422, body: badPhone) } as Sent<String>
                == .no(.invalid(["phone"])))
        #expect(
            await send { throw URLError(.timedOut) } as Sent<String> == .no(.failed(.noConnection)))
        #expect(
            await send { throw TokenError.signedOut } as Sent<String> == .no(.failed(.signedOut)))
        // A 2xx that is not the expected type
        #expect(
            await send { throw ApiError.decoding(URLError(.cannotParseResponse)) } as Sent<String>
                == .no(.failed(.noConnection)))
    }

    @Test @MainActor func `a removal checks its status`() async {
        struct NoToken: TokenSource {
            func token(forceRefresh: Bool) async throws -> String { "t" }
        }
        let body = #"{"detail": {"reason": "incomplete", "missing": ["caregiver"]}}"#
        let stub = StubURLProtocol.replying(.init(422, body))
        let api = ApiClient(
            baseURL: URL(string: "https://api.test")!, tokens: NoToken(), session: stub.session())
        let refused = await send { try await api.removeCaregiver(id: "s1", userId: "u1") }
        guard case .no(let refusal) = refused else {
            Issue.record("a 422 was not refused")
            return
        }
        #expect(refusal == .incomplete(["caregiver"]))
    }

    // UC-11: "Preiau" refused because someone else took it names them (04 §2)
    @Test func `already done carries who took it`() {
        #expect(
            refusalOf(
                status: 409,
                body: #"{"detail":{"reason":"already_done","taken_by_name":"Cristian Pavel"}}"#)
                == .alreadyDone(takenByName: "Cristian Pavel"))
        #expect(
            refusalOf(status: 409, body: #"{"detail":{"reason":"already_done"}}"#)
                == .alreadyDone(takenByName: nil))
    }
}
