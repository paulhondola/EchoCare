import Foundation
import Shared
import WatchConnectivity
import os

/// What PhoneLink uses of `WCSession` to send, so the tests can see which way each message goes.
/// WCSession's methods are thread-safe; PhoneLink calls them from the main actor.
protocol LinkSession: AnyObject {
    var isActive: Bool { get }
    var isReachable: Bool { get }
    /// `sendMessage` with no reply handler: delivered at once, and it wakes the iPhone app.
    func send(message: [String: Any], onError: @escaping @Sendable (any Error) -> Void)
    /// `transferUserInfo`: queued by WatchConnectivity until the phone takes it.
    func transfer(_ userInfo: [String: Any])
    /// The dictionaries of the transfers still waiting.
    var waitingTransfers: [[String: Any]] { get }
    /// Cancels the waiting transfers whose dictionary matches.
    func cancelWaiting(where match: ([String: Any]) -> Bool)
}

extension WCSession: LinkSession {
    var isActive: Bool { activationState == .activated }

    func send(message: [String: Any], onError: @escaping @Sendable (any Error) -> Void) {
        sendMessage(message, replyHandler: nil, errorHandler: onError)
    }

    func transfer(_ userInfo: [String: Any]) {
        transferUserInfo(userInfo)
    }

    var waitingTransfers: [[String: Any]] { outstandingUserInfoTransfers.map(\.userInfo) }

    func cancelWaiting(where match: ([String: Any]) -> Bool) {
        for transfer in outstandingUserInfoTransfers where match(transfer.userInfo) { transfer.cancel() }
    }
}

/// The watch's end of the link to the senior's phone (04 §3, design "Watch ↔ phone"). Events and
/// check-ins go with `sendMessage` when the phone is reachable, which wakes the iPhone app, as the
/// Wear OS Data Layer's `sendMessage` does; else, or when that fails, with `transferUserInfo`,
/// which WatchConnectivity queues. Each dictionary is `WatchMessage.encode` plus `"kind"`. The
/// phone answers an event with `kind: "received"` and `{"id": "<event id>"}` as the JSON, which
/// clears it from the queue; a check-in is never answered, and only the newest one waits.
///
/// Main-actor isolated; the WCSessionDelegate methods arrive on a background queue, decode there
/// into Sendable values and hop over.
@MainActor
final class PhoneLink: NSObject, PhoneSending {
    private let queue: EventQueue
    private let session: (any LinkSession)?
    // The same session, for activation and its delegate; nil in tests
    private let wcSession: WCSession?
    private let log = Logger(subsystem: "ro.echocare.watch", category: "link")
    // The newest check-in sent, so a late failure of an older one doesn't resend it
    private var lastCheckIn: CheckInMessage?

    init(queue: EventQueue) {
        self.queue = queue
        wcSession = WCSession.isSupported() ? WCSession.default : nil
        session = wcSession
        super.init()
    }

    /// For tests: sends through `session`, with no WCSession to activate.
    init(queue: EventQueue, session: any LinkSession) {
        self.queue = queue
        self.session = session
        wcSession = nil
        super.init()
    }

    /// Call once at launch, before anything is sent.
    func activate() {
        guard let wcSession else {
            log.error("WatchConnectivity is not supported")
            return
        }
        wcSession.delegate = self
        wcSession.activate()
    }

    func send(event: EventMessage) {
        guard let session, session.isActive else {
            // Kept in the queue; resent on activation, on reachability and every minute
            log.info("event \(event.id, privacy: .public) waits: the link is not active")
            return
        }
        guard let payload = Self.payload(WatchMessage.event, event) else { return }
        if session.isReachable {
            let id = event.id
            session.send(
                message: payload,
                // @Sendable: WatchConnectivity calls it on its own queue, not the main actor
                onError: { @Sendable [weak self] error in
                    let reason = error.localizedDescription
                    Task { @MainActor in self?.sendFailed(event, id: id, reason: reason) }
                })
            log.info("event \(event.id, privacy: .public) sent")
        } else {
            transfer(event, payload: payload, session: session)
        }
    }

