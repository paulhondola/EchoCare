import Foundation

/// The phone's end of the watch link (design 2026-11-14-ios-port, WatchConnectivity). A stub until
/// Task 8, which fills it: `activate()`, the WCSessionDelegate and the real `startMonitoring()`.
/// Task 6 only needs the signature, for „Pornește monitorizarea” on the senior's home.
// `@unchecked Sendable`: `shared` is global state, and Task 8 keeps what it holds behind its own queue.
final class WatchLink: NSObject, @unchecked Sendable {
    static let shared = WatchLink()

    /// Asks the watch to start monitoring (`HKHealthStore.startWatchApp(with:)`). Throws when it
    /// can't be reached.
    func startMonitoring() async throws {}
}
