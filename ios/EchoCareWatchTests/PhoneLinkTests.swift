import Foundation
import Shared
import Testing

@testable import EchoCareWatch

// 04 §3 over WatchConnectivity: the dictionaries the watch sends, and the phone's `received` ack.
// A payload that doesn't decode acks nothing (Task 2's carried minor).
struct PhoneLinkTests {
    private func received(json: String) -> [String: Any] {
        ["kind": WatchMessage.received, "json": json]
    }

    @Test func aReceivedMessageAcksItsId() {
        #expect(PhoneLink.ackedId(in: received(json: #"{"id":"e1"}"#)) == "e1")
    }

    @Test func anEchoedEventAcksItsId() throws {
        var message = try WatchMessage.encode(EventMessage(id: "e2", type: "fall", measuredAt: "t"))
        message["kind"] = WatchMessage.received
        #expect(PhoneLink.ackedId(in: message) == "e2")
    }

    @Test func aMalformedReceivedAcksNothing() {
        #expect(PhoneLink.ackedId(in: received(json: "{}")) == nil)
        #expect(PhoneLink.ackedId(in: received(json: #"{"id":""}"#)) == nil)
        #expect(PhoneLink.ackedId(in: received(json: "not json")) == nil)
        #expect(PhoneLink.ackedId(in: ["kind": WatchMessage.received]) == nil)
    }

    @Test func otherKindsAckNothing() {
        #expect(PhoneLink.ackedId(in: ["kind": WatchMessage.event, "json": #"{"id":"e1"}"#]) == nil)
        #expect(PhoneLink.ackedId(in: ["json": #"{"id":"e1"}"#]) == nil)
    }

    @Test func anEventGoesAsKindAndSnakeCaseJson() throws {
        let event = EventMessage(
            id: "e3", type: "high_pulse_at_rest", measuredAt: "2026-10-29T20:00:00.000Z",
            snapshot: EventSnapshot(pulse: 125, restingBaseline: 66, moving: false, minutesWithoutSteps: 0, battery: 80))
        let payload = try #require(PhoneLink.payload(WatchMessage.event, event))
        #expect(payload["kind"] as? String == "event")
        #expect((payload["json"] as? String)?.contains("\"resting_baseline\":66") == true)
        #expect(try WatchMessage.decode(EventMessage.self, from: payload) == event)
    }

    @Test func aCheckInGoesAsKindCheckIn() throws {
        let checkIn = CheckInMessage(measuredAt: "t", battery: 80, worn: true, lastPulse: 72)
        let payload = try #require(PhoneLink.payload(WatchMessage.checkIn, checkIn))
        #expect(payload["kind"] as? String == "check-in")
        #expect(try WatchMessage.decode(CheckInMessage.self, from: payload) == checkIn)
    }
}
