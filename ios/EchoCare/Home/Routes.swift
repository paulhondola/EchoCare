// Where each role lands (seniors §8.2), ported from android/app/.../home/Routes.kt `homeFor`. The
// pages that open from a home are `HomeRoute` (HomeNav.swift); the label maps are Labels.swift.
// Android's `alertRoute` is not ported: iOS has no push (design, Out of scope).

/// The root of the signed-in app for a role.
enum StartRoute: Hashable {
    /// The medic's home: their tasks, most important first, and the codes (design 2026-11-13 medic home).
    case medicHome
    /// The seniors the caller reaches as `role`: the caregiver's home.
    case seniors(role: String)
    /// The senior's home: their own page.
    case own
    /// The DAS home: open and in-progress incidents (UC-12).
    case incidents
}

/// Where `role` lands after sign-in. `role` is one of `roles` (Auth/Screen.swift).
func homeFor(_ role: String) -> StartRoute {
    switch role {
    case "medic": .medicHome
    case "caregiver": .seniors(role: role)
    case "senior": .own
    default: .incidents
    }
}
