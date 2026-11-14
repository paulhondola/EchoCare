import SwiftUI

/// Each role's home (android/app/.../home/Routes.kt `homeFor`): DAS's incidents for any role not
/// listed. The senior's is `SeniorHome`; the rest are placeholders, each the role's title in a
/// `Frame`, until Task 9 (caregiver, medic) and Task 11 (DAS) replace their case.
struct RoleHome: View {
    let role: String
    /// A read refused as signed out or not registered ends the session (seniors §8.2).
    let onSessionEnd: (Failure) -> Void

    var body: some View {
        switch role {
        case "medic": Placeholder(title: String(localized: "medic_home"))
        case "caregiver": Placeholder(title: String(localized: "caregiver_home"))
        case "senior": SeniorHome(onSessionEnd: onSessionEnd)
        default: Placeholder(title: String(localized: "role_das"))
        }
    }
}

private struct Placeholder: View {
    let title: String

    var body: some View {
        Frame(title) { EmptyView() }
    }
}
