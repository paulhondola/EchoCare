import Foundation

/// Android's BuildConfig fields (android/app/build.gradle.kts). Base.xcconfig sets them and
/// Local.xcconfig overrides them; Config/EchoCare-Info.plist carries them into the app.
struct AppConfig {
    /// Every route is under `apiURL/api/`, as on Android.
    static let apiURL: URL = {
        guard let url = URL(string: string("EchoCareAPIURL")), url.scheme != nil else {
            fatalError("EchoCareAPIURL is not a URL; check API_URL in Local.xcconfig")
        }
        return url
    }()

    /// How often an open screen re-reads (06 §3): iOS has no push, so this is the only refresh.
    static let rereadSeconds: Int = {
        guard let seconds = Int(string("EchoCareRereadSeconds")), seconds > 0 else {
            fatalError("EchoCareRereadSeconds is not a positive number; check REREAD_SECONDS")
        }
        return seconds
    }()

    /// YES keeps Firebase's app verification on, for real numbers and real SMS (auth-layer §9).
    static let realSMS: Bool = string("EchoCareRealSMS").uppercased() == "YES"

    /// Debug builds are demo builds, with the Wear OS demo timings (BuildConfig.DEMO).
    static let isDemo: Bool = {
        #if DEMO
            true
        #else
            false
        #endif
    }()

    private static func string(_ key: String) -> String {
        guard let value = Bundle.main.object(forInfoDictionaryKey: key) as? String else {
            fatalError("\(key) is missing from Info.plist; see Config/EchoCare-Info.plist")
        }
        return value
    }
}
