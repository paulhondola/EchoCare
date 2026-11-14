import Testing
import UIKit
@testable import EchoCare

// Firebase phone sign-in first sends a fake remote notification through the app delegate and waits
// for it to reach Auth (AuthNotificationManager.checkNotificationForwarding); without it every
// code request fails with FIRAuthErrorDomain 17054, test numbers included.
@MainActor
struct AppDelegateTests {
    private let remoteNotification =
        #selector(UIApplicationDelegate.application(_:didReceiveRemoteNotification:fetchCompletionHandler:))

    // The question Firebase asks of the delegate SwiftUI installs for UIApplicationDelegateAdaptor,
    // which forwards only what our AppDelegate implements.
    @Test func theInstalledDelegateTakesRemoteNotifications() {
        #expect(UIApplication.shared.delegate?.responds(to: remoteNotification) == true)
    }

    @Test func aNotificationFirebaseDoesNotOwnStillCompletes() {
        var results: [UIBackgroundFetchResult] = []
        AppDelegate().application(
            UIApplication.shared,
            didReceiveRemoteNotification: ["aps": ["content-available": 1]]
        ) { results.append($0) }
        #expect(results == [.noData])
    }
}
