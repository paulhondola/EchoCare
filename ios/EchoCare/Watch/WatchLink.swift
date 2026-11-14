import CoreLocation
import HealthKit
import Shared
import Synchronization
import UIKit
import WatchConnectivity
import os

/// Why the watch can't be started.
enum WatchLinkError: Error {
    /// No HealthKit on this device (an iPad), so no `startWatchApp`.
    case notAvailable
}

/// What the phone last heard from the watch, for „Pornește monitorizarea” on the senior's home.
struct WatchSeen: Equatable, Sendable {
    /// When the last event or check-in arrived; nil since launch.
    var lastHeard: Date?
    /// Whether a paired watch has the app; nil until WCSession has activated and said.
    var appInstalled: Bool?
}

/// The phone's end of the watch link (04 §3, design 2026-11-14-ios-port "Watch ↔ phone"), the
/// counterpart of the watch's PhoneLink.swift. Events and check-ins arrive with `sendMessage` or
/// `transferUserInfo`, each `WatchMessage.encode` plus `"kind"`; `Relay` posts them. An accepted event is answered with `kind: "received"` and `{"id": …}`, by
/// `sendMessage` when the watch is reachable, else `transferUserInfo`.
///
/// WatchConnectivity relaunches the app in the background before any view exists (Spike results),
/// so `activate()` runs from `application(_:didFinishLaunchingWithOptions:)` and the relay needs
/// nothing but a signed-in Firebase user. Main-actor isolated; the WCSessionDelegate methods
/// arrive on a background queue, copy out Sendable values and hop over.
@MainActor
final class WatchLink: NSObject {
    static let shared = WatchLink()

    /// The watch's check-in interval (06 §3), the value the watch's `Timings.checkInMinutes` reads.
    nonisolated static let checkInInterval: TimeInterval = CheckInInterval.seconds(
        demo: AppConfig.isDemo)

    private(set) var seen = WatchSeen()

    private let session: WCSession?
    // For the relay's background task, begun off the main actor (UIKit's begin and end are nonisolated)
    nonisolated private let application: UIApplication
    private let store = HKHealthStore()
    // The fix the system holds; the senior's home asks for access (LocationHelper.prepare)
    private let location = LocationHelper()
    private let log = Logger(subsystem: "ro.echocare.ios", category: "watch")
    private lazy var relay = Relay(
        api: ApiClient(tokens: FirebaseTokenSource()),
        location: { [location] in location.lastKnown() },
        ack: { [weak self] id in self?.sendAck(id) })

    /// First touched from `application(_:didFinishLaunchingWithOptions:)`, so the application exists.
    override init() {
        session = WCSession.isSupported() ? WCSession.default : nil
        application = UIApplication.shared
        super.init()
    }

    /// Call once at launch, before any message can arrive.
    func activate() {
        guard let session else {
            log.error("WatchConnectivity is not supported")
            return
        }
        session.delegate = self
        session.activate()
    }

    /// „Pornește monitorizarea”: launches the watch app into its workout session
    /// (`HKHealthStore.startWatchApp(with:)`, the configuration of the watch's
    /// `WorkoutRunner.defaultConfiguration()`). Throws when it can't, error 550 when the watch app
    /// isn't installed (Spike results).
    func startMonitoring() async throws {
        guard HKHealthStore.isHealthDataAvailable() else { throw WatchLinkError.notAvailable }
        // As the spike: the phone asks for the workout and heart rate before starting the watch
        let share: Set<HKSampleType> = [HKObjectType.workoutType()]
        let read: Set<HKObjectType> = [HKQuantityType(.heartRate)]
        do {
            if try await store.statusForAuthorizationRequest(toShare: share, read: read)
                == .shouldRequest
            {
                try await store.requestAuthorization(toShare: share, read: read)
            }
            let configuration = HKWorkoutConfiguration()
            configuration.activityType = .other
            configuration.locationType = .indoor
            try await store.startWatchApp(toHandle: configuration)
            log.info("watch app started")
        } catch {
            log.error("watch app not started: \(String(describing: error), privacy: .public)")
            throw error
        }
    }

    /// The ack the watch's `PhoneLink.ackedId(in:)` reads.
    nonisolated static func ackPayload(id: String) -> [String: Any]? {
        do {
            var payload = try WatchMessage.encode(Received(id: id))
            payload["kind"] = WatchMessage.received
            return payload
        } catch {
            return nil
        }
    }

    private struct Received: Encodable {
        var id: String
    }

