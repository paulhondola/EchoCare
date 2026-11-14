import SwiftUI

/// Each role's home (`homeFor`, Routes.swift). `open` pushes a page over the home.
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
            IncidentsView(onOpen: { open(.incident(id: $0)) }, onSessionEnd: onSessionEnd)
        }
    }
}
