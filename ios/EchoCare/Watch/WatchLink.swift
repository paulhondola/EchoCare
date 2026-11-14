import Foundation

/// Why the watch can't be started.
enum WatchLinkError: Error {
    /// Task 6's stub: nothing is wired to the watch yet, so no one is told it is watching.
    case notAvailable
}

/// The phone's end of the watch link (design 2026-11-14-ios-port, WatchConnectivity). A stub until
/// Task 8, which fills it: `activate()`, the WCSessionDelegate and the real `startMonitoring()`.
/// Task 6 only needs the signature, for „Pornește monitorizarea” on the senior's home.
// `@unchecked Sendable`: `shared` is global state, and Task 8 keeps what it holds behind its own queue.
final class WatchLink: NSObject, @unchecked Sendable {
    static let shared = WatchLink()

    /// Asks the watch to start monitoring (`HKHealthStore.startWatchApp(with:)`). Throws when it
    /// can't be reached.
    func startMonitoring() async throws {
        // Task 8 replaces this. Until then it must not look as if the watch started.
        throw WatchLinkError.notAvailable
    }
}
