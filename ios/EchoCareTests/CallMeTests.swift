import Foundation
import Testing

@testable import EchoCare

// UC-10, 04 §3: „Sunați-mă” posts a manual_request and shows what the server answered. Ported from
// android's CallMeTest.kt.
struct CallMeTests {
    // The same coders as ApiClient.
    private let encoder = ApiClient.makeEncoder()
    private let decoder = ApiClient.makeDecoder()

    @Test func theRequestIsSentAsTheServerReadsIt() throws {
        let form = manualRequest(id: "e1", now: Date(timeIntervalSince1970: 1_793_304_000))
        let sent = try JSONSerialization.jsonObject(with: encoder.encode(form)) as? [String: String]
        #expect(
            sent == [
                "id": "e1", "type": "manual_request", "measured_at": "2026-10-29T20:00:00Z",
                "source": "phone",
            ])
    }

    @Test func everyTapHasItsOwnId() {
        #expect(manualRequest().id != manualRequest().id)
    }

    @Test func aCallIsComingOnlyWhenTheServerNamedOne() {
        #expect(callMeAfter(.ok(EventResult(queued: true, callId: "c1"))) == .coming)
        // A tap that joined the call already there
        #expect(callMeAfter(.ok(EventResult(queued: false, callId: "c1"))) == .coming)
        // Recorded, but stale or the senior is not active: no call
        #expect(callMeAfter(.ok(EventResult())) == .notSent)
    }

    @Test func aFailedTapInvitesAnother() {
        for failure in Failure.allCases {
            #expect(callMeAfter(.no(failure)) == .notSent)
        }
    }

    @Test func anAnswerMissingFieldsOrWithNewOnesIsDecoded() throws {
        #expect(try decoder.decode(EventResult.self, from: Data("{}".utf8)) == EventResult())
        #expect(
            try decoder.decode(
                EventResult.self, from: Data(#"{"queued": true, "call_id": "c1", "later": 1}"#.utf8))
                == EventResult(queued: true, callId: "c1"))
    }

    @Test func aFixIsSentWithTheRequest() throws {
        var form = manualRequest(id: "e1", now: Date(timeIntervalSince1970: 0))
        form.latitude = 45.75
        form.longitude = 21.23
        form.locationAccuracyM = 65
        let sent = try JSONSerialization.jsonObject(with: encoder.encode(form)) as? [String: Any]
        #expect(sent?["latitude"] as? Double == 45.75)
        #expect(sent?["location_accuracy_m"] as? Double == 65)
    }
}
