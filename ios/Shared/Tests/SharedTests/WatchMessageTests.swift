import Foundation
import Testing
@testable import Shared

struct WatchMessageTests {
    private func json(_ dict: [String: Any]) throws -> String {
        try #require(dict["json"] as? String)
    }

    @Test("check-in round-trips through a message with every field set")
    func checkInRoundTrip() throws {
        let original = CheckInMessage(
            measuredAt: "2026-11-07T19:45:00Z",
            battery: 73,
            worn: true,
            lastPulse: 88,
            restingPulse: 66,
            stepsToday: 2450,
            minutesWithoutSteps: 14
        )
        let decoded = try WatchMessage.decode(
            CheckInMessage.self, from: WatchMessage.encode(original))
        #expect(decoded == original)
    }

    @Test("a check-in from an older watch decodes the added fields as null")
    func decodesOlderCheckIn() throws {
        let old =
            #"{"measured_at":"2026-11-07T19:45:00Z","battery":73,"worn":true,"last_pulse":88}"#
        let decoded = try WatchMessage.decode(CheckInMessage.self, from: ["json": old])
        #expect(
            decoded
                == CheckInMessage(
                    measuredAt: "2026-11-07T19:45:00Z", battery: 73, worn: true, lastPulse: 88))
    }

    @Test("check-in omits null fields and decodes them back as null")
    func checkInNilFields() throws {
        let original = CheckInMessage(
            measuredAt: "2026-11-07T19:45:00Z", battery: nil, worn: false, lastPulse: nil)
        let encoded = try WatchMessage.encode(original)
        let text = try json(encoded)
        #expect(!text.contains("battery"))
        #expect(!text.contains("last_pulse"))
        #expect(try WatchMessage.decode(CheckInMessage.self, from: encoded) == original)
    }

    @Test("event round-trips through a message")
    func eventRoundTrip() throws {
        let original = EventMessage(
            id: "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type: "fall",
            measuredAt: "2026-11-07T19:28:51.814+00:00"
        )
        let decoded = try WatchMessage.decode(
            EventMessage.self, from: WatchMessage.encode(original))
        #expect(decoded == original)
    }

    @Test("event round-trips with a full snapshot")
    func eventFullSnapshot() throws {
        let original = EventMessage(
            id: "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type: "high_pulse_at_rest",
            measuredAt: "2026-11-07T19:28:51.814+00:00",
            snapshot: EventSnapshot(
                pulse: 120, restingBaseline: 72, moving: false,
                minutesWithoutSteps: 0, battery: 55)
        )
        let decoded = try WatchMessage.decode(
            EventMessage.self, from: WatchMessage.encode(original))
        #expect(decoded == original)
    }

    @Test("an event with no snapshot serialises without one")
    func omitsNilFields() throws {
        let msg = EventMessage(id: "a", type: "manual_request", measuredAt: "t", snapshot: nil)
        let text = try json(WatchMessage.encode(msg))
        #expect(!text.contains("snapshot"))
    }

    @Test("encodes snake_case keys")
    func encodesSnakeCaseKeys() throws {
        let msg = CheckInMessage(
            measuredAt: "t", battery: nil, worn: true, lastPulse: nil, minutesWithoutSteps: 3)
        let text = try json(WatchMessage.encode(msg))
        #expect(text.contains("\"measured_at\""))
        #expect(text.contains("\"minutes_without_steps\""))
    }

    @Test("kind constants name the three message kinds")
    func kinds() {
        #expect(WatchMessage.event == "event")
        #expect(WatchMessage.checkIn == "check-in")
        #expect(WatchMessage.received == "received")
    }
}