    /// As an event, without the queue: a suspended iPhone app gets a `transferUserInfo` only when
    /// it next runs, and by then the dashboard has marked the watch offline (UC-13).
    func send(checkIn: CheckInMessage) {
        guard let session, session.isActive else {
            log.info("check-in skipped: the link is not active")
            return
        }
        guard let payload = Self.payload(WatchMessage.checkIn, checkIn) else { return }
        lastCheckIn = checkIn
        if session.isReachable {
            session.send(
                message: payload,
                onError: { @Sendable [weak self] error in
                    let reason = error.localizedDescription
                    Task { @MainActor in self?.checkInFailed(checkIn, reason: reason) }
                })
            log.info("check-in sent")
        } else {
            transfer(checkIn: payload, session: session)
        }
    }

    // MARK: Private

    private func checkInFailed(_ checkIn: CheckInMessage, reason: String) {
        log.error("check-in send failed: \(reason, privacy: .public)")
        // A newer check-in has gone since; it says more than this one
        guard checkIn == lastCheckIn, let session, session.isActive,
            let payload = Self.payload(WatchMessage.checkIn, checkIn)
        else { return }
        transfer(checkIn: payload, session: session)
    }

    /// `transferUserInfo`, replacing any older check-in still waiting: only the newest is worth
    /// delivering (UC-13 reads the newest).
    private func transfer(checkIn payload: [String: Any], session: any LinkSession) {
        session.cancelWaiting { $0["kind"] as? String == WatchMessage.checkIn }
        session.transfer(payload)
        log.info("check-in queued for transfer")
    }

    private func sendFailed(_ event: EventMessage, id: String, reason: String) {
        log.error("event \(id, privacy: .public) send failed: \(reason, privacy: .public)")
        guard let session, session.isActive,
            let payload = Self.payload(WatchMessage.event, event)
        else { return }
        transfer(event, payload: payload, session: session)
    }

    /// `transferUserInfo`, once per event: the minute's resend doesn't pile up copies while the
    /// phone is away.
    private func transfer(_ event: EventMessage, payload: [String: Any], session: any LinkSession) {
        let already = session.waitingTransfers.contains { userInfo in
            userInfo["kind"] as? String == WatchMessage.event
                && (try? WatchMessage.decode(EventMessage.self, from: userInfo))?.id == event.id
        }
        if already { return }
        session.transfer(payload)
        log.info("event \(event.id, privacy: .public) queued for transfer")
    }

    private func resendPending() {
        let pending = queue.pending()
        if pending.isEmpty { return }
        log.info("resending \(pending.count) queued event(s)")
        pending.forEach { send(event: $0) }
    }

    private func acked(_ id: String) {
        queue.ack(id: id)
        log.info("event acked id=\(id, privacy: .public)")
    }

    /// `WatchMessage.encode` plus `"kind"`: what the phone's relay reads (Task 8).
    nonisolated static func payload<T: Encodable>(_ kind: String, _ value: T) -> [String: Any]? {
        do {
            var payload = try WatchMessage.encode(value)
            payload["kind"] = kind
            return payload
        } catch {
            Logger(subsystem: "ro.echocare.watch", category: "link")
                .error("can't encode \(kind, privacy: .public): \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    /// The acked id in a phone → watch message, or nil for anything else. Swift's decoder is strict
    /// where Kotlin's defaulted missing fields: a payload that doesn't decode is logged and ignored,
    /// and acks nothing.
    nonisolated static func ackedId(in message: [String: Any]) -> String? {
        guard message["kind"] as? String == WatchMessage.received else { return nil }
        do {
            let id = try WatchMessage.decode(Received.self, from: message).id
            return id.isEmpty ? nil : id
        } catch {
            Logger(subsystem: "ro.echocare.watch", category: "link")
                .error("received message ignored: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }

    private struct Received: Decodable {
        var id: String
    }

    nonisolated private func handle(_ message: [String: Any]) {
        guard let id = Self.ackedId(in: message) else { return }
        Task { @MainActor in self.acked(id) }
    }
}

extension PhoneLink: WCSessionDelegate {
    nonisolated func session(
        _ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState, error: (any Error)?
    ) {
        let active = activationState == .activated
        let reason = error?.localizedDescription ?? "none"
        Task { @MainActor in
            self.log.info("link active=\(active) error=\(reason, privacy: .public)")
            if active { self.resendPending() }
        }
    }

    nonisolated func sessionReachabilityDidChange(_ session: WCSession) {
        let reachable = session.isReachable
        Task { @MainActor in
            self.log.info("phone reachable=\(reachable)")
            if reachable { self.resendPending() }
        }
    }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        handle(message)
    }

    nonisolated func session(
        _ session: WCSession, didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        handle(message)
        replyHandler([:])
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        handle(userInfo)
    }
}
