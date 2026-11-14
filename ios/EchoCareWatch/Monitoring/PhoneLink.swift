import Foundation
import Shared
import WatchConnectivity
import os

/// The watch's end of the link to the senior's phone (04 §3, design "Watch ↔ phone"). Events go
/// with `sendMessage` when the phone is reachable, which wakes the iPhone app, else with
/// `transferUserInfo`, which WatchConnectivity queues; check-ins always with `transferUserInfo`.
/// Each dictionary is `WatchMessage.encode` plus `"kind"`. The phone answers an event with
/// `kind: "received"` and `{"id": "<event id>"}` as the JSON, which clears it from the queue.
///
/// Main-actor isolated; the WCSessionDelegate methods arrive on a background queue, decode there
/// into Sendable values and hop over.
@MainActor
final class PhoneLink: NSObject, PhoneSending {
    private let queue: EventQueue
    private let session: WCSession?
    private let log = Logger(subsystem: "ro.echocare.watch", category: "link")

    init(queue: EventQueue) {
        self.queue = queue
        session = WCSession.isSupported() ? WCSession.default : nil
        super.init()
    }

    /// Call once at launch, before anything is sent.
    func activate() {
        guard let session else {
            log.error("WatchConnectivity is not supported")
            return
        }
        session.delegate = self
        session.activate()
    }

    func send(event: EventMessage) {
        guard let session, session.activationState == .activated else {
            // Kept in the queue; resent on activation, on reachability and every minute
            log.info("event \(event.id, privacy: .public) waits: the link is not active")
            return
        }
        guard let payload = Self.payload(WatchMessage.event, event) else { return }
        if session.isReachable {
            let id = event.id
            session.sendMessage(
                payload, replyHandler: nil,
                // @Sendable: WatchConnectivity calls it on its own queue, not the main actor
                errorHandler: { @Sendable [weak self] error in
                    let reason = error.localizedDescription
                    Task { @MainActor in self?.sendFailed(event, id: id, reason: reason) }
                })
            log.info("event \(event.id, privacy: .public) sent")
        } else {
            transfer(event, payload: payload, session: session)
        }
    }

    func send(checkIn: CheckInMessage) {
        guard let session, session.activationState == .activated else {
            log.info("check-in skipped: the link is not active")
            return
        }
        guard let payload = Self.payload(WatchMessage.checkIn, checkIn) else { return }
        // Only the latest check-in is worth delivering (UC-13 reads the newest)
        for transfer in session.outstandingUserInfoTransfers
        where transfer.userInfo["kind"] as? String == WatchMessage.checkIn {
            transfer.cancel()
        }
        session.transferUserInfo(payload)
        log.info("check-in queued")
    }

    // MARK: Private

    private func sendFailed(_ event: EventMessage, id: String, reason: String) {
        log.error("event \(id, privacy: .public) send failed: \(reason, privacy: .public)")
        guard let session, session.activationState == .activated,
            let payload = Self.payload(WatchMessage.event, event)
        else { return }
        transfer(event, payload: payload, session: session)
    }

    /// `transferUserInfo`, once per event: the minute's resend doesn't pile up copies while the
    /// phone is away.
    private func transfer(_ event: EventMessage, payload: [String: Any], session: WCSession) {
        let already = session.outstandingUserInfoTransfers.contains { transfer in
            transfer.userInfo["kind"] as? String == WatchMessage.event
                && (try? WatchMessage.decode(EventMessage.self, from: transfer.userInfo))?.id == event.id
        }
        if already { return }
        session.transferUserInfo(payload)
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
