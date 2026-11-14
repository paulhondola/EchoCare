import SwiftUI

/// Each role's home (`homeFor`, Routes.swift). DAS's is a placeholder, the role's title in a
/// `Frame`, until Task 11 replaces its case. `open` pushes a page over the home.
struct RoleHome: View {
    let role: String
    /// A read refused as signed out or not registered ends the session (seniors §8.2).
    let onSessionEnd: (Failure) -> Void
    let open: (HomeRoute) -> Void
    @Binding var sent: Bool

    var body: some View {
        switch homeFor(role) {
        case .medicHome:
            MedicHomeView(
                onMonitor: { open(.monitor) },
                onNew: { open(.enroll(id: nil)) },
                onOpen: { open(.senior(id: $0)) },
                onDraft: { open(.enroll(id: $0)) },
                onSessionEnd: onSessionEnd,
                sent: $sent
            )
        case .seniors(let role):
            SeniorsView(role: role, onOpen: { open(.senior(id: $0)) }, onSessionEnd: onSessionEnd)
        case .own:
            SeniorHome(onSessionEnd: onSessionEnd)
        case .incidents:
            Placeholder(title: String(localized: "role_das"))
        }
    }
}

private struct Placeholder: View {
    let title: String

    var body: some View {
        Frame(title) { EmptyView() }
    }
}
