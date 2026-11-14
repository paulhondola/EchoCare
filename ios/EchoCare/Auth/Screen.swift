import Foundation

// Ported from android/app/.../auth/Screen.kt.

/// The roles this build has screens for, in GET /me's order (auth-layer §3.3).
let roles = ["das", "medic", "caregiver", "senior"]

/// Each role's name, for the role picker and the profile page (`Localizable.xcstrings` keys).
let roleLabels = [
    "das": "role_das",
    "medic": "role_medic",
    "caregiver": "role_caregiver",
    "senior": "role_senior",
]

/// What the sign-in flow shows (auth-layer §8.2). `error` is a `Localizable.xcstrings` key.
enum Screen: Equatable {
    /// Signed out: what EchoCare does, with *Intrați* leading on to `phone`.
    case landing
    case phone(error: String? = nil)
    case code(error: String? = nil)
    case loading
    case notRegistered
    case unavailable
    case pickRole([String])
    /// The app in `role`; `roles` are every role it may switch to, from the profile page.
    case home(role: String, displayName: String, roles: [String])

    var canSwitch: Bool {
        if case .home(_, _, let roles) = self { roles.count > 1 } else { false }
    }
}

/// The granted roles this build knows, once each, in `roles` order.
func rolesOf(_ me: Me) -> [String] {
    let granted = Set(me.grants.map(\.role))
    return roles.filter(granted.contains)
}

/// The screen after GET /me answers 200 (auth-layer §8.2). `saved` is the role picked earlier.
/// Roles this build does not know are dropped (app/AGENTS.md: decode leniently); AL3 counts distinct roles.
func screenFor(_ me: Me, saved: String?) -> Screen {
    let known = rolesOf(me)
    if known.isEmpty { return .notRegistered }
    if known.count == 1 { return .home(role: known[0], displayName: me.displayName, roles: known) }
    if let saved, known.contains(saved) {
        return .home(role: saved, displayName: me.displayName, roles: known)
    }
    return .pickRole(known)
}

/// The screen after GET /me fails with HTTP `status` (auth-layer §3.2). A 401 arrives only after
/// ApiClient's retry, so it means sign in again. /me refuses with 403 only for `not_registered`.
func screenFor(status: Int) -> Screen {
    switch status {
    case 401: .phone()
    case 403: .notRegistered
    default: .unavailable
    }
}

/// What the person typed, as E.164 (auth-layer §7.1). The server normalizes again.
func toE164(_ raw: String) -> String {
    let digits = raw.replacing(/[\s\-.()]/, with: "")
    if digits.hasPrefix("00") { return "+" + digits.dropFirst(2) }
    if digits.hasPrefix("0") { return "+40" + digits.dropFirst() }
    if digits.hasPrefix("7") { return "+40" + digits }
    return digits
}
