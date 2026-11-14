import CoreLocation
import Foundation
import Shared
import Testing

@testable import EchoCare

// The phone's relay of the watch (04 §3, UC-09, UC-13), ported from android's
// WearListenerServiceTest.kt case for case, plus the relay's ack rules.
@MainActor
struct RelayTests {
    // MARK: WearListenerServiceTest.kt

    @Test func eventWithSnapshotMapsToEventFormWithSourceWatch() {
        let msg = EventMessage(
            id: "6569b60e-fdf8-4dfe-916d-025f5e573186",
            type: "high_pulse_at_rest",
            measuredAt: "2026-11-12T19:00:00Z",
            snapshot: EventSnapshot(
                pulse: 125, restingBaseline: 70, moving: false, minutesWithoutSteps: 0, battery: 55))
        let form = eventForm(msg, location: nil)
        #expect(form.id == "6569b60e-fdf8-4dfe-916d-025f5e573186")
        #expect(form.type == "high_pulse_at_rest")
        #expect(form.measuredAt == "2026-11-12T19:00:00Z")
        #expect(form.source == "watch")
        #expect(form.snapshot?.pulse == 125)
        #expect(form.snapshot?.restingBaseline == 70)
    }

    @Test func eventWithEmptySnapshotMapsToEventFormWithoutSnapshot() {
        let empty = EventMessage(id: "a", type: "manual_request", measuredAt: "t", snapshot: .empty)
        #expect(eventForm(empty, location: nil).source == "watch")
        #expect(eventForm(empty, location: nil).snapshot == nil)
        // Swift's message can also leave it out altogether
        let none = EventMessage(id: "a", type: "manual_request", measuredAt: "t")
        #expect(eventForm(none, location: nil).snapshot == nil)
    }

    @Test func checkInMapsEveryFieldThrough() {
        let msg = CheckInMessage(
            measuredAt: "2026-11-12T19:00:00Z", battery: 42, worn: false, lastPulse: 88,
            restingPulse: 64, stepsToday: 900, minutesWithoutSteps: 3)
        let form = checkInForm(msg)
        #expect(form.measuredAt == "2026-11-12T19:00:00Z")
        #expect(form.battery == 42)
        #expect(form.worn == false)
        #expect(form.lastPulse == 88)
        #expect(form.restingPulse == 64)
        #expect(form.stepsToday == 900)
        #expect(form.minutesWithoutSteps == 3)
    }

    // MARK: The phone's location (lastKnownLocation in WearListenerService.kt)

