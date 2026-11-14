import CoreLocation

// The phone's last known location, attached to the events we post (UC-09 §5, 04 §3). Ported from
// android/app/.../home/LocationHelper.kt: nil when the senior has not allowed location or no fix
// has come yet. The request never waits for it.

/// Asks for when-in-use access once and keeps a fix fresh, so `lastKnown` has something at the tap.
/// shortcut: `CLLocationManager.location` is best-effort, and may be stale by minutes. Android's
/// `getLastKnownLocation` is the same; upgrade to a continuous stream when staleness matters.
@MainActor
final class LocationHelper: NSObject, CLLocationManagerDelegate {
    private let manager = CLLocationManager()

    override init() {
        super.init()
        manager.delegate = self
        // A coarse fix is enough for an address-level alert, and quicker and kinder to the battery
        manager.desiredAccuracy = kCLLocationAccuracyHundredMeters
    }

    /// The home's first read: asks for access if the senior was never asked, else refreshes the fix.
    func prepare() {
        switch manager.authorizationStatus {
        case .notDetermined: manager.requestWhenInUseAuthorization()
        case .authorizedWhenInUse, .authorizedAlways: manager.requestLocation()
        default: break
        }
    }

    /// The fix the system holds; nil without permission or before any fix.
    func lastKnown() -> CLLocation? {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: manager.location
        default: nil
        }
    }

    // The system calls these on the main thread, where the manager was created.
    nonisolated func locationManagerDidChangeAuthorization(_ manager: CLLocationManager) {
        switch manager.authorizationStatus {
        case .authorizedWhenInUse, .authorizedAlways: manager.requestLocation()
        default: break
        }
    }

    nonisolated func locationManager(_ manager: CLLocationManager, didUpdateLocations locations: [CLLocation]) {}

    // A failed one-shot request leaves `location` as it was: the request goes without a fix
    nonisolated func locationManager(_ manager: CLLocationManager, didFailWithError error: Error) {}
}
