import CoreLocation
import FirebaseAuth
import Foundation
import Shared
import os

// The phone's relay of the watch (04 §3, UC-09, UC-13), ported from
// android/app/.../push/WearListenerService.kt. The watch is not standalone (G5): every one of its
// events and check-ins reaches FastAPI through here.

/// Watch → phone mapping, as `EventMessage.toEventForm`: `source: "watch"`, an empty snapshot left
/// out, and the phone's last known location when it has a valid one (`lastKnownLocation`).
func eventForm(_ msg: EventMessage, location: CLLocation?) -> EventForm {
    var form = EventForm(
        id: msg.id, type: msg.type, measuredAt: msg.measuredAt, source: "watch",
        snapshot: snapshotForm(msg.snapshot))
    if let fix = location, fix.horizontalAccuracy >= 0 {
        form.latitude = fix.coordinate.latitude
        form.longitude = fix.coordinate.longitude
        form.locationAccuracyM = fix.horizontalAccuracy
    }
    return form
}

/// `CheckInMessage.toCheckInForm`: every field through.
func checkInForm(_ msg: CheckInMessage) -> CheckInForm {
    CheckInForm(
        measuredAt: msg.measuredAt, battery: msg.battery, worn: msg.worn, lastPulse: msg.lastPulse,
        restingPulse: msg.restingPulse, stepsToday: msg.stepsToday,
        minutesWithoutSteps: msg.minutesWithoutSteps)
}

/// `EventSnapshot.toForm`: nil for the empty snapshot, and for none at all.
private func snapshotForm(_ snapshot: EventSnapshot?) -> EventSnapshotForm? {
    guard let snapshot, snapshot != .empty else { return nil }
    return EventSnapshotForm(
        pulse: snapshot.pulse, restingBaseline: snapshot.restingBaseline, moving: snapshot.moving,
        minutesWithoutSteps: snapshot.minutesWithoutSteps, battery: snapshot.battery)
}

/// Posts what the watch sends. Signed out, it does nothing, as `onMessageReceived` returns when
/// `auth.currentUser` is null. An event is acked (`ack(id)`) only after FastAPI answered 2xx; any
/// failure, a 4xx included, leaves it in the watch's queue to be resent, as on Android. A check-in
/// is posted once and never acked. A payload that doesn't decode is logged and dropped: Swift's
/// decoder is strict where Kotlin's defaulted missing fields.
actor Relay {
    private let api: ApiClient
    private let signedIn: @Sendable () -> Bool
    private let location: @MainActor @Sendable () -> CLLocation?
    private let ack: @MainActor @Sendable (String) -> Void
    private let log = Logger(subsystem: "ro.echocare.ios", category: "relay")

    init(
        api: ApiClient,
        signedIn: @escaping @Sendable () -> Bool = { Auth.auth().currentUser != nil },
        location: @escaping @MainActor @Sendable () -> CLLocation?,
        ack: @escaping @MainActor @Sendable (String) -> Void
    ) {
        self.api = api
        self.signedIn = signedIn
        self.location = location
        self.ack = ack
    }

    /// The two strings of a watch message: what `WatchLink.split` copies out of the dictionary
    /// before it hops here.
    func handle(kind: String, json: String) async {
        guard signedIn() else {
            log.info("\(kind, privacy: .public) ignored: signed out")
            return
        }
        switch kind {
        case WatchMessage.event:
            guard let msg = decode(EventMessage.self, kind, json) else { return }
            let form = eventForm(msg, location: await location())
            do {
                _ = try await api.sendEvent(form)
                log.info("event \(msg.id, privacy: .public) accepted")
                // Tell the watch to drop this id from its resend queue (04 §3)
                await ack(msg.id)
            } catch {
                log.error(
                    "event \(msg.id, privacy: .public) not sent: \(String(describing: error), privacy: .public)"
                )
            }
        case WatchMessage.checkIn:
            guard let msg = decode(CheckInMessage.self, kind, json) else { return }
            do {
                try await api.checkIn(checkInForm(msg))
                log.info("check-in sent")
            } catch {
                log.error("check-in not sent: \(String(describing: error), privacy: .public)")
            }
        default:
            log.error("watch message ignored: kind \(kind, privacy: .public)")
        }
    }

    private func decode<T: Decodable>(_ type: T.Type, _ kind: String, _ json: String) -> T? {
        do {
            return try WatchMessage.decode(type, from: ["json": json])
        } catch {
            log.error(
                "\(kind, privacy: .public) doesn't decode: \(String(describing: error), privacy: .public)"
            )
            return nil
        }
    }
}
