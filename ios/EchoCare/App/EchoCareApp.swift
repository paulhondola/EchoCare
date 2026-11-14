import FirebaseAuth
import FirebaseCore
import SwiftUI

// One app for the four roles (G3): sign-in, then the role's home (auth-layer §8.2).
@main
struct EchoCareApp: App {
    @UIApplicationDelegateAdaptor(AppDelegate.self) private var appDelegate
    // Created before the delegate configures Firebase: AuthModel touches it only from start()
    @State private var auth = AuthModel()

    var body: some Scene {
        WindowGroup {
            RootView(auth: auth)
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
        // Before the first auth call, as Android's Modules.kt. Affects only Firebase's test numbers
        // (auth-layer §8.2, §9 step 1). REAL_SMS = YES leaves app verification on for real numbers:
        // with no APNs, Firebase verifies the app with its reCAPTCHA page.
        Auth.auth().settings?.isAppVerificationDisabledForTesting = !AppConfig.realSMS
        // Here, not in a view: a watch message relaunches the app with no UI (Spike results)
        WatchLink.shared.activate()
        return true
    }
}
