import SwiftUI

/// Each role's home (android/app/.../home/Routes.kt `homeFor`): DAS's incidents for any role not
/// listed. Placeholders, each the role's title in a `Frame`, until Task 6 (senior), Task 9
/// (caregiver, medic) and Task 11 (DAS) replace their case.
struct RoleHome: View {
    let role: String

    var body: some View {
        switch role {
        case "medic": Placeholder(title: String(localized: "medic_home"))
        case "caregiver": Placeholder(title: String(localized: "caregiver_home"))
        // The senior's page is titled with her form of address once loaded, the app's name before
        case "senior": Placeholder(title: String(localized: "app_name"))
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
