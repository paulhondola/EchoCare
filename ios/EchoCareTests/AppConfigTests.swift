import Foundation
import Testing

@testable import EchoCare

// Base.xcconfig's defaults reach the app through Info.plist, as BuildConfig does on Android.
// These hold while Local.xcconfig overrides none of API_URL, REREAD_SECONDS, REAL_SMS.
struct AppConfigTests {
    @Test("API_URL defaults to staging")
    func apiURLDefaultsToStaging() {
        #expect(AppConfig.apiURL.absoluteString == "https://echocare-api-staging.up.railway.app")
    }

    @Test("REREAD_SECONDS defaults to 30")
    func rereadDefaultsTo30() {
        #expect(AppConfig.rereadSeconds == 30)
    }

    @Test("Debug builds are demo builds")
    func debugIsDemo() {
        #expect(AppConfig.isDemo)
    }
}