    /// The two strings of a watch message, `"kind"` and `"json"` (`WatchMessage`), copied out of the
    /// dictionary before the hop to the main actor: the dictionary isn't Sendable. Nil without them.
    nonisolated static func split(_ payload: [String: Any]) -> (kind: String, json: String)? {
        guard let kind = payload["kind"] as? String, let json = payload["json"] as? String else {
            return nil
        }
        return (kind, json)
    }

    // MARK: Private

    /// Posts one watch message inside the background task `received(_:)` began, and ends it when
    /// the post is done.
    private func relay(kind: String, json: String, background: BackgroundTask) {
        if kind == WatchMessage.event || kind == WatchMessage.checkIn { seen.lastHeard = Date() }
        let relay = relay
        Task {
            await relay.handle(kind: kind, json: json)
            background.end()
        }
    }

    private func sendAck(_ id: String) {
        guard let session, session.activationState == .activated,
            let payload = Self.ackPayload(id: id)
        else {
            log.error("ack \(id, privacy: .public) not sent: the link is not active")
            return
        }
        if session.isReachable {
            session.sendMessage(
                payload, replyHandler: nil,
                // @Sendable: WatchConnectivity calls it on its own queue, not the main actor
                errorHandler: { @Sendable [weak self] error in
                    let reason = error.localizedDescription
                    Task { @MainActor in self?.transferAck(id, reason: reason) }
                })
            log.info("ack \(id, privacy: .public) sent")
        } else {
            session.transferUserInfo(payload)
            log.info("ack \(id, privacy: .public) queued for transfer")
        }
    }

    private func transferAck(_ id: String, reason: String) {
        log.error("ack \(id, privacy: .public) send failed: \(reason, privacy: .public)")
        guard let session, session.activationState == .activated,
            let payload = Self.ackPayload(id: id)
        else {
            return
        }
        session.transferUserInfo(payload)
    }

    private func watchState(activated: Bool, paired: Bool, installed: Bool) {
        seen.appInstalled = activated ? paired && installed : nil
        log.info("watch paired=\(paired) installed=\(installed)")
    }

    nonisolated private func received(_ payload: [String: Any]) {
        guard let (kind, json) = Self.split(payload) else {
            Logger(subsystem: "ro.echocare.ios", category: "watch").error(
                "watch message ignored: no kind or json")
            return
        }
        // Begun here, before the hop: a background relaunch could be suspended in between, or
        // mid-request
        let background = BackgroundTask(name: "relay \(kind)", application: application)
        Task { @MainActor in self.relay(kind: kind, json: json, background: background) }
    }
}

/// `UIApplication.beginBackgroundTask` for one relay, ended once: when the post is done or when
/// iOS says time is up, whichever comes first. UIKit's begin and end are thread-safe.
private final class BackgroundTask: Sendable {
    private let application: UIApplication
    private let id = Mutex(UIBackgroundTaskIdentifier.invalid)

    init(name: String, application: UIApplication) {
        self.application = application
        let begun = application.beginBackgroundTask(withName: name) { [weak self] in self?.end() }
        id.withLock { $0 = begun }
    }

    func end() {
        let current = id.withLock { id in
            defer { id = .invalid }
            return id
        }
        guard current != .invalid else { return }
        application.endBackgroundTask(current)
    }
}

extension WatchLink: WCSessionDelegate {
    nonisolated func session(
        _ session: WCSession, activationDidCompleteWith activationState: WCSessionActivationState,
        error: (any Error)?
    ) {
        let activated = activationState == .activated
        let paired = session.isPaired
        let installed = session.isWatchAppInstalled
        let reason = error?.localizedDescription ?? "none"
        Task { @MainActor in
            self.log.info("link active=\(activated) error=\(reason, privacy: .public)")
            self.watchState(activated: activated, paired: paired, installed: installed)
        }
    }

    nonisolated func sessionWatchStateDidChange(_ session: WCSession) {
        let activated = session.activationState == .activated
        let paired = session.isPaired
        let installed = session.isWatchAppInstalled
        Task { @MainActor in
            self.watchState(activated: activated, paired: paired, installed: installed)
        }
    }

    nonisolated func sessionDidBecomeInactive(_ session: WCSession) {}

    /// The senior switched watches: activate again for the new one.
    nonisolated func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }

    nonisolated func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        received(message)
    }

    /// Answered at once: the ack goes separately, after FastAPI answered.
    nonisolated func session(
        _ session: WCSession, didReceiveMessage message: [String: Any],
        replyHandler: @escaping ([String: Any]) -> Void
    ) {
        received(message)
        replyHandler([:])
    }

    nonisolated func session(_ session: WCSession, didReceiveUserInfo userInfo: [String: Any]) {
        received(userInfo)
    }
}