    @Test func eventCarriesTheLastKnownLocation() {
        let fix = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 45.75, longitude: 21.23), altitude: 0,
            horizontalAccuracy: 35, verticalAccuracy: -1, timestamp: Date())
        let form = eventForm(EventMessage(id: "a", type: "fall", measuredAt: "t"), location: fix)
        #expect(form.latitude == 45.75)
        #expect(form.longitude == 21.23)
        #expect(form.locationAccuracyM == 35)
    }

    @Test func anInvalidFixIsLeftOut() {
        let fix = CLLocation(
            coordinate: CLLocationCoordinate2D(latitude: 45.75, longitude: 21.23), altitude: 0,
            horizontalAccuracy: -1, verticalAccuracy: -1, timestamp: Date())
        let form = eventForm(EventMessage(id: "a", type: "fall", measuredAt: "t"), location: fix)
        #expect(form.latitude == nil)
        #expect(form.longitude == nil)
        #expect(form.locationAccuracyM == nil)
    }

    // MARK: Relay

    private struct NoToken: TokenSource {
        func token(forceRefresh: Bool) async throws -> String { "t" }
    }

    @MainActor final class Acks {
        var ids: [String] = []
    }

    private func relay(_ stub: StubURLProtocol.Stub, acks: Acks, signedIn: Bool = true) -> Relay {
        let api = ApiClient(
            baseURL: URL(string: "https://api.test")!, tokens: NoToken(), session: stub.session())
        return Relay(
            api: api, signedIn: { signedIn }, location: { nil }, ack: { id in acks.ids.append(id) })
    }

    private func eventPayload(id: String = "e1") throws -> [String: Any] {
        var payload = try WatchMessage.encode(EventMessage(id: id, type: "fall", measuredAt: "t"))
        payload["kind"] = WatchMessage.event
        return payload
    }

    /// The production path: WatchLink's delegate splits the dictionary, the relay takes the strings.
    private func deliver(_ payload: [String: Any], to relay: Relay) async throws {
        let (kind, json) = try #require(WatchLink.split(payload))
        await relay.handle(kind: kind, json: json)
    }

    @Test func relayAcksOnlyAfterAccepted() async throws {
        let refused = StubURLProtocol.replying(.init(500))
        let none = Acks()
        try await deliver(try eventPayload(), to: relay(refused, acks: none))
        #expect(refused.requests.count == 1)
        #expect(none.ids.isEmpty)

        let accepted = StubURLProtocol.replying(.init(200, #"{"queued": true, "call_id": "c1"}"#))
        let one = Acks()
        try await deliver(try eventPayload(id: "e7"), to: relay(accepted, acks: one))
        #expect(one.ids == ["e7"])
        let sent = try #require(accepted.requests.first)
        #expect(sent.method == "POST")
        #expect(sent.url.path == "/api/me/events")
        let body = try ApiClient.makeDecoder().decode(EventForm.self, from: sent.body)
        #expect(body.id == "e7")
        #expect(body.source == "watch")
    }

    // 04 §3: the backend answers a seen id with 200 too, so a resent event is acked again
    @Test func aResentEventIsAckedAgain() async throws {
        let stub = StubURLProtocol.replying(.init(200, #"{"queued": false}"#))
        let acks = Acks()
        let relay = relay(stub, acks: acks)
        try await deliver(try eventPayload(id: "e1"), to: relay)
        try await deliver(try eventPayload(id: "e1"), to: relay)
        #expect(acks.ids == ["e1", "e1"])
    }

    // As WearListenerService.kt: any failure, a 4xx included, leaves the event in the watch's queue
    @Test func aRefusedEventIsNotAcked() async throws {
        let stub = StubURLProtocol.replying(.init(422, #"{"detail":"invalid"}"#))
        let acks = Acks()
        try await deliver(try eventPayload(), to: relay(stub, acks: acks))
        #expect(acks.ids.isEmpty)
    }

    @Test func relayIgnoresWhenSignedOut() async throws {
        let stub = StubURLProtocol.replying(.init(200, #"{"queued": true}"#))
        let acks = Acks()
        try await deliver(try eventPayload(), to: relay(stub, acks: acks, signedIn: false))
        #expect(stub.requests.isEmpty)
        #expect(acks.ids.isEmpty)
    }

    @Test func aPayloadThatDoesNotDecodeIsDropped() async throws {
        let stub = StubURLProtocol.replying(.init(200, #"{"queued": true}"#))
        let acks = Acks()
        let relay = relay(stub, acks: acks)
        // No "type": Swift's decoder is strict where Kotlin's defaulted
        await relay.handle(kind: WatchMessage.event, json: #"{"id": "e1", "measured_at": "t"}"#)
        await relay.handle(kind: WatchMessage.event, json: "not json")
        await relay.handle(kind: "something-else", json: "{}")
        #expect(stub.requests.isEmpty)
        #expect(acks.ids.isEmpty)
    }

    @Test func aCheckInIsPostedAndNotAcked() async throws {
        let stub = StubURLProtocol.replying(.init(204))
        let acks = Acks()
        var payload = try WatchMessage.encode(
            CheckInMessage(measuredAt: "2026-11-12T19:00:00Z", battery: 42, worn: true, lastPulse: 70))
        payload["kind"] = WatchMessage.checkIn
        try await deliver(payload, to: relay(stub, acks: acks))
        let sent = try #require(stub.requests.first)
        #expect(sent.url.path == "/api/me/check-ins")
        let body = try ApiClient.makeDecoder().decode(CheckInForm.self, from: sent.body)
        #expect(body.battery == 42)
        #expect(body.worn == true)
        #expect(acks.ids.isEmpty)
    }

    // MARK: WatchLink.split, the copy-out before the hop

    @Test func splitTakesKindAndJson() throws {
        let split = try #require(WatchLink.split(try eventPayload(id: "e1")))
        #expect(split.kind == WatchMessage.event)
        #expect(split.json.contains(#""id":"e1""#))
    }

    @Test func splitNeedsBothStrings() {
        #expect(WatchLink.split(["json": "{}"]) == nil)
        #expect(WatchLink.split(["kind": WatchMessage.event]) == nil)
        #expect(WatchLink.split([:]) == nil)
    }

    @Test func splitRefusesOtherTypes() {
        #expect(WatchLink.split(["kind": 1, "json": "{}"]) == nil)
        #expect(WatchLink.split(["kind": WatchMessage.event, "json": Data("{}".utf8)]) == nil)
        #expect(WatchLink.split(["kind": WatchMessage.event, "json": ["id": "e1"]]) == nil)
    }

    // MARK: The ack the watch reads (PhoneLink.ackedId)

    @Test func theAckIsTheReceivedKindWithTheId() throws {
        let ack = try #require(WatchLink.ackPayload(id: "e1"))
        #expect(ack["kind"] as? String == WatchMessage.received)
        #expect(ack["json"] as? String == #"{"id":"e1"}"#)
    }
}
