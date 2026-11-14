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

// Which way each message goes (design "Watch ↔ phone"): `sendMessage` when the phone is reachable,
// which wakes a suspended iPhone app, else `transferUserInfo`. Check-ins go as events do, as on
// Wear OS, without the queue: only the newest check-in waits.

private struct LinkDown: Error {}

private final class FakeSession: LinkSession {
    var isActive = true
    var isReachable = true
    var messages: [[String: Any]] = []
    var onErrors: [@Sendable (any Error) -> Void] = []
    var waitingTransfers: [[String: Any]] = []
    var cancelled: [[String: Any]] = []

    func send(message: [String: Any], onError: @escaping @Sendable (any Error) -> Void) {
        messages.append(message)
        onErrors.append(onError)
    }

    func transfer(_ userInfo: [String: Any]) { waitingTransfers.append(userInfo) }

    func cancelWaiting(where match: ([String: Any]) -> Bool) {
        cancelled += waitingTransfers.filter(match)
        waitingTransfers.removeAll(where: match)
    }

    func kinds(_ dictionaries: [[String: Any]]) -> [String?] { dictionaries.map { $0["kind"] as? String } }
}

@MainActor
struct PhoneLinkRoutingTests {
    private let session = FakeSession()
    private let queue = EventQueue(
        directory: FileManager.default.temporaryDirectory
            .appending(path: "echocare-link-\(UUID().uuidString)", directoryHint: .isDirectory))
    private let link: PhoneLink

    init() {
        link = PhoneLink(queue: queue, session: session)
    }

    private func checkIn(_ at: String) -> CheckInMessage {
        CheckInMessage(measuredAt: at, battery: 80, worn: true, lastPulse: 72)
    }

    private func measuredAt(_ dictionary: [String: Any]) -> String? {
        (try? WatchMessage.decode(CheckInMessage.self, from: dictionary))?.measuredAt
    }

    /// The error handler hops to the main actor; give it the turns it needs.
    private func settle(until done: () -> Bool) async {
        for _ in 0..<100 where !done() { await Task.yield() }
    }

    @Test func aCheckInGoesAsAMessageWhenThePhoneIsReachable() {
        link.send(checkIn: checkIn("t1"))
        #expect(session.kinds(session.messages) == ["check-in"])
        #expect(measuredAt(session.messages[0]) == "t1")
        #expect(session.waitingTransfers.isEmpty)
    }

    @Test func aCheckInIsTransferredWhenThePhoneIsNotReachable() {
        session.isReachable = false
        link.send(checkIn: checkIn("t1"))
        #expect(session.messages.isEmpty)
        #expect(session.kinds(session.waitingTransfers) == ["check-in"])
    }

    @Test func aNewerCheckInReplacesAnOlderOneStillWaiting() throws {
        session.isReachable = false
        let event = EventMessage(id: "e1", type: "fall", measuredAt: "t0")
        link.send(event: event)
        link.send(checkIn: checkIn("t1"))
        link.send(checkIn: checkIn("t2"))
        // The event's transfer stays; only the older check-in goes
        #expect(session.kinds(session.waitingTransfers) == ["event", "check-in"])
        #expect(measuredAt(session.waitingTransfers[1]) == "t2")
        #expect(session.cancelled.map(measuredAt) == ["t1"])
    }

    @Test func aFailedCheckInMessageFallsBackToATransfer() async throws {
        link.send(checkIn: checkIn("t1"))
        let onError = try #require(session.onErrors.first)
        onError(LinkDown())
        await settle { !session.waitingTransfers.isEmpty }
        #expect(session.kinds(session.waitingTransfers) == ["check-in"])
        #expect(measuredAt(session.waitingTransfers[0]) == "t1")
    }

    @Test func aLateFailureOfAnOlderCheckInIsNotResent() async throws {
        link.send(checkIn: checkIn("t1"))
        link.send(checkIn: checkIn("t2"))
        session.onErrors[0](LinkDown())
        // Then the newer one fails too, and is the one transferred
        session.onErrors[1](LinkDown())
        await settle { !session.waitingTransfers.isEmpty }
        for _ in 0..<10 { await Task.yield() }
        #expect(session.waitingTransfers.map(measuredAt) == ["t2"])
    }

    @Test func nothingGoesWhileTheLinkIsNotActive() {
        session.isActive = false
        link.send(checkIn: checkIn("t1"))
        link.send(event: EventMessage(id: "e1", type: "fall", measuredAt: "t0"))
        #expect(session.messages.isEmpty)
        #expect(session.waitingTransfers.isEmpty)
    }

    @Test func anEventGoesAsAMessageWhenReachableElseOnceAsATransfer() {
        let event = EventMessage(id: "e1", type: "fall", measuredAt: "t0")
        link.send(event: event)
        #expect(session.kinds(session.messages) == ["event"])
        session.isReachable = false
        link.send(event: event)
        link.send(event: event)
        #expect(session.kinds(session.waitingTransfers) == ["event"])
    }

    @Test func aFailedEventMessageFallsBackToATransfer() async throws {
        link.send(event: EventMessage(id: "e1", type: "fall", measuredAt: "t0"))
        session.onErrors[0](LinkDown())
        await settle { !session.waitingTransfers.isEmpty }
        #expect(session.kinds(session.waitingTransfers) == ["event"])
    }
}
