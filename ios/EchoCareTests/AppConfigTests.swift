import Foundation
import Testing

@testable import EchoCare

// Base.xcconfig's defaults reach the app through Info.plist, as BuildConfig does on Android.
// The signer's Local.xcconfig, or a build setting on the command line (REAL_SMS=YES for the demo
// install), may override any of them: each default test then skips rather than fails, and the
// "reads what the build put in" tests still check AppConfig against that build's Info.plist.
private enum Built {
    static let stagingURL = "https://echocare-api-staging.up.railway.app"

    /// What this build wrote into the host app's Info.plist.
    static func value(_ key: String) -> String? {
        Bundle.main.object(forInfoDictionaryKey: key) as? String
    }

    static func isDefault(_ key: String, _ documented: String) -> Bool {
        value(key) == documented
    }
}

struct AppConfigTests {
    @Test("AppConfig reads the build's API_URL")
    func apiURLIsTheBuilt() {
        #expect(AppConfig.apiURL.absoluteString == Built.value("EchoCareAPIURL"))
    }

    @Test(
        "API_URL defaults to staging",
        .enabled(if: Built.isDefault("EchoCareAPIURL", Built.stagingURL), "API_URL is overridden for this build"))
    func apiURLDefaultsToStaging() {
        #expect(AppConfig.apiURL.absoluteString == Built.stagingURL)
    }

    @Test("AppConfig reads the build's REREAD_SECONDS")
    func rereadIsTheBuilt() {
        #expect(String(AppConfig.rereadSeconds) == Built.value("EchoCareRereadSeconds"))
    }

    @Test(
        "REREAD_SECONDS defaults to 30",
        .enabled(if: Built.isDefault("EchoCareRereadSeconds", "30"), "REREAD_SECONDS is overridden for this build"))
    func rereadDefaultsTo30() {
        #expect(AppConfig.rereadSeconds == 30)
    }

    @Test("AppConfig reads the build's REAL_SMS")
    func realSMSIsTheBuilt() {
        #expect(AppConfig.realSMS == (Built.value("EchoCareRealSMS")?.uppercased() == "YES"))
    }

    @Test(
        "REAL_SMS defaults to NO",
        .enabled(if: Built.isDefault("EchoCareRealSMS", "NO"), "REAL_SMS is overridden for this build"))
    func realSMSDefaultsToNo() {
        #expect(!AppConfig.realSMS)
    }

    @Test("Debug builds are demo builds")
    func debugIsDemo() {
        #expect(AppConfig.isDemo)
    }
}
