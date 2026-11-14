import HealthKit
import SwiftUI
import WatchKit

// The senior's watch (G5): one screen and the monitoring session. It never calls FastAPI; events
// and check-ins go to the senior's phone.
@main
struct EchoCareWatchApp: App {
    @WKApplicationDelegateAdaptor(WatchDelegate.self) private var delegate

    var body: some Scene {
        WindowGroup {
            RootView(monitor: delegate.monitor)
        }
    }
}

/// `MainActivity.kt`: „Sunteți bine?” over the home while a prompt is up.
private struct RootView: View {
    let monitor: Monitor

    var body: some View {
        if let prompt = monitor.prompt {
            AreYouOkView(prompt: prompt) { ok in monitor.answer(ok: ok) }
        } else {
            HomeView(monitor: monitor)
        }
    }
}

/// Owns the watch's objects. WatchConnectivity is activated at launch, before any screen, and the
/// phone's `startWatchApp(with:)` arrives here as `handle(_ workoutConfiguration:)` (spike).
@MainActor
final class WatchDelegate: NSObject, WKApplicationDelegate {
    let monitor: Monitor
    private let runner: WorkoutRunner
    private let link: PhoneLink

    override init() {
        let queue = EventQueue.standard()
        runner = WorkoutRunner()
        link = PhoneLink(queue: queue)
        monitor = Monitor(sensors: runner, link: link, queue: queue)
        super.init()
        link.onAcked = { [monitor] id in monitor.eventReceived(id: id) }
    }

    func applicationDidFinishLaunching() {
        link.activate()
    }

    func handle(_ workoutConfiguration: HKWorkoutConfiguration) {
        guard !monitor.running else { return }
        runner.configuration = workoutConfiguration
        Task { await monitor.start() }
    }
}
