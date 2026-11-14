import FirebaseCore
import SwiftUI

// One app for the four roles (G3). Sign-in and role routing replace the placeholder (Task 5).
@main
struct EchoCareApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate

    var body: some Scene {
        WindowGroup {
            ZStack {
                Theme.canvas.ignoresSafeArea()
                Text("app_name")
                    .textStyle(Theme.headlineLarge)
                    .foregroundStyle(Theme.fg)
            }
        }
    }
}

// WatchConnectivity relaunches the app in the background before any view exists (design, Spike
// results), so start-up work lives here rather than in a view.
final class AppDelegate: NSObject, UIApplicationDelegate {
    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        FirebaseApp.configure()
        return true
    }
}
